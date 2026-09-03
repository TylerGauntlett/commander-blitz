""""This ability costs {1} less to activate for each **legendary** creature you control."

    Takenuma, Abandoned Mire — "Channel — {3}{B}, Discard this card: … This
    ability costs {1} less to activate for each legendary creature you control."

Rule 601.2f prices a cost by what the filter actually names, and the filter here
named a supertype. `costs._reduction_matches` read six keys — `zone`,
`controller`, `owner`, `is_commander`, `types`, `subtypes` — while
`loader._validate_cost_reduction` accepted the whole of `STATIC_FILTER_KEYS`, so
fourteen more validated at load time and were dropped at pricing time.

That gap is the worst shape a bug can have here: an ignored narrowing key makes
the filter *wider*, so the ability is cheaper than it prints, and nothing fails.
Takenuma with three ordinary creatures and no legend would have channelled for
{B} instead of {3}{B}, on a card that loads clean and reads right.

The three keys still absent — `attached`, `paired`, `paired_with_source` — are
refused by the loader instead. Each names a relation to one particular permanent
and a reduction counts a board, so implementing them would be inventing a
sentence no card prints; refusing them is what stops the silent-drop from coming
back under a different key.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, _validate_cost_reduction
from automtg.engine.costs import ability_mana
from tests.conftest import oids_of

LEGEND_SCALER = "t_legend_scaling_ability"  # {5}, {T}: draw; {1} less per legendary creature
FLYING_SCALER = "t_flying_scaling_ability"  # {5}, {T}: draw; {1} less per flier
LEGEND = "t_legend"  # Legendary Creature — Human 2/2
OTHER_LEGEND = "t_commander"  # Legendary Creature — Serpent; a *different* legend
BEAR = "t_bear"  # Creature — Bear 2/2, no supertype
FLIER = "t_flier"


def board(builder, scaler, *others, opponent=()):
    return (
        builder(players=2)
        .battlefield(0, [scaler, *(["swamp"] * 5), *others])
        .battlefield(1, list(opponent))
        .library(0, ["swamp"] * 20)
        .build()
    )


def price(game, scaler) -> int:
    oid = oids_of(game, scaler)[0]
    cost = game.state.card(oid).abilities[0].cost
    return ability_mana(game.state, 0, cost).total


class TestASupertypeNarrowsTheCount:
    def test_no_creatures_at_all_is_the_printed_cost(self, builder):
        assert price(board(builder, LEGEND_SCALER), LEGEND_SCALER) == 5

    def test_each_legendary_creature_takes_one_off(self, builder):
        assert price(board(builder, LEGEND_SCALER, LEGEND), LEGEND_SCALER) == 4

    def test_two_of_them_take_two_off(self, builder):
        """Two *differently named* legends, because 704.5j would eat a pair."""
        game = board(builder, LEGEND_SCALER, LEGEND, OTHER_LEGEND)
        assert price(game, LEGEND_SCALER) == 3

    def test_an_ordinary_creature_takes_nothing_off(self, builder):
        """The regression. Before the filter read `supertypes` this was {4}."""
        assert price(board(builder, LEGEND_SCALER, BEAR), LEGEND_SCALER) == 5

    def test_a_board_of_both_counts_only_the_legends(self, builder):
        game = board(builder, LEGEND_SCALER, LEGEND, BEAR, BEAR)
        assert price(game, LEGEND_SCALER) == 4

    def test_an_opponents_legend_does_not_count(self, builder):
        """`controller` still narrows it -- the new key adds to the old ones."""
        game = board(builder, LEGEND_SCALER, opponent=[LEGEND])
        assert price(game, LEGEND_SCALER) == 5


class TestTheOtherKeysAreReadToo:
    """One more key, chosen because it is read off `chars` rather than the card."""

    def test_a_creature_without_the_keyword_takes_nothing_off(self, builder):
        assert price(board(builder, FLYING_SCALER, BEAR), FLYING_SCALER) == 5

    def test_a_creature_with_it_takes_one_off(self, builder):
        assert price(board(builder, FLYING_SCALER, FLIER), FLYING_SCALER) == 4


class TestTheRelationalKeysAreRefused:
    @pytest.mark.parametrize("key", ["attached", "paired", "paired_with_source"])
    def test_the_loader_says_so_rather_than_ignoring_them(self, key):
        with pytest.raises(DslError, match="counts a board"):
            _validate_cost_reduction({"count": {key: True}}, "t.cost.mana_reduction")

    def test_a_key_it_does_read_still_validates(self):
        _validate_cost_reduction(
            {"count": {"controller": "you", "supertypes": ["Legendary"]}},
            "t.cost.mana_reduction",
        )
