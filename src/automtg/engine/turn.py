"""The turn structure: step transitions and turn-based actions.

``begin_step`` is a generator because a couple of turn-based actions need a
decision (discarding to hand size).  Everything else runs straight through.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

from . import combat as combat_mod
from . import replacements, suspend
from .actions import PendingDecision
from .characteristics import player_has_no_hand_limit, untap_also
from .effects.context import EffectContext, ask_objects
from .enums import DecisionKind, Keyword, Step
from .events import EventType
from .player import MAX_HAND_SIZE
from .primitives import (
    clear_until_eot,
    untap_all,
    untap_permanent,
)
from .sba import declare_draw
from .triggers import fire

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def begin_step(state: GameState) -> Generator[Any, list[int], None]:
    """Perform the turn-based actions for the step the game has just entered."""
    state.step_started = True
    state.triggers_this_step = 0
    step = state.step

    if step is Step.UNTAP:
        _untap_step(state)
    elif step is Step.UPKEEP:
        # Before the upkeep triggers: removing the last time counter casts the
        # card, and a spell cast this upkeep should be on the stack under
        # anything that triggers from the upkeep itself.
        suspend.tick(state, state.active_player)
        suspend.rebound_tick(state, state.active_player)
        _epic_copy(state, state.active_player)
        fire(state, EventType.UPKEEP, player=state.active_player)
    elif step is Step.DRAW:
        yield from _draw_step(state)
    elif step is Step.BEGIN_COMBAT:
        combat_mod.start_combat(state)
        fire(state, EventType.BEGIN_COMBAT, player=state.active_player)
    elif step is Step.DECLARE_ATTACKERS:
        _declare_attackers_step(state)
    elif step is Step.DECLARE_BLOCKERS:
        _declare_blockers_step(state)
    elif step is Step.FIRST_STRIKE_DAMAGE:
        yield from combat_mod.deal_combat_damage(state, first_strike_step=True)
    elif step is Step.COMBAT_DAMAGE:
        yield from combat_mod.deal_combat_damage(state, first_strike_step=False)
    elif step is Step.END_OF_COMBAT:
        combat_mod.end_combat(state)
    elif step is Step.END_STEP:
        fire(state, EventType.END_STEP, player=state.active_player)
    elif step is Step.CLEANUP:
        yield from _cleanup_step(state)

    yield from _run_delayed(state)


#: Which ``delay`` step names map to which step.  A small whitelist rather than
#: a free-form name, so a typo in a card file fails at load time like every other
#: piece of DSL vocabulary.
DELAY_STEPS = {
    "upkeep": Step.UPKEEP,
    "draw_step": Step.DRAW,
    "begin_combat": Step.BEGIN_COMBAT,
    "end_step": Step.END_STEP,
}


def _run_delayed(state: GameState) -> Generator[Any, list[int], None]:
    """Resolve anything scheduled for the step just entered.

    Resolved directly rather than put on the stack. That is a divergence -- a
    delayed trigger is a real triggered ability and should be respondable -- and
    it is the same trade `docs/rules-coverage.md` records for modes and trigger
    ordering: it is only observable when somebody would respond differently to
    the delayed half than to the spell that scheduled it.

    Fired by *step name*, and a trigger scheduled during a step therefore waits
    for that step's next occurrence: `begin_step` for the current step has
    already run by the time any effect resolves.
    """
    from .effects import execute
    from .effects.context import EffectContext

    if not state.delayed_triggers:
        return
    due = [d for d in state.delayed_triggers if DELAY_STEPS.get(d.step) is state.step]
    if not due:
        return
    state.delayed_triggers = [d for d in state.delayed_triggers if d not in due]
    for delayed in due:
        ctx = EffectContext(
            state=state,
            controller=delayed.controller,
            source_oid=delayed.source_oid,
            targets={},
            bindings=dict(delayed.bindings),
            source_name=delayed.description,
        )
        yield from execute(ctx, list(delayed.effects))


def _untap_step(state: GameState) -> None:
    player = state.players[state.active_idx]
    player.lands_played = 0
    player.extra_land_drops = 0
    # "…for each card you've drawn this turn." Reset at the *start* of the turn
    # rather than at cleanup with `damage_ledger`, for two reasons that both
    # produce a wrong number rather than an error.
    #
    # The opening hand is drawn by `draw_cards` before turn 1 exists, and a
    # mulligan draws seven more; clearing at cleanup would leave all of that
    # sitting in the tally for the whole first turn.
    #
    # And cleanup gets priority back when it triggers something (rule 514.3a).
    # Draws made during that turn are still "this turn" in that window, so
    # clearing before it would zero the count while the turn is still running.
    state.cards_drawn_this_turn.clear()
    # Detain ends at the start of the *detaining* player's next turn (701.30a),
    # so it is cleared here and keyed by who placed it -- naming the player
    # rather than a turn number is what keeps it right when somebody is
    # eliminated and "your next turn" moves.
    for obj in state.objects.values():
        if obj.detained_by == player.pid:
            obj.detained_by = None
    # Phasing (702.26b) happens **before** untapping and it is a turn-based
    # action, not an ability -- which is why it lives here beside the untap
    # rather than in a card's effect list.
    _phase(state, player.pid)
    _day_night(state, player.pid)
    untap_all(state, player.pid)
    # Murkfiend Liege. Untapped after the active player's own untap so the
    # two cannot fight over `skip_next_untap`, which `untap_all` spends.
    for oid in untap_also(state, player.pid):
        obj = state.objects.get(oid)
        if obj is not None and obj.tapped and not obj.skip_next_untap:
            untap_permanent(state, oid)
    # Both counters: `turn` is the rules one, `round` is the one the log prints.
    state.emit(
        EventType.TURN_BEGAN, player=player.pid, turn=state.turn, round=state.round
    )


def _day_night(state: GameState, pid: int) -> None:
    """Set day or night, and turn the daybound permanents over (726).

    Day and night are a designation the **whole table** shares, which is what
    "a game-wide designated state the engine has no place to keep" meant when
    this was refused. `GameState.day_night` is the place, and it is the same
    shape `turn` and `step` already have.

    Three rules, in the order 726 gives them:

    - **726.2a** -- if it is neither day nor night and a daybound permanent is
      on the battlefield, it becomes day. That is why the field starts as
      ``None`` rather than as ``"day"``: a game with no Werewolf in it never has
      a day, and a card that reads "if it's day" must say no rather than yes.
    - **726.2b** -- if it is day and the player whose turn it *was* cast no
      spells during it, it becomes night.
    - **726.2c** -- if it is night and that player cast two or more, it becomes
      day.

    The count comes from `TurnLedger.spells_cast`, which storm already folds in
    `emit`. Read here, at the start of the next turn, because that is when 726
    asks -- and it is the last moment the previous turn's tally still exists,
    since cleanup clears the ledger.

    Turning the permanents over is `transform`, direction forced, because 726.3
    is the whole content: every daybound permanent becomes its nightbound back
    and every nightbound one becomes its daybound front, together, as the
    designation changes.
    """
    from .characteristics import chars

    daybound = [
        oid
        for oid in state.battlefield
        if Keyword.DAYBOUND.value in chars(state, oid).keywords
    ]
    if state.day_night is None:
        if not daybound:
            return
        state.day_night = "day"
        state.emit("became_day", player=pid)
        return

    # Whoever's turn just ended. On the first untap of the game there is no
    # previous turn, and the ledger is empty, which would read as "cast no
    # spells" and make it night before anybody had a chance to play.
    if state.turn <= 1:
        return
    previous = state.players[(state.active_idx - 1) % len(state.players)].pid
    cast = state.turn_ledger.spells_cast.get(previous, 0)
    if state.day_night == "day" and cast == 0:
        _become(state, "night", pid)
    elif state.day_night == "night" and cast >= 2:
        _become(state, "day", pid)


def _become(state: GameState, designation: str, pid: int) -> None:
    from .characteristics import chars
    from .primitives import transform

    state.day_night = designation
    to_back = designation == "night"
    want = Keyword.DAYBOUND.value if to_back else Keyword.NIGHTBOUND.value
    for oid in [
        oid for oid in state.battlefield if want in chars(state, oid).keywords
    ]:
        transform(state, oid, to_back=to_back)
    state.emit(f"became_{designation}", player=pid)


def _phase(state: GameState, pid: int) -> None:
    """Phase this player's permanents out and in (702.26b).

    "A phased-out permanent is treated as though it does not exist" (702.26c) is
    said by taking it out of ``state.battlefield`` and leaving it in
    ``state.objects`` -- the same nowhere a card on the stack and a card under a
    merged permanent already occupy. Every walk of the battlefield therefore
    misses it: targeting, state-based actions, the characteristics statics, the
    combat declarations and the serializer, none of which needed a test of their
    own.

    Three things follow that would each be work in a flag-based implementation:

    - **No zone change.** Nothing moves, so no leaves- or enters-the-battlefield
      trigger fires and `reset_permanent_state` never runs -- which is exactly
      702.26c, and is why counters, auras and damage survive.
    - **No summoning sickness.** `entered_turn` is untouched, so 702.26f ("it is
      treated as having been continuously on the battlefield") is free.
    - **Attachments come back attached.** `attached_to` is untouched too, and
      the Aura phases out beside its host rather than being seen alone by the
      state-based action that would bin it.

    702.26b is a **toggle**, not two rules: a permanent phases out if it is
    phased in and in if it is out, and each does one or the other in a given
    untap step. So both lists are taken from the state as it stands *before*
    anything moves -- decide, then act. Reading the battlefield as it changes
    would send a permanent out and straight back in, or the reverse, and the
    board would look exactly the same afterwards as if phasing did nothing.
    """
    from .characteristics import chars

    going_in = [
        oid
        for oid, obj in state.objects.items()
        if obj.phased_out and obj.controller == pid and not obj.phased_out_indirectly
    ]
    going_out = [
        oid
        for oid in state.battlefield
        if (obj := state.objects.get(oid)) is not None
        and obj.controller == pid
        and Keyword.PHASING.value in chars(state, oid).keywords
    ]
    for oid in going_in:
        _phase_in(state, oid)
    for oid in going_out:
        _phase_out(state, oid, indirect=False)
    state.bump_chars()


def _phase_out(state: GameState, oid: int, *, indirect: bool) -> None:
    obj = state.objects.get(oid)
    if obj is None or oid not in state.battlefield:
        return
    state.battlefield.remove(oid)
    obj.phased_out = True
    obj.phased_out_indirectly = indirect
    state.emit("phased_out", player=obj.controller, source=oid, oid=oid, card=state.card_of(obj).id)
    # 702.26e: whatever is attached to it phases out with it, and is marked as
    # having done so indirectly -- so it comes back when its host does rather
    # than on the schedule of whoever controls it.
    for other_id in list(state.battlefield):
        other = state.objects.get(other_id)
        if other is not None and other.attached_to == oid:
            _phase_out(state, other_id, indirect=True)


def _phase_in(state: GameState, oid: int) -> None:
    obj = state.objects.get(oid)
    if obj is None or not obj.phased_out:
        return
    obj.phased_out = False
    obj.phased_out_indirectly = False
    state.battlefield.append(oid)
    state.emit("phased_in", player=obj.controller, source=oid, oid=oid, card=state.card_of(obj).id)
    for other_id, other in state.objects.items():
        if other.phased_out and other.phased_out_indirectly and other.attached_to == oid:
            _phase_in(state, other_id)


def _epic_copy(state: GameState, pid: int) -> None:
    """Epic: "at the beginning of each of your upkeeps, copy this spell".

    A rule rather than an ability, for suspend's ticking reason: the epic card
    is in a graveyard with no abilities of its own, and the copy belongs to the
    game the way the untap step does.

    The copy is built from a *reconstructed* stack item rather than a live one,
    because the original left the stack the moment it resolved. Everything that
    matters about it -- the card, the controller -- is on the object, and the
    targets are deliberately empty: an epic spell's copies choose their own, and
    keeping the original's would point every copy at a creature that died on the
    turn it was cast.
    """
    from .effects.ops_stack import put_copy_on_stack
    from .structs import StackItem

    oid = state.players[pid].epic_source
    if oid is None:
        return
    obj = state.objects.get(oid)
    if obj is None:
        return
    template = StackItem(
        sid=-1, kind="spell", controller=pid, def_id=obj.def_id, oid=oid
    )
    put_copy_on_stack(state, pid, template)


def _draw_step(state: GameState) -> Generator[Any, list[int], None]:
    """The turn's draw -- and the one place dredge and miracle can interrupt it.

    A generator because those two ask a question, which is the whole reason this
    step could not carry them before. `begin_step` already ran through
    `Game._run`, so nothing above here changed.
    """
    pid = state.active_player
    # In a two-player game the starting player skips their first draw.
    skip = state.turn == 1 and pid == state.starting_player and state.num_players == 2
    if not skip:
        yield from replacements.draw(state, pid, 1)
    fire(state, EventType.DRAW_STEP, player=pid)


def _declare_attackers_step(state: GameState) -> None:
    if state.combat is None:
        combat_mod.start_combat(state)
    attackers = combat_mod.legal_attackers(state)
    defenders = combat_mod.legal_defenders(state)
    if not attackers or not defenders:
        combat_mod.finish_attackers(state)
        return
    state.pending_decision = PendingDecision(
        kind=DecisionKind.DECLARE_ATTACKERS,
        player=state.active_player,
        prompt="Declare attackers",
    )


def _declare_blockers_step(state: GameState) -> None:
    combat = state.combat
    if combat is None or not combat.attackers:
        return
    _next_blocker_decision(state)


def _next_blocker_decision(state: GameState) -> None:
    """Ask the next defending player to declare blocks, or finish the step."""
    combat = state.combat
    if combat is None:
        return
    while combat.pending_blockers:
        pid = combat.pending_blockers[0]
        if not state.is_alive(pid):
            combat.pending_blockers.pop(0)
            continue
        state.pending_decision = PendingDecision(
            kind=DecisionKind.DECLARE_BLOCKERS,
            player=pid,
            prompt="Declare blockers",
        )
        return
    combat_mod.finish_blockers(state)


def _cleanup_step(state: GameState) -> Generator[Any, list[int], None]:
    pid = state.active_player
    player = state.players[pid]
    excess = 0 if player_has_no_hand_limit(state, pid) else len(player.hand) - MAX_HAND_SIZE
    if excess > 0:
        ctx = EffectContext(state=state, controller=pid, source_name="Cleanup")
        picked = yield from ask_objects(
            ctx, "Discard down to seven cards", list(player.hand), excess, excess, pid, "discard"
        )
        yield from replacements.discard(state, pid, picked)
    clear_until_eot(state)
    # "…dealt damage by this creature THIS TURN". Rule 514.2 wipes damage from
    # permanents here; the ledger that remembers who dealt it goes with it, or
    # a Sengir Vampire would keep growing off a creature it hurt last turn.
    state.damage_ledger.clear()
    state.last_damager.clear()
    # And with it every other "this turn" tally. Cleanup rather than untap for
    # the reason the comment in `_untap_step` gives in reverse: none of these can
    # happen before turn 1, so there is nothing for them to have to survive.
    state.turn_ledger.clear()
    # Rule 514.3a: if anything happened, players get priority and cleanup repeats.
    state.cleanup_repeat = bool(state.pending_triggers)


def step_grants_priority(state: GameState) -> bool:
    """Does the current step give players priority?"""
    if state.step is Step.UNTAP:
        return False
    if state.step is Step.CLEANUP:
        return state.cleanup_repeat
    if state.step is Step.DECLARE_ATTACKERS:
        combat = state.combat
        return combat is not None and combat.attackers_declared
    if state.step is Step.DECLARE_BLOCKERS:
        combat = state.combat
        return combat is None or combat.blockers_declared or not combat.attackers
    return True


def next_step(state: GameState) -> Step | None:
    """The step that follows the current one, or ``None`` to start a new turn."""
    step = state.step
    combat = state.combat

    if step is Step.DECLARE_ATTACKERS:
        if combat is None or not combat.attackers:
            return Step.END_OF_COMBAT
        return Step.DECLARE_BLOCKERS
    if step is Step.DECLARE_BLOCKERS:
        return (
            Step.FIRST_STRIKE_DAMAGE
            if combat_mod.has_first_strike_combatants(state)
            else Step.COMBAT_DAMAGE
        )
    if step is Step.FIRST_STRIKE_DAMAGE:
        return Step.COMBAT_DAMAGE
    if step is Step.CLEANUP:
        return None if not state.cleanup_repeat else Step.CLEANUP
    return Step(int(step) + 1)


def advance(state: GameState) -> None:
    """End the current step and enter the next one (or the next turn)."""
    state.empty_all_mana_pools()
    state.emit(EventType.STEP_ENDED, step=state.step.name)

    nxt = next_step(state)
    if nxt is None:
        _begin_next_turn(state)
        return

    state.step = nxt
    state.step_started = False
    state.priority_idx = None
    state.passes_in_row = 0
    if nxt is Step.CLEANUP:
        state.cleanup_repeat = False


def _begin_next_turn(state: GameState) -> None:
    state.cleanup_repeat = False
    before = state.active_idx
    state.active_idx = state.next_alive_index(state.active_idx)
    state.turn += 1
    # A new round starts when the table wraps back past the player who started
    # the game.  Measured as position *relative to the starting player*, not as
    # a raw index: the starting seat is chosen at random, so "index wrapped to
    # 0" would put the first round boundary in the middle of the first lap
    # whenever anyone but seat 0 goes first.
    #
    # ``next_alive_index`` scans forward modulo the seat count, so a wrap is
    # exactly "the new position is not after the old one".  A lone survivor gets
    # its own index back, which is one round per turn -- correct.
    seats = state.num_players
    start = state.starting_player
    if (state.active_idx - start) % seats <= (before - start) % seats:
        state.round += 1
    state.step = Step.UNTAP
    state.step_started = False
    state.priority_idx = None
    state.passes_in_row = 0
    state.combat = None
    if state.turn > state.max_turns:
        declare_draw(state, f"turn cap {state.max_turns} reached")
