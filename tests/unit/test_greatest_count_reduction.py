"""A reduction that maximises a per-player tally instead of summing one pool.

    "This spell costs {X} less to cast, where X is the greatest number of
    artifacts **an opponent** controls."          -- Cavern-Hoard Dragon

Rule 601.2f prices a spell once, off the board as it stands, and this card's X
is the *greatest* of several numbers rather than their total. `count` is the
near miss and is a **sum**: `cost_reduction.reduction_amount` answers it with
``sum(1 for _ in _reduction_matches(...))`` over one flat pool, and a reduction
filter's ``controller: "opponent"`` names every opponent at once -- the
selector language can say "not you" but not "them, separately", which is what
`effects.values._counts_per_player` says in its own docstring about the
effect-side `max_count_of` that has the arithmetic and cannot be reached from a
price.

**Every test here is at a pod, and that is the whole point of the file.** At two
players the sum and the maximum are the same number, because there is exactly
one opponent to group -- so a Cavern-Hoard Dragon encoded with `count` prices
itself correctly in the two-player authoring sandbox, passes all six gates, and
ships. It is only at three opponents holding two artifacts each that the two
readings part company: {6} from the sum, {2} from the printed card. The
`t_gc_sum` control card is the identical price written with `count`, so the
divergence is measured here rather than argued.

`greatest_mana_value` is the same relation one axis over -- a maximum beside
`total_mana_value`'s sum -- and it is a separate key for the same reason.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import cost_reduction
from automtg.engine.errors import DslError

GREATEST = "t_gc_greatest"  # greatest number of artifacts AN OPPONENT controls
SUM = "t_gc_sum"  # the same filter, read as a flat `count` -- the control
MINE = "t_gc_mine"  # greatest_count with the default "you" filter
BAUBLE = "t_gc_bauble"  # a plain artifact
OGRE = "t_gc_ogre"  # a plain creature, so the filter has something to reject


def pod(builder, *hands):
    """A table of ``len(hands)`` seats, seat 0 being the caster."""
    game = builder(players=len(hands))
    for pid, cards in enumerate(hands):
        game = game.battlefield(pid, list(cards))
    return game.build()


class TestItTakesTheGreatestSeatNotTheTable:
    """The claim the card makes, and the one a two-player board cannot check."""

    def test_three_opponents_with_two_each_discount_two(self, registry, builder):
        """The printed number is {2}. A sum would say {6}."""
        game = pod(
            builder,
            [],
            [BAUBLE, BAUBLE],
            [BAUBLE, BAUBLE],
            [BAUBLE, BAUBLE],
        )
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 2

    def test_the_same_board_summed_is_the_bug_this_key_exists_for(
        self, registry, builder
    ):
        """The control card, so the divergence is a measurement."""
        game = pod(
            builder,
            [],
            [BAUBLE, BAUBLE],
            [BAUBLE, BAUBLE],
            [BAUBLE, BAUBLE],
        )
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 6

    def test_the_richest_opponent_wins_not_the_busiest_table(self, registry, builder):
        """One seat with three, two seats with one each: {3}, not {5}."""
        game = pod(builder, [], [BAUBLE, BAUBLE, BAUBLE], [BAUBLE], [BAUBLE])
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 3
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 5

    def test_a_lone_hoarder_among_empty_seats(self, registry, builder):
        game = pod(builder, [], [], [BAUBLE, BAUBLE, BAUBLE, BAUBLE], [])
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 4

    def test_at_two_players_the_two_readings_agree(self, registry, builder):
        """Why the wrong encoding is invisible in the authoring sandbox.

        Not an accident to be fixed: with one opponent there is one group, so
        the maximum of it *is* the sum of it. This test is here to pin the
        coincidence, so the pod tests above are understood as the ones that
        separate the keys.
        """
        game = pod(builder, [], [BAUBLE, BAUBLE])
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 2
        assert cost_reduction(game.state, 0, registry.get(SUM)) == 2


class TestTheBoundaries:
    def test_no_opponent_has_an_artifact(self, registry, builder):
        """A maximum over nothing is no discount, and the spell costs what it
        prints -- the same `default=0` reading `greatest_mana_value` takes."""
        game = pod(builder, [BAUBLE, BAUBLE, BAUBLE], [OGRE], [], [OGRE])
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 0

    def test_an_empty_table_discounts_nothing(self, registry, builder):
        game = pod(builder, [], [], [], [])
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 0

    def test_your_own_hoard_is_not_an_opponents(self, registry, builder):
        """"an **opponent** controls" -- your twelve artifacts are worth
        nothing, and the one across the table is worth {1}."""
        game = pod(
            builder,
            [BAUBLE] * 12,
            [BAUBLE],
            [],
            [],
        )
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 1

    def test_the_seat_is_never_below_zero(self, registry, builder):
        """Nothing here can go negative, but `cost_reduction` clamps anyway and
        a discount larger than the printed generic cost is still just a
        discount -- see `costs.cost_reduction`."""
        game = pod(builder, [], [BAUBLE] * 20, [], [])
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 20


class TestItGroupsTheFiltersPoolAndNotTheTable:
    """The maximum is over the seats the *filter* admits, not over every seat.

    That is what makes the key composable rather than a second spelling of
    "opponent": the grouping and the filtering are separate steps, so a filter
    that admits one player has one group.
    """

    def test_a_you_filter_collapses_to_a_plain_count(self, registry, builder):
        game = pod(builder, [BAUBLE, BAUBLE, BAUBLE], [BAUBLE] * 7, [], [])
        assert cost_reduction(game.state, 0, registry.get(MINE)) == 3

    def test_and_reads_zero_off_an_empty_board_of_your_own(self, registry, builder):
        game = pod(builder, [OGRE], [BAUBLE] * 7, [], [])
        assert cost_reduction(game.state, 0, registry.get(MINE)) == 0

    def test_a_noncreature_filter_still_applies_per_seat(self, registry, builder):
        """The creatures are ignored before the tally, not after it: seat 2
        would otherwise out-count seat 1."""
        game = pod(builder, [], [BAUBLE, BAUBLE], [OGRE, OGRE, OGRE, BAUBLE], [])
        assert cost_reduction(game.state, 0, registry.get(GREATEST)) == 2


class TestTheLoaderPlacesIt:
    def _card(self, reduction):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "This spell costs {X} less to cast.",
                "mana_cost": "{9}",
                "types": ["Sorcery"],
                "cost_reduction": reduction,
                "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
            }
        )

    def test_it_loads(self):
        compile_card(self._card({"greatest_count": {"controller": "opponent"}}))

    def test_it_needs_a_filter(self):
        with pytest.raises(DslError, match="needs a filter"):
            compile_card(self._card({"greatest_count": 3}))

    def test_it_may_not_be_written_beside_another_shape(self):
        with pytest.raises(DslError, match="exactly one"):
            compile_card(
                self._card(
                    {
                        "greatest_count": {"controller": "opponent"},
                        "count": {"controller": "opponent"},
                    }
                )
            )

    def test_its_filter_may_only_read_printed_characteristics(self):
        with pytest.raises(DslError, match="unsupported filter keys"):
            compile_card(
                self._card({"greatest_count": {"controller": "opponent", "nonsense": 1}})
            )

    def test_a_misspelled_type_is_a_load_error(self):
        """A reduction that matches nothing is a spell quietly priced at what
        it prints, so the guard every reduction filter gets applies here too."""
        with pytest.raises(DslError):
            compile_card(
                self._card(
                    {"greatest_count": {"controller": "opponent", "types": ["Artefact"]}}
                )
            )
