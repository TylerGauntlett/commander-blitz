"""A reduction that sums mana values.

    "This spell costs {X} less to cast, where X is the **total** mana value of
    historic permanents you control."        -- Excalibur, Sword of Eden

`cost_reduction` took exactly one of `count`, `total_power`, `amount` and
`greatest_mana_value`, and not one of them says this:

* `greatest_mana_value` reads mana values and takes a **maximum**, and its own
  docstring says it is a separate key precisely so that it does not sum. Two
  permanents of mana value 3 and 5 are 5 there and 8 here.
* `total_power` sums, but sums *power*, which the board this card is printed for
  mostly has none of -- a Saga and a Signet are power 0 and mana value 3 and 2.
* `count` gives 1 per permanent and `amount` is a flat number needing a
  condition.

So it is the mana-value analogue of `total_power`, and it reads the **printed**
mana value off the card, the same face `greatest_mana_value` reads: a mana value
is a property of a card, and nothing in the characteristics pipeline writes one.

The maximum-shaped control card is the point of this file. Both cards are the
same cost with the same filter, and the only thing that separates them is the
key -- so a `total_mana_value` that quietly took a maximum, or a
`greatest_mana_value` that started summing, fails here rather than on a board.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.engine.costs import cost_reduction
from automtg.engine.errors import DslError
from tests.conftest import cost_reduction_probe, two_seat_board

SUM = "t_tmv_sum"  # total mana value of artifacts you control
MAX = "t_tmv_max"  # the same card, greatest mana value
TWO = "t_tmv_two"  # mana value 2
FIVE = "t_tmv_five"  # mana value 5


class TestItSums:
    def test_one_artifact(self, registry, builder):
        game = two_seat_board(builder, mine=[TWO])
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 2

    def test_two_artifacts_add_up(self, registry, builder):
        game = two_seat_board(builder, mine=[TWO, FIVE])
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 7

    def test_copies_of_one_artifact_add_up(self, registry, builder):
        """A sum counts each permanent, where a maximum cannot tell one from
        three."""
        game = two_seat_board(builder, mine=[TWO, TWO, TWO])
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 6

    def test_an_empty_board_reduces_nothing(self, registry, builder):
        game = two_seat_board(builder)
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 0


class TestItIsNotAMaximum:
    """The control, and the whole reason this is a separate key."""

    def test_the_same_board_read_as_a_maximum(self, registry, builder):
        game = two_seat_board(builder, mine=[TWO, FIVE])
        assert cost_reduction(game.state, 0, registry.get(MAX)) == 5

    def test_and_as_a_sum(self, registry, builder):
        game = two_seat_board(builder, mine=[TWO, FIVE])
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 7

    def test_a_maximum_cannot_count_copies(self, registry, builder):
        game = two_seat_board(builder, mine=[TWO, TWO, TWO])
        assert cost_reduction(game.state, 0, registry.get(MAX)) == 2


class TestTheFilterStillApplies:
    def test_an_opponents_artifacts_do_not_count(self, registry, builder):
        """"artifacts **you control**" -- the filter is the same one every
        other reduction shape reads, so this is checking the wiring rather than
        the filter."""
        game = two_seat_board(builder, mine=[TWO], theirs=[FIVE, FIVE])
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 2

    def test_a_noncreature_nonartifact_does_not(self, registry, builder):
        game = two_seat_board(builder, mine=[TWO, "forest"])
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 2


class TestTheLoaderPlacesIt:
    def test_it_loads(self):
        compile_card(cost_reduction_probe({"total_mana_value": {"controller": "you"}}))

    def test_it_needs_a_filter(self):
        with pytest.raises(DslError, match="needs a filter"):
            compile_card(cost_reduction_probe({"total_mana_value": 3}))

    def test_it_may_not_be_written_beside_another_shape(self):
        """Two would be paid at whichever the code read first, which is not
        something a printed line says."""
        with pytest.raises(DslError, match="exactly one"):
            compile_card(
                cost_reduction_probe(
                    {
                        "total_mana_value": {"controller": "you"},
                        "greatest_mana_value": {"controller": "you"},
                    }
                )
            )

    def test_its_filter_may_only_read_printed_characteristics(self):
        with pytest.raises(DslError, match="unsupported filter keys"):
            compile_card(
                cost_reduction_probe({"total_mana_value": {"controller": "you", "nonsense": 1}})
            )
