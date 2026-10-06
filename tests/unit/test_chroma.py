"""Chroma — the first thing that looks *inside* a mana cost.

    Primalcrux — "Chroma — Primalcrux's power and toughness are each equal to
    the number of green mana symbols in the mana costs of permanents you
    control."

Every other reader of a `ManaCost` in the engine wants one of two things: its
total (`mana_value`, for costing and for clash) or the set of colours in it
(`colors`, for colour identity). Chroma wants neither — it wants how many times
one symbol appears, so `{G}{G}{G}{G}` is **four** where `colors` says green
once and `mana_value` says four *including the generic it does not have*.

Two facts the tests pin because both are silently wrong otherwise:

- **A hybrid pip counts for each of its colours** (rule 107.4f). A Kitchen Finks
  in play adds one to a green chroma count and one to a white one; treating
  `hybrid` as "not a coloured pip" — which is how `ManaCost` stores it, and for
  good reasons — would make it count for neither.
- **It reads the printed cost.** That is what the keyword says, and it is also
  why the leaf is legal inside a `set_pt` static: a printed mana cost is a
  pipeline *input*, so no layer can change one and no static comes to depend on
  another's output. Primalcrux is a static, so the leaf had to be in both value
  languages or the card would have loaded and read 0.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader.statics import _validate_static_value
from automtg.engine.characteristics import chars
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value, validate_value
from automtg.engine.errors import DslError
from automtg.engine.mana import ManaCost

FOREST = "forest"
BEAR = "t_bear"          # {1}{G}
GIANT = "t_big"          # {5}{G}
HULK = "t_chroma_hulk"   # {G}{G}{G}{G}
ISLAND = "island"

MINE = {"mana_symbols": {"of": "G", "objects": {"controller": "you"}}}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


class TestCountingSymbols:
    def test_it_counts_repeats_not_colours(self, builder):
        """`colors` says green once. The card says four."""
        assert ManaCost.parse("{G}{G}{G}{G}").symbols_of("G") == 4

    def test_generic_is_not_a_symbol(self):
        assert ManaCost.parse("{5}{G}").symbols_of("G") == 1

    def test_another_colour_is_not_counted(self):
        assert ManaCost.parse("{1}{U}{U}").symbols_of("G") == 0

    def test_a_land_with_no_cost_counts_nothing(self):
        assert ManaCost.parse("").symbols_of("G") == 0

    def test_a_hybrid_pip_counts_for_each_of_its_colours(self):
        """Rule 107.4f. `hybrid` is stored apart from `colored`, so this is
        the case that would silently count neither."""
        cost = ManaCost.parse("{1}{G/W}")
        assert cost.symbols_of("G") == 1
        assert cost.symbols_of("W") == 1

    def test_a_two_generic_hybrid_counts_once_for_its_colour(self):
        assert ManaCost.parse("{2/W}").symbols_of("W") == 1
        assert ManaCost.parse("{2/W}").symbols_of("G") == 0


class TestOverABoard:
    def test_it_sums_across_permanents(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, GIANT]).build(advance=False)
        assert value(game, MINE) == 2

    def test_lands_contribute_nothing(self, builder):
        game = builder(players=2).battlefield(0, [FOREST] * 5).build(advance=False)
        assert value(game, MINE) == 0, "a basic land has no mana cost"

    def test_an_opponents_board_is_not_counted(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [BEAR, GIANT])
            .build(advance=False)
        )
        assert value(game, MINE) == 1

    def test_an_empty_board_is_zero(self, builder):
        game = builder(players=2).build(advance=False)
        assert value(game, MINE) == 0


class TestInsideAStatic:
    def test_primalcrux_sizes_itself(self, builder):
        """Its own {G}{G}{G}{G} counts, which is why it is a 4/4 alone."""
        game = builder(players=2).battlefield(0, [HULK]).build(advance=False)
        hulk = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == HULK)
        assert (chars(game.state, hulk).power, chars(game.state, hulk).toughness) == (4, 4)

    def test_it_grows_with_the_board(self, builder):
        game = builder(players=2).battlefield(0, [HULK, BEAR, GIANT]).build(advance=False)
        hulk = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == HULK)
        assert chars(game.state, hulk).power == 6, "four of its own, plus one each"

    def test_off_colour_permanents_do_not_grow_it(self, builder):
        game = builder(players=2).battlefield(0, [HULK, ISLAND]).build(advance=False)
        hulk = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == HULK)
        assert chars(game.state, hulk).power == 4


class TestTheGuards:
    def test_both_languages_accept_a_well_formed_leaf(self):
        validate_value(MINE, "test")
        _validate_static_value(MINE, "test")

    def test_a_missing_colour_is_refused(self):
        """Read as 0 it makes Primalcrux a 0/0 that dies on arrival."""
        with pytest.raises(DslError, match="must name a colour"):
            validate_value({"mana_symbols": {"objects": {"controller": "you"}}}, "test")

    def test_an_unknown_colour_is_refused(self):
        with pytest.raises(DslError, match="must name a colour"):
            validate_value(
                {"mana_symbols": {"of": "Green", "objects": {"controller": "you"}}}, "test"
            )

    def test_a_missing_objects_is_refused(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            validate_value({"mana_symbols": {"of": "G"}}, "test")

    def test_the_static_language_refuses_it_too(self):
        with pytest.raises(DslError, match="must name a colour"):
            _validate_static_value({"mana_symbols": {"objects": {"controller": "you"}}}, "test")
