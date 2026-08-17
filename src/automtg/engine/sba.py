"""State-based actions.

Run to a fixpoint before any player receives priority and after anything
resolves.  Order within a pass does not matter because the caller loops until
nothing changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .characteristics import chars
from .enums import Keyword, LossReason, Zone
from .events import EventType
from .objects import MINUS_ONE, PLUS_ONE
from .player import COMMANDER_DAMAGE_THRESHOLD
from .zones import destroy, move_object

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState

#: Safety valve: SBAs that keep changing something forever indicate a rules bug.
MAX_SBA_PASSES = 100


def run(state: GameState) -> None:
    """Apply state-based actions until nothing changes."""
    for _ in range(MAX_SBA_PASSES):
        if not check(state):
            break
    check_game_over(state)


def check(state: GameState) -> bool:
    """One pass.  Returns True if anything changed."""
    changed = False
    changed |= _player_losses(state)
    changed |= _tokens_and_attachments(state)
    changed |= _counter_annihilation(state)
    changed |= _creature_deaths(state)
    changed |= _planeswalker_deaths(state)
    changed |= _legend_rule(state)
    changed |= _ascend(state)
    return changed


#: Permanents you must control to get the city's blessing (rule 702.131a).
ASCEND_THRESHOLD = 10


def _ascend(state: GameState) -> bool:
    """The city's blessing, granted by a **state trigger** (rule 702.131a).

    Not a triggered ability, and that is the whole reason this lives here.
    Ascend is not an *event*: a player at nine permanents who plays a land gets
    the blessing at the instant of the tenth, with nothing having fired, and
    gets it during an opponent's turn just as readily. State triggers are
    checked whenever state-based actions are, use no stack and cannot be
    responded to -- so this is the pass they belong in, beside the legend rule.

    One-way, for the rest of the game: it survives the permanents leaving, it
    survives the Ascend card itself leaving, and it is shared by every card that
    player controls. A trigger-plus-counter version would be a *different* card
    in the direction that matters, because a re-checked trigger would come and
    go.
    """
    changed = False
    for pid in state.alive():
        if state.players[pid].has_city_s_blessing:
            continue
        # Someone must actually have Ascend for the check to matter. Read off
        # the battlefield rather than stored, so a card that leaves stops
        # granting it -- to anyone who does not have it already.
        if not any(
            (obj := state.objects.get(oid)) is not None
            and obj.controller == pid
            and state.card_of(obj).ascend
            for oid in state.battlefield
        ):
            continue
        permanents = sum(
            1
            for oid in state.battlefield
            if (obj := state.objects.get(oid)) is not None and obj.controller == pid
        )
        if permanents >= ASCEND_THRESHOLD:
            state.players[pid].has_city_s_blessing = True
            state.emit(EventType.CITY_S_BLESSING, player=pid)
            state.bump_chars()
            changed = True
    return changed


# ----------------------------------------------------------------------
# players
# ----------------------------------------------------------------------


#: Rule 704.5c: ten or more poison counters and the player loses.
POISON_THRESHOLD = 10


def _player_losses(state: GameState) -> bool:
    changed = False
    for player in state.players:
        if player.has_lost:
            continue
        reason: LossReason | None = None
        if player.life <= 0:
            reason = LossReason.LIFE
        elif player.attempted_draw_from_empty:
            reason = LossReason.EMPTY_LIBRARY
        elif player.max_commander_damage() >= COMMANDER_DAMAGE_THRESHOLD:
            reason = LossReason.COMMANDER_DAMAGE
        elif player.poison >= POISON_THRESHOLD:
            # Rule 704.5c. Its own reason rather than folding into LIFE,
            # because a player at 40 life who loses to poison did not run out
            # of life, and a log that said so would be lying about the game.
            reason = LossReason.POISON
        if reason is not None:
            _eliminate(state, player.pid, reason)
            changed = True
    return changed


def _eliminate(state: GameState, pid: int, reason: LossReason) -> None:
    """Remove a player from the game and everything they own with them."""
    player = state.players[pid]
    player.has_lost = True
    player.loss_reason = reason
    state.emit(EventType.PLAYER_LOST, player=pid, reason=reason.value)

    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is not None and (obj.owner == pid or obj.controller == pid):
            move_object(state, oid, Zone.EXILE, cause="player_left")

    state.stack = [item for item in state.stack if item.controller != pid]
    state.pending_triggers = [t for t in state.pending_triggers if t.controller != pid]
    if state.combat is not None:
        for attacker, defender in list(state.combat.attackers.items()):
            if defender == pid:
                state.combat.remove(attacker)
    player.mana_pool.clear()
    state.bump_chars()


def check_game_over(state: GameState) -> None:
    """A game ends when one player remains, or none do."""
    if state.game_over:
        return
    alive = state.alive()
    if len(alive) <= 1:
        state.game_over = True
        state.winners = list(alive)
        state.result = "win" if alive else "draw"
        state.priority_idx = None
        state.pending_decision = None
        state.pending_generator = None
        state.emit(EventType.GAME_OVER, winners=state.winners, result=state.result)


def declare_draw(state: GameState, reason: str) -> None:
    """End the game in a draw (turn cap reached, or a rules loop was detected)."""
    if state.game_over:
        return
    state.game_over = True
    state.winners = []
    state.result = "draw"
    state.priority_idx = None
    state.pending_decision = None
    state.pending_generator = None
    state.emit(EventType.GAME_OVER, winners=[], result="draw", reason=reason)


# ----------------------------------------------------------------------
# permanents
# ----------------------------------------------------------------------


def _tokens_and_attachments(state: GameState) -> bool:
    changed = False

    # A token that has left the battlefield ceases to exist.
    #
    # **Except on the stack.** A copy of a spell is a token object sitting on
    # the stack (706.10), and it is a legal object there until it resolves --
    # 704.5e removes it *after*. Popping it here deletes the copy before it can
    # do anything, which is silent: the copy is announced, the log says the
    # spell was copied, and then nothing happens.
    for oid, obj in list(state.objects.items()):
        if not obj.is_token or obj.zone in (Zone.BATTLEFIELD, Zone.STACK):
            continue
        lst = None
        if obj.zone in (Zone.HAND, Zone.GRAVEYARD, Zone.EXILE, Zone.LIBRARY, Zone.COMMAND):
            lst = state.players[obj.owner].zone_list(obj.zone)
        if lst is not None and oid in lst:
            lst.remove(oid)
        state.objects.pop(oid, None)
        changed = True

    # An Aura or Equipment attached to something that is gone (or was never
    # legally attached) falls off; Auras with nothing to enchant are put away.
    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        card = state.card_of(obj)
        if not (card.is_aura or card.is_equipment):
            continue
        target = state.objects.get(obj.attached_to) if obj.attached_to else None
        if target is None or not target.on_battlefield:
            if obj.attached_to is not None:
                obj.attached_to = None
                changed = True
            if card.is_aura:
                move_object(state, oid, Zone.GRAVEYARD, cause="aura_unattached")
                changed = True
    if changed:
        state.bump_chars()
    return changed


def _counter_annihilation(state: GameState) -> bool:
    changed = False
    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        plus = obj.counter(PLUS_ONE)
        minus = obj.counter(MINUS_ONE)
        if plus and minus:
            pairs = min(plus, minus)
            obj.remove_counter(PLUS_ONE, pairs)
            obj.remove_counter(MINUS_ONE, pairs)
            changed = True
    if changed:
        state.bump_chars()
    return changed


def _planeswalker_deaths(state: GameState) -> bool:
    """704.5i: a planeswalker with zero loyalty goes to its owner's graveyard.

    A sibling of `_creature_deaths`'s zero-toughness branch, and the same shape
    for the same reason: this is not destruction, so it goes through
    `move_object` rather than `destroy` and indestructible does not save it.

    Loyalty is counters, so "zero loyalty" is "no loyalty counters" -- which is
    also what a planeswalker that somehow lost its enters-with-counters
    replacement would read, and binning it is right: 306.5b says a planeswalker
    with no loyalty counters on it has zero loyalty.
    """
    changed = False
    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        if "Planeswalker" not in chars(state, oid).types:
            continue
        if obj.counter("loyalty") <= 0:
            move_object(state, oid, Zone.GRAVEYARD, cause="zero_loyalty")
            changed = True
    return changed


def _creature_deaths(state: GameState) -> bool:
    changed = False
    for oid in list(state.battlefield):
        obj = state.objects.get(oid)
        if obj is None:
            continue
        c = chars(state, oid)
        if "Creature" not in c.types:
            continue
        if c.toughness <= 0:
            # Zero toughness is not destruction: indestructible does not save it.
            move_object(state, oid, Zone.GRAVEYARD, cause="zero_toughness")
            changed = True
            continue
        lethal = obj.damage >= c.toughness or (obj.deathtouched and obj.damage > 0)
        if lethal and Keyword.INDESTRUCTIBLE.value not in c.keywords:
            # Name the killer only when there is exactly one candidate. A gang
            # block damages a creature from three sources and `last_damager`
            # holds whichever wrote last, so attributing here would blame an
            # arbitrary blocker; the caption degrades to a plain "Lethal damage"
            # instead, which is true.
            damagers = state.damage_ledger.get(oid, ())
            by = state.last_damager.get(oid) if len(damagers) == 1 else None
            # Through `destroy`, not `move_object`: lethal damage **destroys**
            # (704.5g), so a regeneration shield and totem armor both replace
            # it. `destroy`'s own docstring already claimed this routed through
            # it, and it did not -- a regenerating creature that took lethal
            # damage died with its shield unspent.
            #
            # The indestructible test above stays where it is rather than being
            # left to `destroy`: `changed` has to report whether the board
            # actually moved, and `destroy` returning False is the only way to
            # know.
            if destroy(state, oid, cause="lethal_damage", by=by):
                changed = True
    return changed


def _legend_rule(state: GameState) -> bool:
    """Keep one of each legendary name per player; the rest are put in the graveyard.

    Simplification: the engine keeps the *most recently* played copy rather than
    asking the controller.  Documented in docs/rules-coverage.md.
    """
    changed = False
    seen: dict[tuple[int, str], list[int]] = {}
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None:
            continue
        card = state.card_of(obj)
        if not card.is_legendary:
            continue
        seen.setdefault((obj.controller, card.name), []).append(oid)

    for oids in seen.values():
        if len(oids) < 2:
            continue
        for oid in oids[:-1]:  # battlefield order is arrival order; keep the newest
            move_object(state, oid, Zone.GRAVEYARD, cause="legend_rule")
            changed = True
    return changed
