""""…three or more lands with the same name" -- `most_sharing_a_name`.

    Endless Atlas -- "{2}, {T}: Draw a card. Activate only if you control three
    or more lands with the same name."

The question is how big the largest same-name group in a pool is, and the two
neighbouring leaves each answer a different one: `count` is how many objects
(five lands, any names), and `distinct` is how many different values (two
names among five lands). Three Islands and two Forests is a 3 here, a 5 to
`count` and a 2 to `distinct` -- and only the 3 is the card.

Names are read as `shares_a_name_with` reads them, off the card: nothing in the
characteristics layer renames an object. A face-down permanent has no name
(708.2a) and shares one with nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, only_oid

ATLAS = "t_msn_atlas"
LANDS = {"controller": "you", "types": ["Land"], "zone": "battlefield"}


def board(builder, lands, theirs=()):
    return (
        builder(players=2)
        .battlefield(0, [ATLAS, *lands])
        .battlefield(1, list(theirs))
        .build()
    )


def largest(game) -> int:
    ctx = EffectContext(state=game.state, controller=0)
    return evaluate_value(ctx, {"most_sharing_a_name": {"objects": LANDS}})


class TestTheValue:
    def test_it_is_the_largest_group_not_the_total(self, builder):
        game = board(builder, ["island"] * 3 + ["forest"] * 2)
        assert largest(game) == 3

    def test_different_names_are_groups_of_one(self, builder):
        game = board(builder, ["island", "forest", "plains"])
        assert largest(game) == 1

    def test_an_empty_pool_is_zero(self, builder):
        game = board(builder, [])
        assert largest(game) == 0

    def test_only_the_pool_counts(self, builder):
        """An opponent's three Swamps are not yours."""
        game = board(builder, ["island", "island"], theirs=["swamp"] * 3)
        assert largest(game) == 2


class TestTheAtlas:
    def test_two_of_a_name_is_not_enough(self, builder):
        game = board(builder, ["island"] * 2 + ["forest"] * 2)
        assert not activations(game, only_oid(game, ATLAS, 0))

    def test_three_of_a_name_is(self, builder):
        game = board(builder, ["island"] * 3 + ["forest"])
        assert activations(game, only_oid(game, ATLAS, 0))


class TestTheLoader:
    def test_an_empty_selector_is_refused(self):
        with pytest.raises(DslError, match="most_sharing_a_name"):
            validate_value({"most_sharing_a_name": {"objects": {}}}, "test")

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="most_sharing_a_name"):
            validate_value({"most_sharing_a_name": {"objects": LANDS, "of": "name"}}, "test")
