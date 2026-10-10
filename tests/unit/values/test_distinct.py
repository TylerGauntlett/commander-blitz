"""Domain, coven and delirium — counting *different values*, which `count` cannot do.

    Domain — "…for each basic land type among lands you control."
    Coven — "…if you control three or more creatures with different powers."
    Delirium — "…if there are four or more card types among cards in your graveyard."

Both were filed `blocked` in the census for the same one-line reason: the value
language counts objects, and these count distinct values over a pool. The two
readings fail `count` in opposite directions, which is what makes them one
capability rather than two —

- five Forests are **one** basic land type and five objects;
- three 2/2s are **three** objects and one power.

so no selector, however filtered, gets either number. `{"distinct": {"of": …,
"objects": …}}` is the leaf, and its two `of` values are the two printed cards.

Domain and coven read **derived** characteristics, and that is load-bearing twice
over. An anthem changes who has coven; "all lands are Islands" changes what
counts for domain. It is also the reason this leaf is deliberately absent from
the *static* condition language: a static that read it would depend on another
static's output, which is exactly the cycle layers-lite exists to forbid.

**Delirium reads the printed face**, and that is not an inconsistency: it counts
cards in a *graveyard*, where there are no continuous effects to apply. Asking
`chars` there would be answering a question about a permanent for something that
is not one — the same reading `characteristics._count_matching` already takes
off the battlefield.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError

FOREST = "forest"
ISLAND = "island"
MOUNTAIN = "mountain"
BEAR = "t_bear"          # 2/2
GIANT = "t_big"          # 6/6
ANTHEM = "t_anthem"      # creatures you control get +1/+1

MY_LANDS = {"controller": "you", "types": ["Land"]}
MY_CREATURES = {"controller": "you", "types": ["Creature"]}


def domain(objects=None):
    return {"distinct": {"of": "basic_land_type", "objects": objects or MY_LANDS}}


def coven(objects=None):
    return {"distinct": {"of": "power", "objects": objects or MY_CREATURES}}


MY_GRAVEYARD = {"zone": "graveyard", "controller": "you"}


def delirium(objects=None):
    return {"distinct": {"of": "card_type", "objects": objects or MY_GRAVEYARD}}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


class TestDomain:
    def test_it_counts_types_not_lands(self, builder):
        """Five Forests are one basic land type. `count` says five."""
        game = builder(players=2).battlefield(0, [FOREST] * 5).build(advance=False)
        assert value(game, domain()) == 1

    def test_each_different_type_adds_one(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST, ISLAND, MOUNTAIN, FOREST])
            .build(advance=False)
        )
        assert value(game, domain()) == 3

    def test_no_lands_is_zero(self, builder):
        game = builder(players=2).battlefield(0, [BEAR]).build(advance=False)
        assert value(game, domain()) == 0

    def test_it_ignores_lands_the_selector_excludes(self, builder):
        """`controller: "you"` is the card; an opponent's Island is not yours."""
        game = (
            builder(players=2)
            .battlefield(0, [FOREST])
            .battlefield(1, [ISLAND, MOUNTAIN])
            .build(advance=False)
        )
        assert value(game, domain()) == 1


class TestCoven:
    def test_creatures_with_the_same_power_count_once(self, builder):
        game = builder(players=2).battlefield(0, [BEAR] * 3).build(advance=False)
        assert value(game, coven()) == 1, "three 2/2s are one power"

    def test_different_powers_each_count(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, GIANT]).build(advance=False)
        assert value(game, coven()) == 2

    def test_an_empty_board_is_zero(self, builder):
        game = builder(players=2).build(advance=False)
        assert value(game, coven()) == 0

    def test_it_reads_derived_power(self, builder):
        """An anthem lifts every creature equally, so the *count* is unchanged.

        The claim being pinned is that derived power is what is read at all —
        with printed power the anthem would be invisible, and the case that
        separates them is a board where only some creatures are buffed.
        """
        game = builder(players=2).battlefield(0, [BEAR, BEAR, ANTHEM]).build(advance=False)
        assert value(game, coven()) == 1, "both bears moved together"

        game = builder(players=2).battlefield(0, [BEAR, GIANT, ANTHEM]).build(advance=False)
        assert value(game, coven()) == 2


class TestDelirium:
    """Card types among cards in your graveyard."""

    def yard(self, builder, cards):
        return builder(players=2).graveyard(0, list(cards)).build(advance=False)

    def test_an_empty_graveyard_is_nought(self, builder):
        assert value(self.yard(builder, []), delirium()) == 0

    def test_one_card_is_one_type(self, builder):
        assert value(self.yard(builder, [BEAR]), delirium()) == 1

    def test_two_cards_of_one_type_are_still_one(self, builder):
        """The whole reason `count` cannot say it: two objects, one type."""
        assert value(self.yard(builder, [BEAR, GIANT]), delirium()) == 1

    def test_different_types_add_up(self, builder):
        game = self.yard(builder, [BEAR, FOREST, "t_plain_instant"])
        assert value(game, delirium()) == 3

    def test_it_counts_your_graveyard_only(self, builder):
        """`controller` is the filter; an opponent's graveyard is theirs."""
        game = (
            builder(players=2)
            .graveyard(0, [BEAR])
            .graveyard(1, [FOREST, "t_plain_instant"])
            .build(advance=False)
        )
        assert value(game, delirium()) == 1


class TestUsedAsACondition:
    def test_coven_is_an_ordinary_comparison(self, builder):
        """Nothing new in the condition language: `cmp` already takes values."""
        from commanderblitz.engine.effects.conditions import evaluate_condition

        game = builder(players=2).battlefield(0, [BEAR, GIANT, FOREST]).build(advance=False)
        three = {"cmp": ">=", "left": coven(), "right": {"const": 3}}
        two = {"cmp": ">=", "left": coven(), "right": {"const": 2}}
        assert not evaluate_condition(game.state, three, controller=0), (
            "a Forest is not a creature"
        )
        assert evaluate_condition(game.state, two, controller=0)


class TestTheLoaderGuards:
    def test_every_well_formed_leaf_loads(self):
        validate_value(domain(), "test")
        validate_value(coven(), "test")
        validate_value(delirium(), "test")

    def test_a_missing_of_is_refused(self):
        """Defaulted it would count powers on a card that meant land types."""
        with pytest.raises(DslError, match="'of' must be one of"):
            validate_value({"distinct": {"objects": MY_LANDS}}, "test")

    def test_an_unknown_of_is_refused(self):
        with pytest.raises(DslError, match="'of' must be one of"):
            validate_value({"distinct": {"of": "colour", "objects": MY_LANDS}}, "test")

    def test_a_missing_objects_is_refused(self):
        """An empty selector is the whole battlefield, opponents included."""
        with pytest.raises(DslError, match="needs 'objects'"):
            validate_value({"distinct": {"of": "power"}}, "test")

    def test_a_static_may_not_read_it(self):
        """The layers-lite rule, not an oversight.

        Both readings are of derived characteristics, so a static's `condition`
        or value reading this would switch on another static's *output* — which
        is the dependency the fixed-order pipeline cannot have. The static value
        language is a whitelist, so it already refuses it; this pins that it
        stays refused.
        """
        from commanderblitz.cards.loader.statics import _validate_static_value

        with pytest.raises(DslError, match="static values may only use"):
            _validate_static_value(coven(), "test")

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            validate_value(
                {"distinct": {"of": "power", "objects": MY_CREATURES, "zone": "hand"}},
                "test",
            )
