"""Shared test fixtures.

:class:`GameBuilder` -- the exact-position builder most rules tests start from --
now lives in ``automtg.engine.sandbox`` and is re-exported here, because the
card-authoring verifier needs it too and production code must not import from
the test suite. Every test that does ``from tests.conftest import GameBuilder``
keeps working.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from automtg.cards.registry import CardRegistry, GameData, authored_card_paths, load_decks
from automtg.engine.actions import Action, PendingDecision
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.game import Game
from automtg.engine.sandbox import GameBuilder

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
