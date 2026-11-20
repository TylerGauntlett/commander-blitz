"""Boast abilities as a class a card can name.

    "Boast abilities you activate cost {1} less to activate for each Dragon
    you control."                                  -- Dragonkin Berserker

702.142a: a boast ability is an activated ability that may be activated only
if its creature attacked this turn and only once each turn. It compiles to an
ordinary activated ability with `once_each_turn` and an attacked-this-turn
`condition`, and nothing told it apart from any other ability printing the
same restriction. So the card declares it with `is_boast`, as an equip ability
declares `is_equip`, and the loader holds the declaration to the shape: an
activated ability, printing the word, once each turn, only after attacking.

`t_lookalike` is the near miss: the same cost and restriction without the
word, which `affects_abilities: {"boast": true}` must not reach.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.vocabulary import BOAST_CONDITION
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import ability_mana
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, two_seat_board

PATRON = "t_boast_patron"  # boast abilities you activate cost {1} less per Dragon
BOASTER = "t_boaster"  # Boast -- {4}{R}
LOOKALIKE = "t_lookalike"  # {4}{R}, the same restriction, no word
DRAGON = "t_boast_dragon"


def price(game, card_id: str, pid: int = 0) -> int:
    """The generic half of what this creature's one ability costs ``pid`` now."""
    oid = only_oid(game, card_id)
    ability = game.state.card_of(game.state.objects[oid]).abilities[-1]
    return ability_mana(game.state, pid, ability.cost, 0, oid, ability=ability).generic


class TestTheDiscountReachesBoastAbilities:
    def test_without_a_dragon_it_is_the_printed_cost(self, builder):
        game = two_seat_board(builder, mine=[PATRON, BOASTER])
        assert price(game, BOASTER) == 4

    def test_one_less_for_each_dragon(self, builder):
        game = two_seat_board(builder, mine=[PATRON, BOASTER, DRAGON, DRAGON])
        assert price(game, BOASTER) == 2

    def test_never_below_zero(self, builder):
        game = two_seat_board(builder, mine=[PATRON, BOASTER, *[DRAGON] * 6])
        assert price(game, BOASTER) == 0

    def test_an_opponents_dragons_do_not_count(self, builder):
        game = two_seat_board(builder, mine=[PATRON, BOASTER], theirs=[DRAGON])
        assert price(game, BOASTER) == 4


class TestOnlyBoastAbilities:
    def test_the_lookalike_is_not_discounted(self, builder):
        game = two_seat_board(builder, mine=[PATRON, LOOKALIKE, DRAGON])
        assert price(game, LOOKALIKE) == 4

    def test_an_opponents_boast_is_not_discounted(self, builder):
        """"Boast abilities **you** activate"."""
        game = two_seat_board(builder, mine=[DRAGON], theirs=[PATRON, BOASTER, DRAGON])
        assert price(game, BOASTER, pid=1) == 3
        assert price(game, BOASTER, pid=0) == 4


def boast(**extra):
    base = {
        "kind": "activated",
        "text": "Boast — {1}: You gain 1 life.",
        "is_boast": True,
        "once_each_turn": True,
        "condition": BOAST_CONDITION,
        "cost": {"mana": "{1}"},
        "effects": [{"op": "gain_life", "amount": {"const": 1}}],
    }
    base.update(extra)
    return {k: v for k, v in base.items() if v is not None}


def compile_with(ability):
    return compile_card(
        CardModel.model_validate(
            {
                "id": "t_boast_shape",
                "name": "Test Boast Shape",
                "mana_cost": "{R}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "oracle_text": ability["text"],
                "abilities": [ability],
            }
        )
    )


class TestTheDeclarationIsHeldToTheShape:
    def test_the_printed_shape_loads_and_is_marked(self):
        assert compile_with(boast()).abilities[0].is_boast

    def test_an_unmarked_ability_is_not_boast(self):
        assert not compile_with(boast(is_boast=None)).abilities[0].is_boast

    @pytest.mark.parametrize(
        "broken",
        [
            {"once_each_turn": None},
            {"condition": None},
            {"condition": {"exists": {"tapped": True, "self_only": True, "zone": "battlefield"}}},
            {"text": "{1}: You gain 1 life."},
        ],
    )
    def test_a_boast_without_the_mechanic_is_refused(self, broken):
        with pytest.raises(DslError):
            compile_with(boast(**broken))
