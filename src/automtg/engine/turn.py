"""The turn structure: step transitions and turn-based actions.

``begin_step`` is a generator because a couple of turn-based actions need a
decision (discarding to hand size).  Everything else runs straight through.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

from . import combat as combat_mod
from . import suspend
from .actions import PendingDecision
from .characteristics import player_has_no_hand_limit, untap_also
from .effects.context import EffectContext, ask_objects
from .enums import DecisionKind, Step
from .events import EventType
from .player import MAX_HAND_SIZE
from .primitives import (
    clear_until_eot,
    discard_cards,
    draw_cards,
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
        fire(state, EventType.UPKEEP, player=state.active_player)
    elif step is Step.DRAW:
        _draw_step(state)
    elif step is Step.BEGIN_COMBAT:
        combat_mod.start_combat(state)
        fire(state, EventType.BEGIN_COMBAT, player=state.active_player)
    elif step is Step.DECLARE_ATTACKERS:
        _declare_attackers_step(state)
    elif step is Step.DECLARE_BLOCKERS:
        _declare_blockers_step(state)
    elif step is Step.FIRST_STRIKE_DAMAGE:
        combat_mod.deal_combat_damage(state, first_strike_step=True)
    elif step is Step.COMBAT_DAMAGE:
        combat_mod.deal_combat_damage(state, first_strike_step=False)
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


def _draw_step(state: GameState) -> None:
    pid = state.active_player
    # In a two-player game the starting player skips their first draw.
    skip = state.turn == 1 and pid == state.starting_player and state.num_players == 2
    if not skip:
        draw_cards(state, pid, 1)
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
        discard_cards(state, pid, picked)
    clear_until_eot(state)
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
