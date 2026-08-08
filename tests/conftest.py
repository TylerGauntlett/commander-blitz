"""Shared test fixtures.

The star of this module is :class:`GameBuilder`, which puts the game into an
exact, hand-specified position -- known hands, known battlefields, a known top of
library -- so a rules test can assert one thing without playing ten turns first.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import pytest

from automtg.cards.registry import CardRegistry, GameData, load_decks
from automtg.engine.actions import Action, PendingDecision
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.game import Game
from automtg.engine.player import PlayerState
from automtg.engine.rng import Rng
from automtg.engine.state import GameState, new_object

REPO_ROOT = Path(__file__).resolve().parents[1]
CARD_DIR = REPO_ROOT / "data" / "cards"
TEST_CARD_DIR = Path(__file__).resolve().parent / "data"

#: Library filler so tests never lose to decking by accident.
FILLER_CARD = "island"
FILLER_COUNT = 40


@pytest.fixture(scope="session")
def registry() -> CardRegistry:
    """Every real card plus the test-only cards."""
    paths = sorted(CARD_DIR.glob("*.cards.json")) + sorted(TEST_CARD_DIR.glob("*.cards.json"))
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


class GameBuilder:
    """Construct a game in an exact position, skipping setup and mulligans.

    Example::

        game = (GameBuilder(reg, players=2, seed=7)
                .hand(0, ["t_counterspell", "island", "island"])
                .battlefield(0, ["island", "island"])
                .battlefield(1, ["t_bear"])
                .life(1, 3)
                .step(Step.PRECOMBAT_MAIN)
                .build())
    """

    def __init__(self, registry: CardRegistry, *, players: int = 2, seed: int = 0) -> None:
        self.registry = registry
        self.state = GameState(
            registry=registry,
            players=[PlayerState(pid=i, name=f"P{i}") for i in range(players)],
            rng=Rng(seed),
        )
        self.state.turn = 1
        self.state.round = 1
        self.state.step = Step.PRECOMBAT_MAIN
        self.state.active_idx = 0
        self.state.starting_player = 0
        self._explicit_library: set[int] = set()

    # -- zone population ----------------------------------------------------

    def hand(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.HAND)
            self.state.players[pid].hand.append(obj.oid)
        return self

    def battlefield(
        self,
        pid: int,
        card_ids: Sequence[str],
        *,
        tapped: bool = False,
        sick: bool = False,
        counters: dict[str, int] | None = None,
    ) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.BATTLEFIELD)
            obj.tapped = tapped
            # Permanents start having been controlled since before this turn, so
            # creatures can attack unless a test explicitly asks for sickness.
            obj.entered_turn = self.state.turn if sick else self.state.turn - 1
            if counters:
                obj.counters = dict(counters)
            self.state.battlefield.append(obj.oid)
        self.state.bump_chars()
        return self

    def library(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        """Set the exact top of this player's library (index 0 is the top card)."""
        self._explicit_library.add(pid)
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.LIBRARY)
            self.state.players[pid].library.append(obj.oid)
        return self

    def graveyard(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(self.state, card_id, owner=pid, zone=Zone.GRAVEYARD)
            self.state.players[pid].graveyard.append(obj.oid)
        return self

    def commander(self, pid: int, card_ids: Sequence[str]) -> GameBuilder:
        for card_id in card_ids:
            obj = new_object(
                self.state, card_id, owner=pid, zone=Zone.COMMAND, is_commander=True
            )
            self.state.players[pid].command.append(obj.oid)
            self.state.players[pid].commanders.append(obj.oid)
        return self

    # -- scalar state -------------------------------------------------------

    def life(self, pid: int, amount: int) -> GameBuilder:
        self.state.players[pid].life = amount
        return self

    def step(self, step: Step) -> GameBuilder:
        self.state.step = step
        return self

    def turn(self, turn: int) -> GameBuilder:
        self.state.turn = turn
        return self

    def active(self, pid: int) -> GameBuilder:
        self.state.active_idx = pid
        return self

    def lands_played(self, pid: int, count: int) -> GameBuilder:
        self.state.players[pid].lands_played = count
        return self

    def max_turns(self, turns: int) -> GameBuilder:
        self.state.max_turns = turns
        return self

    # -- build --------------------------------------------------------------

    def build(self, *, advance: bool = True) -> Game:
        """Finish the position and hand back a ``Game``.

        ``advance=False`` leaves the game frozen exactly as described.  Use it
        when the assertion is about the position itself: advancing runs the
        engine's auto-pass, which will happily roll several turns forward when
        nobody has a real decision to make.
        """
        state = self.state
        for player in state.players:
            if player.pid not in self._explicit_library:
                for _ in range(FILLER_COUNT):
                    obj = new_object(state, FILLER_CARD, owner=player.pid, zone=Zone.LIBRARY)
                    player.library.append(obj.oid)
            player.has_kept_hand = True

        state.started = True
        state.step_started = True
        state.bump_chars()
        game = Game(state)
        if advance:
            game._advance()
        return game


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
