"""A reduction that counts mana values, at a price per value.

    "This spell costs {2} less to cast for each **different** mana value among
    instant and sorcery cards in your graveyard."  -- Eris, Roar of the Storm

Two things the reduction language could not say. `count` counts cards, so two
instants of mana value 2 would be two units where the card says one; the head
`distinct_mana_values` counts the set of printed mana values instead. And every
counting head gave {1} a unit; `each` is the per-unit price beside it, so a
unit here is {2}.

The control is Eris's own filter read through `count` -- the same graveyard,
the same key the card would have been written with -- because a distinct count
that quietly counted cards would pass every board where the values differ.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.engine.cost_reduction import reduction_amount
from commanderblitz.engine.errors import DslError
from tests.conftest import cost_reduction_probe

BOLT = "lightning_bolt"  # instant, mana value 1
VISIONS = "serum_visions"  # sorcery, mana value 1
COUNTERSPELL = "counterspell"  # instant, mana value 2
CANCEL = "cancel"  # instant, mana value 3
BEARS = "grizzly_bears"  # creature, mana value 2

SPELLS = {"zone": "graveyard", "owner": "you", "any_types": ["Instant", "Sorcery"]}
ERIS = {"distinct_mana_values": SPELLS, "each": 2}


def graveyard(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .graveyard(0, list(mine))
        .graveyard(1, list(theirs))
        .build(advance=False)
    )


class TestItCountsValuesNotCards:
    def test_three_values_are_three_units(self, builder):
        game = graveyard(builder, [BOLT, COUNTERSPELL, CANCEL])
        assert reduction_amount(game.state, 0, {"distinct_mana_values": SPELLS}) == 3

    def test_two_cards_of_one_value_are_one_unit(self, builder):
        """Lightning Bolt and Serum Visions are both mana value 1."""
        game = graveyard(builder, [BOLT, VISIONS])
        assert reduction_amount(game.state, 0, {"distinct_mana_values": SPELLS}) == 1

    def test_count_would_have_read_two(self, builder):
        """The control: the key the card would otherwise be written with."""
        game = graveyard(builder, [BOLT, VISIONS])
        assert reduction_amount(game.state, 0, {"count": SPELLS}) == 2

    def test_the_filter_still_applies(self, builder):
        """A creature card's mana value is not "among instant and sorcery
        cards", and an opponent's graveyard is not yours."""
        game = graveyard(builder, [BOLT, BEARS], theirs=[COUNTERSPELL])
        assert reduction_amount(game.state, 0, {"distinct_mana_values": SPELLS}) == 1

    def test_an_empty_graveyard_reduces_nothing(self, builder):
        game = graveyard(builder)
        assert reduction_amount(game.state, 0, ERIS) == 0


class TestAnyTypesIsRead:
    def test_a_creature_card_is_not_an_instant_or_sorcery(self, builder):
        """`any_types` was accepted on a reduction filter and read by nothing,
        so Furygale Flocking's "for each instant and sorcery card in your
        graveyard" counted every card there."""
        game = graveyard(builder, [BOLT, BEARS, BEARS])
        assert reduction_amount(game.state, 0, {"count": SPELLS}) == 1


class TestEachIsThePricePerUnit:
    def test_two_a_value(self, builder):
        game = graveyard(builder, [BOLT, VISIONS, COUNTERSPELL, CANCEL])
        assert reduction_amount(game.state, 0, ERIS) == 6

    def test_it_multiplies_a_plain_count_too(self, builder):
        game = graveyard(builder, [BOLT, VISIONS])
        assert reduction_amount(game.state, 0, {"count": SPELLS, "each": 2}) == 4


class TestTheLoaderPlacesIt:
    def test_it_loads(self):
        compile_card(cost_reduction_probe(ERIS))

    def test_it_needs_a_filter(self):
        with pytest.raises(DslError, match="needs a filter"):
            compile_card(cost_reduction_probe({"distinct_mana_values": 3}))

    def test_each_needs_a_head_that_counts(self):
        """Beside a sum of power, "{2} less for each" multiplies a total no
        printed card multiplies."""
        with pytest.raises(DslError, match="only beside a head that counts"):
            compile_card(
                cost_reduction_probe({"total_power": {"controller": "you"}, "each": 2})
            )

    @pytest.mark.parametrize("each", [1, 0, "2", True])
    def test_each_is_an_integer_of_two_or_more(self, each):
        """One unit is already {1}; `each: 1` is the head written the long way."""
        with pytest.raises(DslError, match="2 or more"):
            compile_card(cost_reduction_probe({"count": SPELLS, "each": each}))
