"""The "every card actually works" gate.

For every card in ``data/cards`` this exercises the real code path: put it in a
hand with enough mana and a board rich enough to satisfy its targets, take the
legal action the engine offers, and drive every decision the resolution asks
for.  A card that cannot be cast, or that throws while resolving, fails here.

This is the test that makes "the decks are curated so every card works" a fact
rather than an intention.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automtg.cards.registry import CardRegistry
from automtg.engine.actions import PendingDecision
from automtg.engine.carddef import CardDef
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.game import Game
from automtg.engine.stack import push_spell
from automtg.engine.state import new_object
from tests.conftest import GameBuilder

EXPECTATIONS_PATH = Path(__file__).resolve().parent / "expectations.json"

#: A mana base deep enough for anything in either deck.
MANA_BASE = ["plains"] * 6 + ["island"] * 6 + ["swamp"] * 6 + ["mountain"] * 6 + ["forest"] * 6

#: Things for targeted effects to point at.
OWN_BOARD = ["t_bear", "t_dork"]
OPPONENT_BOARD = ["t_bear", "t_flyer", "sol_ring", "t_anthem", "forest", "island"]
OWN_GRAVEYARD = ["t_bear", "t_dork", "t_flyer"]


@pytest.fixture(scope="session")
def expectations() -> dict:
    if not EXPECTATIONS_PATH.exists():
        return {}
    return json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))


def all_cards(registry: CardRegistry) -> list[CardDef]:
    return [card for card in registry if not card.is_token]


def card_ids(registry: CardRegistry) -> list[str]:
    return sorted(card.id for card in all_cards(registry))


def pytest_generate_tests(metafunc):
    """Parametrize over every shipped card id."""
    if "card_id" not in metafunc.fixturenames:
        return
    registry = CardRegistry.from_dir()
    metafunc.parametrize("card_id", card_ids(registry))


def build_sandbox(registry: CardRegistry, card_id: str, *, in_hand: bool = True) -> Game:
    builder = GameBuilder(registry, players=2, seed=1)
    builder.battlefield(0, MANA_BASE)
    builder.battlefield(0, OWN_BOARD)
    builder.battlefield(1, OPPONENT_BOARD)
    builder.graveyard(0, OWN_GRAVEYARD)
    builder.library(0, ["forest", "island", "swamp", "mountain", "plains"] * 8)
    builder.library(1, ["forest", "island"] * 10)
    if in_hand:
        builder.hand(0, [card_id])
    return builder.build(advance=False)


def add_dummy_spell(game: Game) -> None:
    """Put a spell on the stack so counterspells have something to target."""
    obj = new_object(game.state, "t_bear", owner=1, zone=Zone.HAND)
    game.state.players[1].hand.append(obj.oid)
    push_spell(game.state, obj.oid, 1)


def drive(game: Game, limit: int = 60) -> None:
    """Answer every decision with the first legal action until the game settles."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or game.over:
            return
        if decision.kind is DecisionKind.PRIORITY:
            return
        game.apply(_answer(game, decision))


def _answer(game: Game, decision: PendingDecision):
    actions = game.legal_actions()
    assert actions, f"no legal action for {decision.kind.value}"

    # Decline combat: this test is about the card, and letting the sandbox attack
    # would fold combat damage and creature deaths into every card's outcome.
    if decision.kind in (DecisionKind.DECLARE_ATTACKERS, DecisionKind.DECLARE_BLOCKERS):
        for action in actions:
            if action.kind is ActionKind.FINISH_DECLARATION:
                return action

    # Otherwise make a real choice, so optional effects actually get exercised.
    for action in actions:
        if action.kind in (ActionKind.CHOOSE, ActionKind.YES):
            return action
    return actions[0]


def find_play(game: Game, card_id: str):
    for action in game.legal_actions():
        if action.kind not in (ActionKind.CAST, ActionKind.PLAY_LAND):
            continue
        obj = game.state.objects.get(action.source)
        if obj is not None and obj.def_id == card_id and obj.zone is Zone.HAND:
            return action
    return None


