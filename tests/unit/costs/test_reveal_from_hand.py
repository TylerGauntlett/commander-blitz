"""Reveal from hand -- "reveal a Dinosaur card from your hand or pay {1}".

Thunderherd Migration: "As an additional cost to cast this spell, reveal a
Dinosaur card from your hand or pay {1}." The Ixalan and Lorwyn cycles print the
same cost for Pirates, Vampires, Kithkin, Merfolk, Goblins and Giants.

The nearest spelling before this was `behold`, and it is a cheaper card than the
printed one: behold also accepts a matching permanent you control, so a
Dinosaur already on the battlefield would pay a cost that names only the hand.
The reveal is the whole price -- the card stays in hand and every opponent
learns it -- and 601.2a still holds: a spell is on the stack before its costs
are paid, so a Dinosaur with this cost can never reveal itself.

`t_reveal_migration` is the "or pay {1}" branch on an instant, and
`t_reveal_buccaneer` a Dinosaur whose mandatory cost must find a *different*
Dinosaur.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, hand_ids

RAPTOR = "t_reveal_raptor"
MIGRATION = "t_reveal_migration"
BUCCANEER = "t_reveal_buccaneer"
BEAR = "t_bear"


def cast_lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def board(builder, card_id: str, *, mine=(), hand=(), lands: int = 4):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * lands + list(mine))
        .hand(0, [card_id, *hand])
        .library(0, ["forest"] * 20)
        .build()
    )


def pay(game, action) -> None:
    game.apply(action)
    for _ in range(50):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.PRIORITY:
            return
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
        else:
            game.apply(_default_answer(game, decision))


def reveals(game) -> list[list[str]]:
    return [e.data["cards"] for e in game.state.events if e.type == "reveal"]


class TestWhatPaysIt:
    def test_with_no_dinosaur_only_the_pay_branch_is_offered(self, builder):
        game = board(builder, MIGRATION, hand=[BEAR])
        assert sorted(a.additional_choice for a in cast_lines(game, MIGRATION)) == [1]

    def test_a_dinosaur_in_hand_opens_the_reveal_branch(self, builder):
        game = board(builder, MIGRATION, hand=[RAPTOR])
        assert sorted(a.additional_choice for a in cast_lines(game, MIGRATION)) == [0, 1]

    def test_a_dinosaur_on_the_battlefield_does_not_pay_it(self, builder):
        """The difference from behold: the printed cost names only the hand."""
        game = board(builder, MIGRATION, mine=[RAPTOR], hand=[BEAR])
        assert sorted(a.additional_choice for a in cast_lines(game, MIGRATION)) == [1]

    def test_a_dinosaur_spell_cannot_reveal_itself(self, builder):
        """601.2a: it is on the stack, not in hand, when the cost is paid."""
        alone = board(builder, BUCCANEER, lands=1)
        assert cast_lines(alone, BUCCANEER) == []
        paired = board(builder, BUCCANEER, lands=1, hand=[RAPTOR])
        assert len(cast_lines(paired, BUCCANEER)) == 1


class TestPayingIt:
    def test_revealing_costs_no_mana_shows_the_card_and_keeps_it(self, builder):
        game = board(builder, MIGRATION, hand=[RAPTOR], lands=1)
        # One Forest: {G} alone. The {1} branch is not affordable, revealing is.
        assert sorted(a.additional_choice for a in cast_lines(game, MIGRATION)) == [0]
        pay(game, cast_lines(game, MIGRATION)[0])
        graveyard = [game.state.objects[o].def_id for o in game.state.players[0].graveyard]
        assert graveyard == [MIGRATION], "cast and resolved on {G} alone"
        assert reveals(game) == [[RAPTOR]]
        assert RAPTOR in hand_ids(game)

    def test_paying_the_mana_reveals_nothing(self, builder):
        game = board(builder, MIGRATION, hand=[RAPTOR])
        pay(game, next(a for a in cast_lines(game, MIGRATION) if a.additional_choice == 1))
        assert reveals(game) == []


class TestTheLoaderRefuses:
    def card(self, cost):
        return CardModel.model_validate(
            {
                "id": "t_bad_reveal",
                "name": "Test Bad Reveal",
                "oracle_text": "Draw a card.",
                "mana_cost": "{1}{G}",
                "types": ["Sorcery"],
                "additional_cost": {"reveal_from_hand": cost},
                "spell_effects": [{"op": "draw", "player": "you"}],
            }
        )

    @pytest.mark.parametrize(
        "cost",
        [{}, {"subtypes": ["Dinosaur"], "count": 0}, {"subtypes": ["Dinosaur"], "count": "x"}],
    )
    def test_a_malformed_selector(self, cost):
        with pytest.raises(DslError):
            compile_card(self.card(cost), source="t")

    @pytest.mark.parametrize("key", ["zone", "controller"])
    def test_a_zone_or_controller_is_implied(self, key):
        with pytest.raises(DslError, match="implied"):
            compile_card(self.card({"subtypes": ["Dinosaur"], key: "battlefield"}), source="t")
