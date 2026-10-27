"""Discover — cascade's walk with a different bound, a second home and a name.

    701.57a "Discover N" means "Exile cards from the top of your library until
    you exile a nonland card with mana value N or less. You may cast that card
    without paying its mana cost. If you don't cast it, put that card into your
    hand. Put the remaining exiled cards on the bottom of your library in a
    random order."
    701.57c An effect that refers to a "discovered card" means the card exiled
    by the discover, whether it was cast or put into its owner's hand.

`cascade` is the near miss and makes three different cards at once. Its bound
is strictly *less than*, so discover 2 written as cascade walks past a
two-drop. A card it does not cast goes to the bottom, so "or put it into your
hand" becomes "or lose it". And it binds nothing, so Hit the Mother Lode --
"if the discovered card's mana value is less than 10, create a number of
tapped Treasure tokens equal to the difference" -- has nothing to read.

The witness is Hit the Mother Lode, and the boundary that matters for it is the
empty scan: a library with no qualifying card discovers nothing, and the
Treasures must not then be computed off a mana value of 0.
"""

from __future__ import annotations

import inspect

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import hand_ids, library_ids

FOREST = "forest"
BEAR = "t_bear"           # {1}{G}, mana value 2
GIANT = "t_big"           # {5}{G}, mana value 6
SOURCE = "t_cascader"     # only somewhere for the effect to come from

#: Hit the Mother Lode's second sentence, exactly as the card writes it.
MOTHER_LODE_FOLLOW_UP = {
    "op": "if",
    "condition": {
        "all": [
            {"exists": {"binding": "discovered"}},
            {
                "cmp": "<",
                "left": {"mana_value_of": {"objects": {"binding": "discovered"}}},
                "right": {"const": 10},
            },
        ]
    },
    "then": [
        {
            "op": "create_token",
            "token": "treasure_token",
            "tapped": True,
            "amount": {
                "minus": [
                    {"const": 10},
                    {"mana_value_of": {"objects": {"binding": "discovered"}}},
                ]
            },
        }
    ],
}


def board(builder, library: list[str]):
    game = builder(players=2).battlefield(0, [SOURCE]).library(0, library).build(advance=False)
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, specs: list[dict], source: int, *, cast: bool = True) -> EffectContext:
    """Run effects in one context, as one resolution, answering every yes/no."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    for spec in specs:
        gen = OPS[spec["op"]](ctx, spec)
        if not inspect.isgenerator(gen):
            continue
        send = None
        while True:
            try:
                gen.send(send)
            except StopIteration:
                break
            send = [0] if cast else [1]
    return ctx


def discover(n: int) -> dict:
    return {"op": "discover", "amount": {"const": n}, "as": "discovered"}


def treasures(game) -> list:
    return [o for o in game.state.battlefield_objects(0) if o.def_id == "treasure_token"]


class TestTheBound:
    def test_mana_value_equal_to_n_stops_the_scan(self, builder):
        """"N or less" -- the boundary cascade gets wrong."""
        game, src = board(builder, [FOREST, BEAR, GIANT])

        run(game, [discover(2)], src, cast=True)

        assert [item.def_id for item in game.state.stack] == [BEAR]
        assert library_ids(game)[0] == GIANT, "the scan stopped at the Bear"

    def test_a_card_over_n_is_walked_past(self, builder):
        game, src = board(builder, [GIANT, BEAR, FOREST])

        run(game, [discover(2)], src, cast=True)

        assert [item.def_id for item in game.state.stack] == [BEAR]
        assert library_ids(game)[0] == FOREST
        assert sorted(library_ids(game)[1:]) == [GIANT], "the Giant went to the bottom"

    def test_a_land_never_stops_it(self, builder):
        game, src = board(builder, [FOREST, FOREST, BEAR])

        run(game, [discover(10)], src, cast=True)

        assert [item.def_id for item in game.state.stack] == [BEAR]
        assert library_ids(game) == [FOREST, FOREST]


class TestCastOrHand:
    def test_declining_puts_it_into_hand(self, builder):
        """Cascade bottoms a declined card; discover hands it over."""
        game, src = board(builder, [FOREST, BEAR, GIANT])

        run(game, [discover(3)], src, cast=False)

        assert game.state.stack == []
        assert hand_ids(game) == [BEAR]
        assert library_ids(game) == [GIANT, FOREST]

    def test_the_rest_never_reach_the_hand(self, builder):
        game, src = board(builder, [GIANT, FOREST, BEAR])

        run(game, [discover(2)], src, cast=False)

        assert hand_ids(game) == [BEAR]
        assert sorted(library_ids(game)) == sorted([GIANT, FOREST])
        assert all(game.state.objects[o].zone is Zone.LIBRARY for o in game.state.players[0].library)


class TestTheBinding:
    def test_it_names_the_cast_card(self, builder):
        game, src = board(builder, [FOREST, BEAR])

        ctx = run(game, [discover(5)], src, cast=True)

        (oid,) = ctx.bindings["discovered"]
        assert game.state.objects[oid].def_id == BEAR

    def test_it_names_the_card_put_into_hand(self, builder):
        """701.57c -- the discovered card is the discovered card either way."""
        game, src = board(builder, [FOREST, BEAR])

        ctx = run(game, [discover(5)], src, cast=False)

        (oid,) = ctx.bindings["discovered"]
        assert oid in game.state.players[0].hand

    def test_an_exhausted_library_binds_nothing(self, builder):
        game, src = board(builder, [FOREST, GIANT])

        ctx = run(game, [discover(2)], src)

        assert ctx.bindings["discovered"] == []
        assert sorted(library_ids(game)) == sorted([FOREST, GIANT])
        assert hand_ids(game) == []


class TestHitTheMotherLode:
    def test_the_difference_in_tapped_treasures(self, builder):
        game, src = board(builder, [FOREST, BEAR])

        run(game, [discover(10), MOTHER_LODE_FOLLOW_UP], src, cast=True)

        made = treasures(game)
        assert len(made) == 8, "10 minus the Bear's 2"
        assert all(t.tapped for t in made)

    def test_a_card_put_into_hand_still_counts(self, builder):
        game, src = board(builder, [GIANT])

        run(game, [discover(10), MOTHER_LODE_FOLLOW_UP], src, cast=False)

        assert len(treasures(game)) == 4

    def test_nothing_discovered_makes_no_treasure(self, builder):
        """Read off an empty binding, the mana value would be 0 and the card
        would make ten Treasures for whiffing."""
        game, src = board(builder, [FOREST, FOREST])

        run(game, [discover(10), MOTHER_LODE_FOLLOW_UP], src)

        assert treasures(game) == []


class TestTheLoaderGuard:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_discover_probe",
                "name": "Discover Probe",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )

    def test_a_number_loads(self):
        compile_card(self._card(discover(10)))

    def test_without_one_it_is_refused(self):
        """Read as 0, discover would stop only at a free nonland card."""
        with pytest.raises(DslError, match="discover needs an 'amount'"):
            compile_card(self._card({"op": "discover"}))
