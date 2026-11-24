"""``min_colors`` in a static's ``affects`` -- "multicolored", 202.2b.

    "Other multicolored creatures you control get +1/+0."
        -- Rienne, Angel of Rebirth

A multicolored object is one with two or more colours. `colors` cannot say it:
it is a membership test, so ``["W", "U"]`` matches a mono-white creature and a
union of colour pairs still lets one-colour creatures through. The trigger,
spell and off-battlefield filters already had ``min_colors`` for exactly this;
a battlefield static's ``affects`` refused it, so Rienne's anthem was
unwritable.

It is read by `characteristics._matches_printed` off the printed colours, as
`colors` is, so a static cannot depend on a colour another static writes.
A colour-setting characteristic-defining ability ("Transguild Courier is all
colors", 604.3) is part of the printed card and counts.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, pt, static_probe

ANGEL = "t_mc_angel"  # Other multicolored creatures you control get +1/+0.
GOLD = "t_mc_gold"  # a white-blue 2/2
SHARD = "t_mc_shard"  # a white-blue-black 2/2
BEAR = "t_bear"  # a green 2/2


def board(builder, mine=(GOLD, SHARD, BEAR), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, [ANGEL, *mine])
        .battlefield(1, list(theirs))
        .build()
    )


def first(game, card_id: str, pid: int = 0) -> int:
    return oids_of(game, card_id, pid)[0]


class TestTheAnthem:
    def test_a_two_colour_creature_gets_it(self, builder):
        game = board(builder)
        assert pt(game, first(game, GOLD)) == (3, 2)

    def test_a_three_colour_creature_gets_it_once(self, builder):
        """A floor, not a count: three colours is still +1/+0."""
        game = board(builder)
        assert pt(game, first(game, SHARD)) == (3, 2)

    def test_a_one_colour_creature_does_not(self, builder):
        game = board(builder)
        assert pt(game, first(game, BEAR)) == (2, 2)

    def test_the_source_is_excluded(self, builder):
        game = board(builder)
        assert pt(game, first(game, ANGEL)) == (5, 4)

    def test_an_opponents_multicolored_creature_does_not(self, builder):
        game = board(builder, mine=(), theirs=(GOLD,))
        assert pt(game, first(game, GOLD, 1)) == (2, 2)

    def test_it_wears_off_with_the_source(self, builder):
        game = board(builder)
        destroy(game.state, first(game, ANGEL))
        assert pt(game, first(game, GOLD)) == (2, 2)

    def test_an_all_colors_cda_counts(self, builder):
        """Transguild Courier's "is all colors" is printed (604.3)."""
        game = board(builder, mine=("transguild_courier",))
        assert pt(game, first(game, "transguild_courier")) == (4, 3)


def _load(affects: dict) -> None:
    compile_card(
        CardModel.model_validate(
            static_probe(
                {
                    "effect": "buff",
                    "affects": affects,
                    "power": {"const": 1},
                    "toughness": {"const": 0},
                }
            )
        )
    )


class TestTheLoader:
    def test_the_fixture_loads(self, registry):
        assert registry.get(ANGEL).abilities

    def test_it_loads_in_a_branch(self):
        _load(
            {
                "types": ["Creature"],
                "any_of": [{"min_colors": 2}, {"subtypes": ["Angel"]}],
            }
        )

    @pytest.mark.parametrize("value", [0, 6, True, "2", 1.5])
    def test_it_refuses_anything_but_one_to_five(self, value):
        with pytest.raises(DslError, match="min_colors"):
            _load({"types": ["Creature"], "min_colors": value})

    @pytest.mark.parametrize("value", [0, True])
    def test_it_refuses_a_bad_value_in_a_branch(self, value):
        with pytest.raises(DslError, match="min_colors"):
            _load(
                {
                    "types": ["Creature"],
                    "any_of": [{"min_colors": value}, {"subtypes": ["Angel"]}],
                }
            )
