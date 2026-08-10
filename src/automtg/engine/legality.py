"""Legal action enumeration -- the single source of truth for "what can I do?".

Both the HTTP action list and the RL action mask are built from this function, so
the two can never disagree about what is legal.  The ordering is deterministic:
the same state always produces the same list in the same order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import combat as combat_mod
from .actions import Action, PendingDecision
from .carddef import CardDef
from .characteristics import chars
from .costs import can_pay, can_pay_mana, commander_cost, land_drops_available
from .enums import ActionKind, DecisionKind, Keyword, Step, Zone
from .mana import Requirement, max_affordable_x, solve_payment
from .structs import TargetRef
from .targeting import enumerate_target_tuples

if TYPE_CHECKING:  # pragma: no cover
    from .state import GameState


def legal_actions(state: GameState) -> list[Action]:
    """Every action the player with the pending decision may take."""
    if state.game_over:
        return []
    decision = state.pending_decision
    if decision is None:
        return []

    kind = decision.kind
    if kind is DecisionKind.PRIORITY:
        return _priority_actions(state, decision.player)
    if kind is DecisionKind.DECLARE_ATTACKERS:
        return _attacker_actions(state, decision.player)
    if kind is DecisionKind.DECLARE_BLOCKERS:
        return _blocker_actions(state, decision.player)
    if kind is DecisionKind.MULLIGAN:
        return [
            Action(kind=ActionKind.MULLIGAN, label="Mulligan"),
            Action(kind=ActionKind.KEEP, label="Keep"),
        ]
    if kind is DecisionKind.MAY:
        return [
            Action(kind=ActionKind.YES, label="Yes"),
            Action(kind=ActionKind.NO, label="No"),
        ]
    return _choice_actions(decision)


# ----------------------------------------------------------------------
# choices
# ----------------------------------------------------------------------


def _choice_actions(decision: PendingDecision) -> list[Action]:
    out = [
        Action(
            kind=ActionKind.CHOOSE,
            choice=i,
            label=decision.options[i].label,
            targets=(decision.options[i].ref,) if decision.options[i].ref else (),
        )
        for i in decision.remaining_options
    ]
    if decision.allow_done and not decision.is_complete:
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done"))
    if not out:
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done"))
    return out


# ----------------------------------------------------------------------
# combat declarations
# ----------------------------------------------------------------------


def _attacker_actions(state: GameState, pid: int) -> list[Action]:
    out: list[Action] = []
    defenders = combat_mod.legal_defenders(state)
    for oid in combat_mod.legal_attackers(state):
        name = state.card(oid).name
        for defender in defenders:
            out.append(
                Action(
                    kind=ActionKind.ADD_ATTACKER,
                    source=oid,
                    targets=(TargetRef.player(defender),),
                    label=f"Attack p{defender} with {name}",
                )
            )
    out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done attacking"))
    del pid
    return out


def _blocker_actions(state: GameState, pid: int) -> list[Action]:
    out: list[Action] = []
    for blocker_oid, attacker_oid in combat_mod.legal_blocks(state, pid):
        out.append(
            Action(
                kind=ActionKind.ADD_BLOCKER,
                source=blocker_oid,
                targets=(TargetRef.obj(attacker_oid),),
                label=f"Block {state.card(attacker_oid).name} with {state.card(blocker_oid).name}",
            )
        )
    if combat_mod.blocks_valid(state, pid):
        out.append(Action(kind=ActionKind.FINISH_DECLARATION, label="Done blocking"))
    return out


# ----------------------------------------------------------------------
# priority
# ----------------------------------------------------------------------


def _priority_actions(state: GameState, pid: int) -> list[Action]:
    out: list[Action] = [Action(kind=ActionKind.PASS, label="Pass")]
    sorcery_speed = _can_act_at_sorcery_speed(state, pid)

    if sorcery_speed and land_drops_available(state, pid) > 0:
        out.extend(_land_actions(state, pid))

    out.extend(_cast_actions(state, pid, sorcery_speed))
    out.extend(_activate_actions(state, pid, sorcery_speed))
    return out


def _can_act_at_sorcery_speed(state: GameState, pid: int) -> bool:
    return (
        state.active_player == pid
        and state.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN)
        and not state.stack
    )


def _land_actions(state: GameState, pid: int) -> list[Action]:
    """One action per land *object* in hand, not per land name.

    Two Forests are the same play in rules terms, but the UI keys everything by
    object id: it dims any hand card no action names.  Deduplicating by
    ``card.id`` here made the second and third Forest unclickable and
    undraggable, which is a much worse trade than a slightly wider action list.
    """
    from .characteristics import (
        player_plays_lands_from_graveyard,
        player_plays_lands_from_library_top,
    )

    zones = [state.players[pid].hand]
    if player_plays_lands_from_graveyard(state, pid):
        # Ramunap Excavator, Crucible of Worlds, Ancient Greenwarden. Still one
        # land drop -- this widens *where* a land may be played from, not how
        # many, which `lands_played` already governs.
        zones.append(state.players[pid].graveyard)
    if player_plays_lands_from_library_top(state, pid) and state.players[pid].library:
        # The top card only -- which is what the cards say, and the only part
        # of a hidden zone anybody is entitled to see.
        zones.append(state.players[pid].library[:1])

    out: list[Action] = []
    for zone in zones:
        for oid in zone:
            card = state.card(oid)
            if not card.is_land:
                continue
            out.append(
                Action(kind=ActionKind.PLAY_LAND, source=oid, label=f"Play {card.name}")
            )
    return out


def _cast_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    out: list[Action] = []

    # Per object, not per card name -- see the note on _land_actions.
    for oid in state.players[pid].hand:
        card = state.card(oid)
        if card.is_land:
            continue
        if not _timing_ok(card, sorcery_speed):
            continue
        out.extend(_cast_options(state, pid, oid, card, extra_generic=0))

    for oid in state.players[pid].command:
        obj = state.objects[oid]
        if not obj.is_commander:
            continue
        card = state.card(oid)
        if not _timing_ok(card, sorcery_speed):
            continue
        out.extend(
            _cast_options(state, pid, oid, card, extra_generic=commander_cost(state, oid))
        )
    return out


def _timing_ok(card: CardDef, sorcery_speed: bool) -> bool:
    if card.is_instant or Keyword.FLASH.value in card.keywords:
        return True
    return sorcery_speed


def _cast_options(
    state: GameState, pid: int, oid: int, card: CardDef, *, extra_generic: int
) -> list[Action]:
    """Every distinct way to cast this card right now.

    Kicker makes that plural for one card: paying the extra cost and not paying
    it are two different actions with the same source, offered side by side, and
    the player picks.  Unkicked is listed first so the cheap line stays the
    obvious one.
    """
    exclude_sid = state.objects[oid].stack_id
    tuples = enumerate_target_tuples(
        state, pid, card.targets, oid, exclude_sid=exclude_sid
    )
    if not tuples:
        return []

    out = _cast_variant(state, pid, oid, card, tuples, extra_generic=extra_generic, kicked=False)
    if card.kicker is not None:
        out += _cast_variant(state, pid, oid, card, tuples, extra_generic=extra_generic, kicked=True)
    return out


def _cast_variant(
    state: GameState,
    pid: int,
    oid: int,
    card: CardDef,
    tuples,
    *,
    extra_generic: int,
    kicked: bool,
) -> list[Action]:
    from .costs import cost_reduction, mana_sources

    sources = mana_sources(state, pid)
    pool = state.players[pid].mana_pool

    cost = card.mana_cost.plus(card.kicker) if kicked else card.mana_cost
    discount = cost_reduction(state, pid, card)

    x = 0
    if cost.x_count:
        x = max_affordable_x(cost, pool, sources)
        if x < 0:
            return []

    # Solve rather than merely test: the solution names the permanents that
    # would tap, which is what lets the client show a hovered spell eating into
    # the mana row.  `can_pay_mana` would run the same solver and discard it.
    req = cost.with_x(x)
    generic = max(0, req.generic + extra_generic - discount)
    if generic != req.generic:
        req = Requirement(colored=req.colored, generic=generic)
    payment = solve_payment(req, pool, sources)
    if payment is None:
        return []
    # Sources only.  `Payment` does not itemise which floating mana it spent, so
    # claiming a pool pip here would be a guess; the client dims source pips and
    # says nothing about the pool.
    pays = tuple(dict.fromkeys(tap[0] for tap in payment.taps))

    label_base = f"Cast {card.name}"
    if kicked:
        label_base += " (kicked)"
    if extra_generic:
        label_base += f" (+{extra_generic})"
    out = []
    for targets in tuples:
        label = label_base
        if targets:
            label += " -> " + ", ".join(_describe_ref(state, ref) for ref in targets)
        out.append(
            Action(
                kind=ActionKind.CAST,
                source=oid,
                targets=targets,
                x=x,
                kicked=kicked,
                label=label,
                pays=pays,
            )
        )
    return out


#: The gates :func:`unplayable_reason` can name, in the order it checks them.
UNPLAYABLE_REASONS = ("priority", "timing", "land_drop", "mana", "targets")


def unplayable_reason(state: GameState, pid: int, oid: int) -> str | None:
    """Why this card in ``pid``'s hand cannot be played right now, for the UI.

    The client dims any hand card that no action names, which tells the player
    "no" without ever telling them why -- "not enough mana", "sorcery, and it
    is not your main phase" and "no legal target" all look identical.  This
    walks the same gates :func:`_priority_actions` walks, in the same order,
    and names the first one that closes.

    Returns ``None`` exactly when a legal action for ``oid`` exists.  That is an
    invariant worth stating out loud, because this function necessarily
    restates logic owned by the generators above: it is a diagnostic, never an
    authority, and :func:`legal_actions` remains the only source of truth.
    ``tests/unit/test_legality_reasons.py`` pins the two together.
    """
    decision = state.pending_decision
    if (
        state.game_over
        or decision is None
        or decision.kind is not DecisionKind.PRIORITY
        or decision.player != pid
    ):
        return "priority"

    card = state.card(oid)
    sorcery_speed = _can_act_at_sorcery_speed(state, pid)

    if card.is_land:
        if not sorcery_speed:
            return "timing"
        if land_drops_available(state, pid) <= 0:
            return "land_drop"
        return None

    if not _timing_ok(card, sorcery_speed):
        return "timing"

    # Hand cards never owe commander tax -- that is a command-zone cost only.
    from .costs import cost_reduction

    discount = cost_reduction(state, pid, card)
    x = 0
    if card.mana_cost.x_count:
        from .costs import mana_sources

        x = max_affordable_x(
            card.mana_cost, state.players[pid].mana_pool, mana_sources(state, pid)
        )
        if x < 0:
            return "mana"
    if not can_pay_mana(state, pid, card.mana_cost, x=x, extra_generic=-discount):
        return "mana"

    exclude_sid = state.objects[oid].stack_id
    if not enumerate_target_tuples(
        state, pid, card.targets, oid, exclude_sid=exclude_sid
    ):
        return "targets"
    return None


def _activate_actions(state: GameState, pid: int, sorcery_speed: bool) -> list[Action]:
    out: list[Action] = []
    for oid in state.battlefield:
        obj = state.objects.get(oid)
        if obj is None or obj.controller != pid or obj.abilities_locked:
            continue
        card = state.card_of(obj)
        for ability in card.abilities:
            if not ability.is_activated or ability.is_mana_ability:
                # Mana abilities are activated automatically by the payment
                # solver; offering them separately would only add noise.
                continue
            if ability.sorcery_speed_only and not sorcery_speed:
                continue
            x = 0
            if ability.cost is not None and ability.cost.mana.x_count:
                from .costs import mana_sources

                x = max_affordable_x(
                    ability.cost.mana, state.players[pid].mana_pool, mana_sources(state, pid)
                )
                if x < 0:
                    continue
            if not can_pay(state, pid, ability.cost, oid, x=x):
                continue
            tuples = enumerate_target_tuples(state, pid, ability.targets, oid)
            if not tuples:
                continue
            for targets in tuples:
                label = f"{card.name}: {ability.text or 'activate'}"
                if targets:
                    label += " -> " + ", ".join(_describe_ref(state, ref) for ref in targets)
                out.append(
                    Action(
                        kind=ActionKind.ACTIVATE,
                        source=oid,
                        ability_index=ability.index,
                        targets=targets,
                        x=x,
                        label=label,
                    )
                )
    return out


def _describe_ref(state: GameState, ref: TargetRef) -> str:
    if ref.kind == "player":
        return state.players[ref.id].name or f"p{ref.id}"
    if ref.kind == "stack":
        item = state.stack_item(ref.id)
        return item.description if item else f"stack#{ref.id}"
    obj = state.objects.get(ref.id)
    return state.card_of(obj).name if obj else f"#{ref.id}"


def summarize(state: GameState) -> list[str]:  # pragma: no cover - debug helper
    return [a.label or a.kind.value for a in legal_actions(state)]


def creature_can_attack(state: GameState, oid: int) -> bool:
    """Exposed for the heuristic agent and the UI."""
    c = chars(state, oid)
    return "Creature" in c.types and combat_mod.can_attack(state, oid)


def zone_name(state: GameState, oid: int) -> str:
    obj = state.objects.get(oid)
    return obj.zone.value if obj else Zone.EXILE.value
