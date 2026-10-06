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

from automtg.cards.loader import compile_card
from automtg.cards.loader.statics import _validate_cost_reduction
from automtg.cards.schema import CardModel
from automtg.engine.costs import ability_mana, reduction_amount
from automtg.engine.errors import DslError
from tests.conftest import oids_of

LEGEND_SCALER = "t_legend_scaling_ability"  # {5}, {T}: draw; {1} less per legendary creature
FLYING_SCALER = "t_flying_scaling_ability"  # {5}, {T}: draw; {1} less per flier
LEGEND = "t_legend"  # Legendary Creature — Human 2/2
OTHER_LEGEND = "t_commander"  # Legendary Creature — Serpent; a *different* legend
BEAR = "t_bear"  # Creature — Bear 2/2, no supertype

#: "…for each legendary creature you control", spelled as the loader accepts it.
LEGENDARY_CREATURES = {
    "controller": "you",
    "types": ["Creature"],
    "supertypes": ["Legendary"],
}
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


class TestOutsideTheBattlefield:
    """A reduction may count the graveyard and the command zone, where there is
    no characteristics pipeline and the printed face answers instead. The
    Kamigawa channel legends are why the zones are reachable at all, and the
    printed-face path has to read the same keys the derived one does or the
    filter means two different things depending on where it looks."""

    def counted(self, game, filt) -> int:
        return reduction_amount(game.state, 0, {"count": filt})

    def test_a_legend_in_your_graveyard_counts_when_the_zone_says_so(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5)
            .graveyard(0, [LEGEND, BEAR])
            .build()
        )
        filt = dict(LEGENDARY_CREATURES, zone="graveyard")
        assert self.counted(game, filt) == 1, "the bear is in there too"

    def test_a_legendary_commander_counts_from_the_command_zone(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5)
            .commander(0, [OTHER_LEGEND])
            .build()
        )
        filt = dict(LEGENDARY_CREATURES, zone=["battlefield", "command"])
        assert self.counted(game, filt) == 1

    def test_the_default_zone_is_still_the_battlefield(self, builder):
        """A filter naming no zone means what it always meant, so teaching the
        counter a new key cannot have widened an existing card's reach."""
        game = builder(players=2).battlefield(0, ["swamp"] * 5).graveyard(0, [LEGEND]).build()
        assert self.counted(game, LEGENDARY_CREATURES) == 0


class TestAMisspelledNameIsRefused:
    """One layer below the rest of this file, and the same failure shape.

    A misspelled type matches nothing, and a reduction that matches nothing is a
    discount of zero -- a card quietly priced at exactly what it prints, on a
    board where nothing looks wrong. A *selector* that matches nothing fails
    visibly the first time somebody plays the card; a reduction never does.

    `subtypes` is deliberately unchecked, here and in the selector language:
    creature and land types are open-ended and there is no closed set to check.
    """

    def _card(self, filt):
        return CardModel.model_validate(
            {
                "id": "t_reduction_probe",
                "name": "Reduction Probe",
                "mana_cost": "{4}{G}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "cost_reduction": {"count": filt},
            }
        )

    def test_a_misspelled_supertype(self):
        filt = {"controller": "you", "types": ["Creature"], "supertypes": ["Legendarry"]}
        with pytest.raises(DslError, match="unknown supertype"):
            compile_card(self._card(filt))

    def test_a_misspelled_type(self):
        with pytest.raises(DslError, match="unknown type"):
            compile_card(self._card({"controller": "you", "types": ["Creatures"]}))

    def test_the_real_spelling_loads(self):
        compile_card(self._card(LEGENDARY_CREATURES))


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
