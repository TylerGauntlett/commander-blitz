"""``mana_value`` in a static's ``affects`` -- "with mana value 4 or greater".

    "During your turn, each non-Equipment artifact and non-Aura enchantment you
     control with mana value 4 or greater is a 4/4 Elemental creature ..."
     -- Bello, Bard of the Brambles

A threshold over the printed mana value, which nothing in the static language
could say: `mana_cost` matches exact printed cost strings, and listing every
cost of four or more is not a finite spelling. Without it Bello animates every
artifact and enchantment, a much stronger card than the printed one.

Rule 202.3e: on the battlefield an {X} in a mana cost counts as 0, so a
permanent cast for a large X still has the small mana value its cost prints.
The comparison is the cast lock's literal shape (`{"op": ">=", "value": 4}` or
a bare number for equality), refused at load time in any other shape.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, static_probe

LORD = "t_mv_lord"
FOUR, THREE, X_ROCK = "t_mv_four", "t_mv_three", "t_mv_x"


def board(builder):
    return builder(players=2).battlefield(0, [LORD, FOUR, THREE, X_ROCK]).build()


def indestructible(game, card_id: str, pid: int = 0) -> bool:
    oid = oids_of(game, card_id, pid)[0]
    return "indestructible" in {str(k) for k in chars(game.state, oid).keywords}


class TestTheThreshold:
    def test_mana_value_four_is_reached(self, builder):
        assert indestructible(board(builder), FOUR)

    def test_mana_value_three_is_not(self, builder):
        assert not indestructible(board(builder), THREE)

    def test_x_counts_as_zero_on_the_battlefield(self, builder):
        """{X}{X}{1} is mana value 1 on the battlefield (202.3e)."""
        assert not indestructible(board(builder), X_ROCK)

    def test_an_opponents_artifact_is_not_reached(self, builder):
        game = builder(players=2).battlefield(0, [LORD]).battlefield(1, [FOUR]).build()
        assert not indestructible(game, FOUR, 1)


def probe(affects: dict) -> CardModel:
    return CardModel.model_validate(
        static_probe({"effect": "grant_keyword", "affects": affects, "keywords": ["haste"]})
    )


class TestTheLoader:
    def test_a_literal_comparison_loads(self):
        compile_card(probe({"types": ["Artifact"], "mana_value": {"op": ">=", "value": 4}}))

    def test_a_parity_loads(self):
        compile_card(probe({"types": ["Artifact"], "mana_value": {"parity": "odd"}}))

    def test_a_bare_number_loads(self):
        compile_card(probe({"types": ["Artifact"], "mana_value": 4}))

    @pytest.mark.parametrize(
        "bad",
        [{"amount": 4}, {"op": "~", "value": 4}, {"parity": "prime"}, {"op": ">=", "value": {"const": 4}}, "4", True],
    )
    def test_any_other_shape_is_refused(self, bad):
        with pytest.raises(DslError, match="mana_value"):
            compile_card(probe({"types": ["Artifact"], "mana_value": bad}))

    def test_it_is_checked_inside_a_branch(self):
        with pytest.raises(DslError, match="mana_value"):
            compile_card(
                probe({"any_of": [{"types": ["Artifact"], "mana_value": {"amount": 4}}, {"types": ["Enchantment"]}]})
            )
