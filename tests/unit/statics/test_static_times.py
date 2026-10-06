"""A static's magnitude with a step bigger than one.

    "Equipped creature gets +2/+2 for each Equipment you control."
                                                        -- Swordsman's Steel

`buff` with a `count` magnitude has shipped since Crown of Gondor, and it always
stepped by exactly one. Every leaf in the static value language *measures*
something -- a board count, a life total, mana symbols -- and nothing combined
two, so a card that counts in twos could not be written at all.

**Two statics are not the alternative they look like.** A static ability carries
no `effects`, so "+2/+2 for each" split in half would have to be two *abilities*;
and the residual gate asks which printed line each ability claims, so two
abilities claiming one sentence is precisely what that gate exists to refuse.

`times` is deliberately the same spelling and the same shape as the effect-side
`times` in `effects/values.py`: a list of factors, multiplied. One word meaning
one thing in both languages. It is safe inside a static for `count`'s reason --
every factor it may contain is a pipeline input, so a magnitude built from them
cannot come to depend on another static's output.

The validator recurses, which matters: the key-difference check reads only the
outermost keys, so an effect-side leaf smuggled inside a `times` would load and
then reach `_static_value` as vocabulary it cannot evaluate.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.errors import DslError
from automtg.engine.primitives import attach
from tests.conftest import oids_of, two_seat_board

DOUBLER = "t_st_doubler"  # +2/+2 for each Equipment you control
SINGLE = "t_st_single"  # +1/+1 for each, the spelling that already worked
NESTED = "t_st_nested"  # count x count
GEAR = "t_st_gear"  # a bare Equipment, there to be counted
BEAR = "t_st_bear"  # 2/2


def equipped_power(game, steel: str) -> int:
    """Attach ``steel`` to the bear and read the bear's power."""
    bear = oids_of(game, BEAR, 0)[0]
    attach(game.state, oids_of(game, steel, 0)[0], bear)
    return chars(game.state, bear).power


class TestItMultiplies:
    def test_one_equipment_gives_two(self, builder):
        """The Steel counts itself, so one Equipment is the Steel alone."""
        game = two_seat_board(builder, [DOUBLER, BEAR], advance=False)
        assert equipped_power(game, DOUBLER) == 2 + 2

    def test_two_equipment_give_four(self, builder):
        game = two_seat_board(builder, [DOUBLER, GEAR, BEAR], advance=False)
        assert equipped_power(game, DOUBLER) == 2 + 4

    def test_three_equipment_give_six(self, builder):
        game = two_seat_board(builder, [DOUBLER, GEAR, GEAR, BEAR], advance=False)
        assert equipped_power(game, DOUBLER) == 2 + 6


class TestTheStepIsReallyTwo:
    """Kept live against the one-step spelling, so the tests above are
    measuring the multiplication and not the count."""

    def test_the_single_step_card_gives_half(self, builder):
        game = two_seat_board(builder, [SINGLE, GEAR, BEAR], advance=False)
        assert equipped_power(game, SINGLE) == 2 + 2

    def test_and_the_doubler_on_the_same_board_gives_twice_that(self, builder):
        game = two_seat_board(builder, [DOUBLER, GEAR, BEAR], advance=False)
        assert equipped_power(game, DOUBLER) == 2 + 4


class TestItIsAListOfFactors:
    def test_two_counts_multiply(self, builder):
        """Not a count with a scalar scale -- any factor may be a value.

        Three Equipment on the board, so 3 x 3.
        """
        game = two_seat_board(builder, [NESTED, GEAR, GEAR, BEAR], advance=False)
        assert equipped_power(game, NESTED) == 2 + 9

    def test_it_falls_to_zero_with_nothing_to_count(self, builder):
        """A factor of nought makes the whole product nought, rather than the
        multiplier leaking through as a flat bonus."""
        game = two_seat_board(builder, [BEAR], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        assert chars(game.state, bear).power == 2


class TestTheLoaderHoldsTheFactors:
    def _card(self, magnitude) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Equipped creature gets +2/+2 for each Equipment you control.",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "subtypes": ["Equipment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Equipped creature gets +2/+2 for each Equipment you control.",
                        "effect": "buff",
                        "affects": {"attached": True},
                        "power": magnitude,
                    }
                ],
            }
        )

    def test_a_pair_of_factors_loads(self):
        compile_card(self._card({"times": [{"count": {"types": ["Artifact"]}}, {"const": 2}]}))

    def test_a_single_factor_is_refused(self):
        """A one-element product is a `count` wearing a hat, and writing it that
        way hides which of the two the author meant."""
        with pytest.raises(DslError, match="times"):
            compile_card(self._card({"times": [{"const": 2}]}))

    def test_an_effect_side_leaf_inside_times_is_refused(self):
        """The reason the validator recurses. The outer key-difference check
        sees only `times`, so without it this would load and then reach
        `_static_value` as vocabulary it cannot evaluate."""
        with pytest.raises(DslError, match="static values"):
            compile_card(self._card({"times": [{"cards_in_hand": "you"}, {"const": 2}]}))
