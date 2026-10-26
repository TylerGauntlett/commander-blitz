"""State-based actions.

Run to a fixpoint before any player receives priority and after anything
resolves.  Order within a pass does not matter because the caller loops until
nothing changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import battles, sagas
from .characteristics import chars
from .enums import Keyword, LossReason, Supertype, Zone
from .events import EventType
from .objects import MINUS_ONE, PLUS_ONE, SHIELD
from .player import COMMANDER_DAMAGE_THRESHOLD
from .player_statics import outcome_barred_by_static
from .primitives import become_monarch, clear_until_next_turn
from .temp_effects import (
    clear_flash_permissions,
    clear_goad,
    clear_permanent_shields,
    drop_attack_requirements,
)
from .zones import destroy, move_object, sacrifice

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

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
    # One pass is one simultaneous event (704.3): a Kalitas that left in an
    # earlier pass, or in the op before this, no longer replaces anything.
    state.leaving_dies_replacers.clear()
    changed = False
    changed |= _player_losses(state)
    changed |= _tokens_and_attachments(state)
    changed |= _counter_annihilation(state)
    changed |= _creature_deaths(state)
    changed |= _planeswalker_deaths(state)
    changed |= _defeated_battles(state)
    changed |= _finished_sagas(state)
    changed |= _legend_rule(state)
    changed |= _role_rule(state)
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
        if reason is not None and player_cant_lose(state, player.pid):
            # 104.3b: "You can't lose the game this turn" (Angel's Grace). The
            # player keeps playing at zero or negative life and loses the moment
            # the lock ends, which is the whole of what the card buys -- a turn
            # at 1 life or less to find an answer.
            #
            # Checked here rather than by rewriting the life total, because every
            # printed card in this family is a prohibition on the *outcome*: a
            # version that set life to 1 would also stop "whenever you lose
            # life" triggers and would show the wrong number on the board.
            #
            # All four loss reasons are covered, not just life. Angel's Grace
            # says "you can't lose the game", full stop, so an empty library, 21
            # commander damage and ten poison counters are all held off too.
            reason = None
        if reason is not None:
            _eliminate(state, player.pid, reason)
            changed = True
    return changed


def player_cant_lose(state: GameState, pid: int) -> bool:
    """Whether an `OutcomeLock` is holding this seat in the game -- 104.3b.

    Short-circuits on the empty list, which is what `state.outcome_locks` is in
    every game that plays none of these cards.
    """
    if any(lock.player == pid and lock.cant_lose for lock in state.outcome_locks):
        return True

    return outcome_barred_by_static(state, pid, "cant_lose_the_game")


def player_cant_win(state: GameState, pid: int) -> bool:
    """Whether an `OutcomeLock` forbids this seat winning -- 104.3b.

    The other half of the same sentence, and a separate question because most
    cards print only one of the two: Abyssal Persecutor says "you can't win the
    game" and nothing about losing.
    """
    if any(lock.player == pid and lock.cant_win for lock in state.outcome_locks):
        return True

    return outcome_barred_by_static(state, pid, "cant_win_the_game")


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
    # Beside the stack and trigger prunes above, and for the same reason: a
    # designation is a player id, and an eliminated seat is still a valid one.
    # Inert either way -- a dead attacker controls nothing and a dead defender is
    # not in `alive()` -- so this is hygiene, not a fix.
    state.attack_restrictions = [
        r for r in state.attack_restrictions if pid not in (r.attacker, r.defender)
    ]
    # This one is not hygiene. "Until your next turn" is cleared in that
    # player's untap step, and an eliminated player never has another one -- so
    # a prohibition keyed to a seat that has left would last for the rest of the
    # game. (`detained_by` has the same clock and the same hole; it is left
    # alone here because it is a different capability's bug, not this one's.)
    state.block_prohibitions = [
        r
        for r in state.block_prohibitions
        if not (r.duration == "until_your_next_turn" and r.player == pid)
    ]
    # The same hole in the mirror list: "until your next turn, that creature
    # can't be blocked" is cleared in the granting player's untap step, and an
    # eliminated player never has another one -- so the evasion would last for
    # the rest of the game.
    state.unblockables = [
        u
        for u in state.unblockables
        if not (u.duration == "until_your_next_turn" and u.player == pid)
    ]
    # And the same hole again: "until your next turn, you gain protection from
    # everything" is cleared in that player's untap step, so a protection keyed
    # to a seat that has left would stand for the rest of the game -- and unlike
    # the two above it, it would keep protecting nobody while still answering
    # `player_protected_from` for a pid `alive()` never offers.
    state.player_protections = [
        p
        for p in state.player_protections
        if not (p.duration == "until_your_next_turn" and p.player == pid)
    ]
    # And the same hole once more, for the other half of the same card.
    state.life_locks = [
        lock
        for lock in state.life_locks
        if not (lock.duration == "until_your_next_turn" and lock.player == pid)
    ]
    # And the same hole in the cast lock, which is the worst of them: "until
    # your next turn, your opponents can't cast spells from anywhere other than
    # their hands" is cleared in the *caster's* untap step, so killing the
    # caster would leave every other seat locked out of every zone but their
    # hand for the rest of the game. `player` is the clock here, not the locked
    # seat, which is why this reads it and not `affects`.
    state.cast_locks = [
        lock
        for lock in state.cast_locks
        if not (lock.duration == "until_your_next_turn" and lock.player == pid)
    ]
    # And the same hole in goad's mark. It is *more* than a stale flag here:
    # a goad nobody can clear compels every combat for the rest of the game, and
    # its target restriction would keep pointing at an empty seat -- which, with
    # the goader gone, is a defender `alive()` never offers, so the "if able"
    # escape could never fire either. Cleared with `clear_goad`, the same call
    # the untap step makes, because this *is* that player's last untap step.
    clear_goad(state, pid)
    # And the same hole in the permanent-scoped prevention shields: "until your
    # next turn, prevent all damage target permanent would deal" is cleared in
    # the installing player's untap step, so a shield keyed to a seat that has
    # left would pacify the creature it was aimed at for the rest of the game.
    clear_permanent_shields(state, "until_your_next_turn", pid)
    # Hygiene for Gideon Jura's mark: a compelled player who has left never
    # takes the turn it waits for.
    drop_attack_requirements(state, pid)
    # And the same hole in the per-object entries: a -2/-1 or a lifelink "until
    # your next turn" keyed to a seat that has left would stand for good.
    clear_until_next_turn(state, pid)
    # And a timed flash permission keyed to a seat that has left.
    clear_flash_permissions(state, "until_your_next_turn", pid)
    player.mana_pool.clear()
    _monarch_left(state, pid)
    state.bump_chars()


def _monarch_left(state: GameState, pid: int) -> None:
    """"If the monarch leaves the game, the active player becomes the monarch" (721.5).

    Here rather than nowhere, because a designation is a *player id* and an
    eliminated player is still a valid one: without this the crown sits on a seat
    that has left, the end-step draw finds nobody to draw for, and every "if
    there is no monarch" reads False for the rest of the game. All three are
    silent -- the field looks perfectly ordinary.

    Written after `has_lost` is set, so `become_monarch`'s own liveness guard and
    `next_alive_index` both see the table as it now stands. A monarch eliminated
    on their own turn hands it to the next seat in turn order, which is 721.5's
    second sentence and is what `next_alive_index` returns.

    Unreachable in a two-player game -- the monarch losing ends it -- so this is
    for the pod.
    """

    if state.monarch != pid:
        return
    state.monarch = None
    # A static may ask who the monarch is (`is_monarch`), so the cache goes
    # with the crown -- here as well as in `become_monarch`, for the pod where
    # nobody is left to take it.
    state.bump_chars()
    successor = (
        state.active_player
        if state.is_alive(state.active_player)
        else state.players[state.next_alive_index(state.active_idx)].pid
    )
    if state.is_alive(successor):
        become_monarch(state, successor)


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


def declare_win(state: GameState, pid: int) -> None:
    """"You win the game" -- 104.2b, spelled as 104.2a.

    The engine has exactly one writer of a game result, `check_game_over`, and it
    derives the winner from who is still `alive()`. That is not an accident to
    route around: `Game.over`, `Game.winners`, `state.result`, the `GAME_OVER`
    event and both serializers in `serialize.py` all read what that one function
    wrote. A card that assigned `state.winners` itself would produce a game that
    was over with a winner and *no* `PLAYER_LOST` for the seat that lost, no
    permanents swept off the battlefield, and priority still sitting on
    somebody -- a result that replays and serializes but does not agree with the
    board underneath it.

    So this declares no winner at all. It eliminates every **other** player,
    through the same `_eliminate` a lethal life total reaches, and then knocks on
    the same door; `check_game_over` finds one seat alive and draws its own
    conclusion. That is 104.2a -- "a player still in the game wins the game if
    that player's opponents have all left the game" -- and it is why the pod
    needs no second branch: at four players the sentence removes three seats
    instead of one, which is the shape the rule already had.

    Two no-ops, both deliberate. A game that is already over is not re-decided,
    so the second of two simultaneous wins changes nothing. And a player who has
    already left the game cannot win it -- there is nobody to eliminate on their
    behalf, and eliminating the rest anyway would end the game in a *draw*,
    `check_game_over` finding nobody alive.

    Deliberately not modelled, because no card in the pool needs it yet:

    - **"You can't win the game" / "can't lose the game"** (Platinum Angel,
      Abyssal Persecutor). That is replacement-shaped and belongs beside the
      other continuous prohibitions, not in this function.
    - **The pod's real ending.** By 800.4 a player who wins a multiplayer game
      leaves it and the survivors play on; here the game ends for everybody.
      Recorded in docs/rules-coverage.md.
    """
    if state.game_over or not state.is_alive(pid):
        return
    if player_cant_win(state, pid):
        # "Your opponents can't win the game this turn" (Angel's Grace), read
        # from this seat's side: 104.3b makes it a prohibition on *winning*, so
        # the win simply does not happen and the game carries on.
        #
        # Here rather than inside `_eliminate`, because a win is implemented by
        # eliminating everybody else: checked one layer down it would eliminate
        # some opponents and then stop, leaving a game whose result nobody had
        # declared and whose board had been half dismantled.
        return
    for other in state.alive():
        if other != pid:
            _eliminate(state, other, LossReason.OPPONENT_WON)
    check_game_over(state)


def declare_loss(state: GameState, pids: Iterable[int]) -> None:
    """ "That player loses the game" -- 104.3a.

    The mirror of :func:`declare_win`, and narrower on purpose: it eliminates
    **only** the named seat, through the same `_eliminate` a lethal life total
    reaches, then asks `check_game_over`. Written as `declare_win` on an
    opponent it would be a different sentence -- in a pod, one Assassin hit
    would knock out every other seat too.

    Every named seat is eliminated before the game-over check, so "each player
    loses the game" is a draw (104.4a) rather than a win for whichever seat the
    loop reached last. A game already over, or a seat already gone, is a no-op.
    "Can't lose the game" (Platinum Angel) is not modelled.
    """
    if state.game_over:
        return
    for pid in pids:
        if state.is_alive(pid):
            _eliminate(state, pid, LossReason.LOST_BY_EFFECT)
    check_game_over(state)


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
        # 704.5n reads "attached to an illegal **object or player**, or is not
        # attached to an object or player". An Aura enchanting a player who is
        # still in the game has a legal host, so it is not binned -- and getting
        # this wrong is not a subtle bug: "Enchant opponent" resolved, attached
        # to a seat and was in the graveyard before its own enters trigger could
        # resolve, so the card played as a blank.
        #
        # A player who has *lost* is an illegal host, and the Aura goes with
        # them by falling through to the branch below. `is_alive` rather than a
        # seat-count test, because a player eliminated in a pod keeps their
        # index -- the list is never compacted.
        if obj.attached_to_player is not None:
            if state.is_alive(obj.attached_to_player):
                continue
            obj.attached_to_player = None
            changed = True
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


def _defeated_battles(state: GameState) -> bool:
    """704.5x: a battle with no defense counters is put into its owner's graveyard.

    The sibling of `_planeswalker_deaths` immediately above, and the same shape
    for the same reason: this is not destruction, so it goes through
    `move_object` and indestructible does not save it.

    Directly after the planeswalker pass rather than anywhere else in the order,
    because the two are one rule read twice -- 506.2's non-seat defenders, each
    with its own counter kind -- and a reader looking for one should find the
    other. `check` loops to a fixed point anyway, so the placement is legibility
    rather than correctness.

    The reason the test is a call into `battles` rather than a bare
    `obj.counter("defense") <= 0` here: `battles.defeated` is where 704.5x's
    exemption for a battle that is the source of a trigger on the stack will go,
    and it carries the note saying why there is nothing to exempt yet.
    """
    changed = False
    for oid in list(state.battlefield):
        if not battles.is_battle(state, oid):
            continue
        if battles.defeated(state, oid):
            move_object(state, oid, Zone.GRAVEYARD, cause="defeated")
            changed = True
    return changed


def _finished_sagas(state: GameState) -> bool:
    """704.5s: a Saga that has run out of chapters is sacrificed.

    "If the number of lore counters on a Saga permanent with one or more chapter
    abilities is greater than or equal to its final chapter number and it isn't
    the source of a chapter ability that has triggered but hasn't left the stack,
    that Saga's controller sacrifices it."

    **A state-based action and not the last line of chapter III**, which is the
    tempting shape and is wrong in a way the card would never report: appended to
    the final chapter's effects, the Saga would be sacrificed part-way through its
    own chapter resolving, so anything later in that chapter would run with its
    source already in a graveyard -- and on Oath of Eorl the crown is granted
    *after* the counter, so a Saga written that way would be reading a dead
    permanent's controller. The rule waits until the chapter has left the stack
    for exactly this reason, and the wait is what makes the "and it isn't the
    source of a chapter ability…" clause necessary.

    A **sacrifice**, so it goes through `zones.sacrifice` rather than `destroy`
    and indestructible does not save it -- which matters, since a Saga is a
    permanent an opponent may well have made indestructible, and the alternative
    is a Saga that sits on the battlefield finished for ever.
    """
    changed = False
    for oid in list(state.battlefield):
        if sagas.finished(state, oid):
            sacrifice(state, oid)
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
            shields = obj.counter(SHIELD)
            if destroy(state, oid, cause="lethal_damage", by=by):
                changed = True
            elif obj.counter(SHIELD) < shields:
                # A shield counter (122.1c) replaced the destruction, and unlike
                # regeneration and totem armor it does **not** remove the marked
                # damage. So the damage is still lethal and 704.3 says to check
                # again: the creature sheds one counter per check until it has
                # none and dies. Reported as a change for that reason alone --
                # without it the loop stops here and a creature standing in
                # lethal damage would survive on one counter until somebody next
                # got priority, then die a check at a time.
                changed = True
    return changed


def _role_rule(state: GameState) -> bool:
    """704.5y: one Role per player per permanent, the newest kept (303.7a).

    "If a permanent has more than one Role controlled by the same player
    attached to it, each of those Roles except the one with the most recent
    timestamp is put into its owner's graveyard." Not destroyed and not
    sacrificed -- put into the graveyard, so a Wicked Role replaced this way
    still drains on its way out.

    Newest by `attached_timestamp`, which is when each became attached (613.7e),
    not by arrival: a Role moved onto a permanent is newer than one created
    there earlier. Roles controlled by *different* players coexist.
    """
    changed = False
    groups: dict[tuple[int, int], list[int]] = {}
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.attached_to is None:
            continue
        if "Role" not in chars(state, oid).subtypes:
            continue
        groups.setdefault((obj.attached_to, obj.controller), []).append(oid)
    for oids in groups.values():
        if len(oids) < 2:
            continue
        order = {oid: i for i, oid in enumerate(state.battlefield)}
        oids.sort(key=lambda o: (state.objects[o].attached_timestamp, order[o]))
        for oid in oids[:-1]:
            move_object(state, oid, Zone.GRAVEYARD, cause="role_rule")
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
        # The derived supertypes, not the printed ones: a token copied "except
        # it's legendary" (Adagia, Windswept Bastion) has a non-legendary card
        # behind it, and the exception is the whole reason the copy is unique.
        if Supertype.LEGENDARY.value not in chars(state, oid).supertypes:
            continue
        seen.setdefault((obj.controller, card.name), []).append(oid)

    for oids in seen.values():
        if len(oids) < 2:
            continue
        for oid in oids[:-1]:  # battlefield order is arrival order; keep the newest
            move_object(state, oid, Zone.GRAVEYARD, cause="legend_rule")
            changed = True
    return changed