class TestEveryCardIsPlayable:
    def test_card_can_be_played_and_resolves(self, registry, card_id, expectations):
        card = registry.get(card_id)
        game = build_sandbox(registry, card_id)

        needs_spell_target = any(spec.kind == "spell" for spec in card.targets)
        if needs_spell_target:
            add_dummy_spell(game)
        game._advance()

        action = find_play(game, card_id)
        assert action is not None, (
            f"{card_id} ({card.name}) is not playable in the sandbox; "
            f"offered: {[a.label for a in game.legal_actions()][:10]}"
        )

        oid = action.source
        game.apply(action)
        drive(game)

        obj = game.state.objects.get(oid)
        assert obj is not None, f"{card_id} vanished entirely"
        assert obj.zone is not Zone.STACK, f"{card_id} never left the stack"

        if card.is_permanent:
            assert obj.zone is Zone.BATTLEFIELD, (
                f"{card_id} is a permanent but ended in {obj.zone.value}"
            )
        else:
            assert obj.zone is Zone.GRAVEYARD, (
                f"{card_id} is a spell but ended in {obj.zone.value}"
            )

        expectation = expectations.get(card_id)
        if expectation:
            _check_expectation(game, card_id, oid, expectation)


class TestActivatedAbilities:
    def test_every_activated_ability_can_be_used(self, registry, card_id):
        """Put the card onto the battlefield and activate each non-mana ability."""
        card = registry.get(card_id)
        activated = [
            a for a in card.abilities if a.is_activated and not a.is_mana_ability
        ]
        if not activated:
            pytest.skip(f"{card_id} has no activated abilities")

        for ability in activated:
            game = build_sandbox(registry, card_id, in_hand=False)
            game.state.battlefield.append(
                new_object(game.state, card_id, owner=0, zone=Zone.BATTLEFIELD).oid
            )
            for oid in game.state.battlefield:
                game.state.objects[oid].entered_turn = 0
            game.state.bump_chars()
            game._advance()

            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.ACTIVATE
                    and a.ability_index == ability.index
                    and game.state.objects[a.source].def_id == card_id
                ),
                None,
            )
            assert action is not None, (
                f"{card_id} ability {ability.index} ({ability.text!r}) is not activatable; "
                f"offered: {[a.label for a in game.legal_actions()][:10]}"
            )
            game.apply(action)
            drive(game)


class TestManaAbilities:
    def test_mana_abilities_produce_mana(self, registry, card_id):
        card = registry.get(card_id)
        mana_abilities = card.mana_abilities()
        if not mana_abilities:
            pytest.skip(f"{card_id} produces no mana")
        for ability in mana_abilities:
            assert ability.mana_options, f"{card_id} ability {ability.index} yields nothing"
            for option in ability.mana_options:
                assert sum(option) > 0


def _check_expectation(game: Game, card_id: str, oid: int, expectation: dict) -> None:
    """Assert a per-card expectation from ``expectations.json``."""
    state = game.state
    if "life" in expectation:
        for pid, value in expectation["life"].items():
            assert state.players[int(pid)].life == value, (
                f"{card_id}: player {pid} life is {state.players[int(pid)].life}, "
                f"expected {value}"
            )
    if "hand_size" in expectation:
        for pid, value in expectation["hand_size"].items():
            assert len(state.players[int(pid)].hand) == value, (
                f"{card_id}: player {pid} hand is {len(state.players[int(pid)].hand)}, "
                f"expected {value}"
            )
    if "counters" in expectation:
        kind, value = expectation["counters"]["kind"], expectation["counters"]["amount"]
        assert state.objects[oid].counter(kind) == value
    if "tokens" in expectation:
        token_id, count = expectation["tokens"]["id"], expectation["tokens"]["count"]
        made = [o for o in state.battlefield_objects(0) if state.objects[o.oid].def_id == token_id]
        assert len(made) == count, f"{card_id}: expected {count} {token_id}, got {len(made)}"
    if "battlefield_count" in expectation:
        assert len(state.battlefield_objects(0)) == expectation["battlefield_count"]

