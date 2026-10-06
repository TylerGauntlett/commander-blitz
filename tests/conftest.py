"""Shared test fixtures.

:class:`GameBuilder` -- the exact-position builder most rules tests start from --
lives in ``automtg.engine.sandbox``, because the card-authoring verifier needs
it too and production code must not import from the test suite. Import it from
there; this module uses it only for the ``builder`` fixture.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from automtg.cards.registry import CardRegistry, GameData, authored_card_paths, load_decks
from automtg.cards.schema import CardModel
from automtg.engine.actions import Action, PendingDecision
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.game import Game
from automtg.engine.objects import PLUS_ONE
from automtg.engine.sandbox import GameBuilder
from automtg.engine.structs import TargetRef

REPO_ROOT = Path(__file__).resolve().parents[1]
CARD_DIR = REPO_ROOT / "data" / "cards"
TEST_CARD_DIR = Path(__file__).resolve().parent / "data"



@pytest.fixture(scope="session")
def registry() -> CardRegistry:
    """Every real card -- hand-written *and* machine-authored -- plus the test-only ones.

    `authored_card_paths` rather than a glob of `data/cards/` alone: cards in
    `data/cards/auto/` are shipped and playable, so a fixture that omitted them
    would parametrize tests over ids it cannot then look up.
    """
    paths = authored_card_paths(CARD_DIR) + sorted(TEST_CARD_DIR.glob("*.cards.json"))
    return CardRegistry.from_paths(paths)


@pytest.fixture(scope="session")
def game_data(registry: CardRegistry) -> GameData:
    return GameData(registry=registry, decks=load_decks())


@pytest.fixture(scope="session")
def real_registry() -> CardRegistry:
    """Only the shipped cards -- what a real game uses."""
    return CardRegistry.from_dir(CARD_DIR)


@pytest.fixture
def builder(registry: CardRegistry):
    def make(players: int = 2, seed: int = 0) -> GameBuilder:
        return GameBuilder(registry, players=players, seed=seed)

    return make


# ----------------------------------------------------------------------
# assertions and helpers used across the suite
# ----------------------------------------------------------------------


def find_action(game: Game, kind: ActionKind, **match) -> Action:
    """Find one legal action, failing loudly with the alternatives if absent."""
    for action in game.legal_actions():
        if action.kind is not kind:
            continue
        if all(getattr(action, key) == value for key, value in match.items()):
            return action
    raise AssertionError(
        f"no legal {kind.value} action matching {match}; "
        f"legal actions: {[a.label or a.kind.value for a in game.legal_actions()]}"
    )


def action_for_card(game: Game, kind: ActionKind, card_id: str) -> Action:
    """Find a cast/play action for a card by its definition id."""
    state = game.state
    for action in game.legal_actions():
        if action.kind is not kind or action.source is None:
            continue
        obj = state.objects.get(action.source)
        if obj is not None and obj.def_id == card_id:
            return action
    raise AssertionError(
        f"no legal {kind.value} for {card_id}; "
        f"legal: {[a.label or a.kind.value for a in game.legal_actions()]}"
    )


def pass_until(game: Game, predicate, limit: int = 400) -> None:
    """Pass priority (and decline optional choices) until ``predicate(game)`` holds."""
    for _ in range(limit):
        if predicate(game) or game.over:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("pass_until did not reach its condition")


def _default_answer(game: Game, decision: PendingDecision) -> Action:
    """The most passive legal answer to any decision."""
    actions = game.legal_actions()
    preference = {
        DecisionKind.PRIORITY: ActionKind.PASS,
        DecisionKind.DECLARE_ATTACKERS: ActionKind.FINISH_DECLARATION,
        DecisionKind.DECLARE_BLOCKERS: ActionKind.FINISH_DECLARATION,
        DecisionKind.MULLIGAN: ActionKind.KEEP,
        DecisionKind.MAY: ActionKind.NO,
    }.get(decision.kind, ActionKind.FINISH_DECLARATION)
    for action in actions:
        if action.kind is preference:
            return action
    # `CHOOSE_X` has no passive answer: X = 0 is not "declining", it is casting
    # the spell for nothing. Maximum is what legality used to pin it to, so a
    # test that merely passes priority past an X spell sees what it always saw.
    if decision.kind is DecisionKind.CHOOSE_X:
        choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
        if choices:
            return max(choices, key=lambda a: a.choice or 0)
    return actions[0]


def advance_to_step(game: Game, step: Step, limit: int = 400) -> None:
    pass_until(game, lambda g: g.state.step is step, limit=limit)


def battlefield_ids(game: Game, pid: int | None = None) -> list[str]:
    return [obj.def_id for obj in game.state.battlefield_objects(pid)]


def count_on_battlefield(game: Game, card_id: str, pid: int | None = None) -> int:
    return battlefield_ids(game, pid).count(card_id)


def oids_of(game: Game, card_id: str, pid: int | None = None) -> list[int]:
    return [
        obj.oid for obj in game.state.battlefield_objects(pid) if obj.def_id == card_id
    ]


def only_oid(game: Game, card_id: str, pid: int | None = None) -> int:
    found = oids_of(game, card_id, pid)
    assert len(found) == 1, f"expected exactly one {card_id}, found {len(found)}"
    return found[0]


def event_types(events: Iterable) -> list[str]:
    return [e.type for e in events]


# ----------------------------------------------------------------------
# positions, and the reads and moves many files used to copy
# ----------------------------------------------------------------------


def two_seat_board(builder, mine=(), theirs=(), *, advance: bool = True) -> Game:
    """Player 0's ``mine`` facing player 1's ``theirs``, at the builder's defaults.

    Nothing else: no lands, hands or libraries beyond the builder's filler, in
    the precombat main phase the builder starts in. ``advance=False`` freezes it
    there; otherwise `build()` runs the engine's auto-pass first.
    """
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=advance)
    )


def settle(game: Game) -> None:
    """Pass until the stack is empty and no trigger is waiting to go on it.

    A trigger is *pending*, not on the stack, the moment its event happens -- it
    is promoted the next time a player would receive priority. So the wait is on
    both lists being empty, not just the stack.
    """
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def settle_to_priority(game: Game) -> None:
    """Pass until the stack is empty and nobody is mid-resolution."""
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def settle_completely(game: Game) -> None:
    """Pass until the stack is empty, nothing is waiting to go on it, and the
    decision in front of the table is priority."""
    pass_until(
        game,
        lambda g: (
            not g.state.stack
            and not g.state.pending_triggers
            and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)
        ),
    )


def activations(game: Game, oid: int, index: int | None = None) -> list:
    """The legal activations of ``oid``, optionally of one ability index only."""
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE
        and a.source == oid
        and (index is None or a.ability_index == index)
    ]


def attack_with(game: Game, oid: int, defender: int = 1) -> None:
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(defender),))
    )


def pt(game: Game, oid: int) -> tuple[int, int]:
    c = chars(game.state, oid)
    return c.power, c.toughness


def keywords(game: Game, oid: int) -> set[str]:
    return {str(k) for k in chars(game.state, oid).keywords}


def plus_one_counters(game: Game, oid: int) -> int:
    return game.state.objects[oid].counter(PLUS_ONE)


def hand_ids(game: Game, pid: int = 0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].hand]


def library_ids(game: Game, pid: int = 0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].library]


# ----------------------------------------------------------------------
# probe cards for the loader's refusals
# ----------------------------------------------------------------------


def static_probe(static: dict) -> dict:
    """An enchantment whose one ability is the static ``static`` -- raw, unvalidated."""
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Probe.",
        "mana_cost": "{W}",
        "types": ["Enchantment"],
        "abilities": [{"kind": "static", "text": "Probe.", **static}],
    }


def cost_reduction_probe(reduction) -> CardModel:
    """A {9} draw-a-card sorcery that costs ``reduction`` less to cast."""
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "This spell costs {X} less to cast.",
            "mana_cost": "{9}",
            "types": ["Sorcery"],
            "cost_reduction": reduction,
            "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
        }
    )
