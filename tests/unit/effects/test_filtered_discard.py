"""Discard narrowed to a kind of card -- "discard any number of **land** cards".

    Nantuko Cultivator — "When this creature enters, you may discard any number
    of land cards. Put that many +1/+1 counters on this creature and draw that
    many cards."

Rule 701.9a: to discard is to move a card from its owner's hand to their
graveyard, and the effect names which cards qualify. Without a filter the
`discard` op offered the whole hand, so Cultivator could pitch a spell and
count it toward "that many": a different card. The cost route is no better --
`discard_selector` fixes the number before anything resolves -- and a loop of
one-land discards is as many discard events as lands, which a "one or more"
trigger (603.2c) hears once per land.

So `selector` narrows the pool the player chooses from, the ceiling is the
matching cards rather than the hand, the chosen cards go as **one** event, and
`as` records exactly them. `t_exact_land_pitch` is the exact-count
counterfactual: it discards as many matching cards as it can, never a nonland
one. The loader refuses a `zone` (the hand is the only one), an empty filter,
and the filter beside `whole_hand` or `random`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError

PITCH = "t_land_pitch"
EXACT = "t_exact_land_pitch"
DOOM = "t_land_discard_drainer"
START = 40


def board(builder, card_id: str, hand=("forest", "mountain", "sol_ring"), watcher=()):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + list(watcher))
        .hand(0, [card_id, *hand])
        .library(0, ["plains"] * 20)
        .build()
    )
    cast(game, card_id)
    for _ in range(20):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
            break
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
    return game


def cast(game, card_id: str) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        )
    )


def offered(game) -> list[str]:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
    return sorted(game.state.card(opt.value).id for opt in decision.options)


def choose_all_then_finish(game, take: int) -> None:
    """Answer the discard with ``take`` cards, then let the spell finish resolving."""
    for _ in range(40):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
            actions = game.legal_actions()
            choose = [a for a in actions if a.kind is ActionKind.CHOOSE]
            if take > 0 and choose:
                take -= 1
                game.apply(choose[0])
            else:
                game.apply(next(a for a in actions if a.kind is ActionKind.FINISH_DECLARATION))
            continue
        if not game.state.stack:
            return
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))


def graveyard_ids(game) -> list[str]:
    return sorted(game.state.card(oid).id for oid in game.state.players[0].graveyard)


class TestOnlyTheMatchingCardsAreOffered:
    def test_the_nonland_card_is_not_a_choice(self, builder):
        game = board(builder, PITCH)
        assert offered(game) == ["forest", "mountain"]

    def test_none_is_a_legal_answer(self, builder):
        """"Any number" is zero up: declining is offered."""
        game = board(builder, PITCH)
        assert any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


class TestThatMany:
    def test_two_lands_discarded_draw_two(self, builder):
        game = board(builder, PITCH)
        library = len(game.state.players[0].library)
        choose_all_then_finish(game, 2)
        assert len(game.state.players[0].library) == library - 2
        assert graveyard_ids(game) == sorted(["forest", "mountain", PITCH])
        hand = [game.state.card(oid).id for oid in game.state.players[0].hand]
        assert "sol_ring" in hand

    def test_declining_draws_nothing(self, builder):
        game = board(builder, PITCH)
        library = len(game.state.players[0].library)
        choose_all_then_finish(game, 0)
        assert len(game.state.players[0].library) == library
        assert graveyard_ids(game) == [PITCH]

    def test_a_hand_with_no_land_asks_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4)
            .hand(0, [PITCH, "sol_ring"])
            .library(0, ["plains"] * 20)
            .build()
        )
        cast(game, PITCH)
        choose_all_then_finish(game, 0)
        assert graveyard_ids(game) == [PITCH]
        assert [game.state.card(o).id for o in game.state.players[0].hand] == ["sol_ring"]


class TestOneEvent:
    def test_a_one_or_more_trigger_hears_two_lands_once(self, builder):
        """603.2c: the lands chosen together are one discard event."""
        game = board(builder, PITCH, watcher=(DOOM,))
        choose_all_then_finish(game, 2)
        assert game.state.players[1].life == START - 2


class TestTheExactCount:
    def test_it_takes_lands_and_never_the_spell(self, builder):
        """Only one land in hand: it discards that one, and Sol Ring stays."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4)
            .hand(0, [EXACT, "forest", "sol_ring"])
            .library(0, ["plains"] * 20)
            .build()
        )
        cast(game, EXACT)
        choose_all_then_finish(game, 0)
        assert graveyard_ids(game) == sorted([EXACT, "forest"])
        sol = next(
            o for o in game.state.objects.values() if game.state.card_of(o).id == "sol_ring"
        )
        assert sol.zone is Zone.HAND


class TestTheLoaderRefuses:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {"op": "discard", "player": "you", "amount": {"const": 1}, **extra}
                ],
            }
        )

    def test_the_filter_loads(self):
        compile_card(self._card(selector={"types": ["Land"]}, up_to=True))

    def test_a_zone(self):
        with pytest.raises(DslError, match="drop 'zone'"):
            compile_card(self._card(selector={"types": ["Land"], "zone": "graveyard"}))

    def test_an_empty_filter(self):
        with pytest.raises(DslError, match="non-empty filter"):
            compile_card(self._card(selector={}))

    def test_beside_random(self):
        with pytest.raises(DslError, match="whole_hand"):
            compile_card(self._card(selector={"types": ["Land"]}, random=True))
