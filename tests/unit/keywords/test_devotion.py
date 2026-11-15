"""Devotion to two colours -- `mana_symbols` with a list in `of`.

    Athreos, Shroud-Veiled -- "As long as your devotion to white and black is
    less than seven, Athreos isn't a creature."
    March of the Canonized -- "At the beginning of your upkeep, if your
    devotion to white and black is seven or greater, create a 4/3 ..."

Rule 700.5a: devotion to two colours is the number of mana symbols among the
mana costs of permanents you control that are *either* colour. A `{W/B}` pip is
one symbol that happens to be both, so it counts **once**.

The near miss is a `sum` of two single-colour `mana_symbols` leaves. Each one
counts a hybrid pip for its colour (107.4f, which chroma needs), so the sum
counts `{W/B}` twice and a God becomes a creature early. These tests pin the
single count in both value languages: the effect side, which March's
intervening-if reads, and the static side, which the God's `set_types` reads.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.statics import _validate_static_value
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import ManaCost

GOD = "t_wb_god"              # {W/B}, not a creature below devotion 4
NIP = "nip_gwyllion"          # {W/B}
HARVEST = "harvest_gwyllion"    # {2}{W/B}{W/B}
SPIKES = "riot_spikes"        # {B/R}
LIFELINKER = "t_lifelinker"   # {1}{W}
BEAR = "t_bear"              # {1}{G}

WB = {"mana_symbols": {"of": ["W", "B"], "objects": {"controller": "you"}}}
SUMMED = {
    "sum": [
        {"mana_symbols": {"of": "W", "objects": {"controller": "you"}}},
        {"mana_symbols": {"of": "B", "objects": {"controller": "you"}}},
    ]
}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def board(builder, mine=(), theirs=()):
    game = builder(players=2).battlefield(0, list(mine)).battlefield(1, list(theirs))
    return game.build(advance=False)


def god(game) -> int:
    return next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == GOD)


class TestCountingACost:
    def test_a_hybrid_of_both_colours_counts_once(self):
        assert ManaCost.parse("{W/B}").symbols_of_any(["W", "B"]) == 1

    def test_plain_pips_of_each_colour_both_count(self):
        assert ManaCost.parse("{W}{W}{B}").symbols_of_any(["W", "B"]) == 3

    def test_a_hybrid_with_one_listed_colour_counts(self):
        """{B/R} is a black symbol, so it counts toward white-and-black."""
        assert ManaCost.parse("{B/R}").symbols_of_any(["W", "B"]) == 1

    def test_a_hybrid_with_no_listed_colour_does_not(self):
        assert ManaCost.parse("{G/U}").symbols_of_any(["W", "B"]) == 0

    def test_generic_is_not_a_symbol(self):
        assert ManaCost.parse("{3}{W}").symbols_of_any(["W", "B"]) == 1

    def test_a_string_is_single_colour_chroma(self):
        cost = ManaCost.parse("{1}{W/B}{W/B}")
        assert cost.symbols_of_any("W") == cost.symbols_of("W") == 2


class TestOverABoard:
    def test_hybrid_permanents_count_once_each(self, builder):
        game = board(builder, mine=[NIP, HARVEST])
        assert value(game, WB) == 3, "one {W/B} on Nip Gwyllion, two on Harvest Gwyllion"

    def test_the_sum_near_miss_double_counts(self, builder):
        """Why the list exists: two leaves summed see every hybrid twice."""
        game = board(builder, mine=[NIP, HARVEST])
        assert value(game, SUMMED) == 6

    def test_mixed_board(self, builder):
        game = board(builder, mine=[NIP, SPIKES, LIFELINKER, BEAR])
        assert value(game, WB) == 3, "{W/B}, {B/R}, {W}; the green bear adds nothing"

    def test_an_opponents_board_is_not_counted(self, builder):
        game = board(builder, mine=[NIP], theirs=[HARVEST, NIP])
        assert value(game, WB) == 1


class TestInsideAStatic:
    def test_below_the_threshold_it_is_not_a_creature(self, builder):
        """Its own {W/B}, plus the Harvest Gwyllion's two: three, one short."""
        game = board(builder, mine=[GOD, HARVEST])
        got = chars(game.state, god(game))
        assert "Creature" not in got.types
        assert "Enchantment" in got.types

    def test_reaching_the_threshold_makes_it_one(self, builder):
        game = board(builder, mine=[GOD, HARVEST, NIP])
        assert "Creature" in chars(game.state, god(game)).types

    def test_double_counting_would_have_animated_it_early(self, builder):
        """God + Harvest Gwyllion summed per colour is six; devotion is three."""
        game = board(builder, mine=[GOD, HARVEST])
        assert value(game, SUMMED) >= 4
        assert "Creature" not in chars(game.state, god(game)).types


class TestTheGuards:
    def test_both_languages_accept_a_colour_list(self):
        validate_value(WB, "test")
        _validate_static_value(WB, "test")

    @pytest.mark.parametrize(
        "of",
        [["W"], ["W", "W"], ["W", "Black"], [], ["W", 1]],
        ids=["one", "repeat", "misspelt", "empty", "not-a-string"],
    )
    def test_a_malformed_list_is_refused(self, of):
        expr = {"mana_symbols": {"of": of, "objects": {"controller": "you"}}}
        with pytest.raises(DslError, match="two or more distinct colours"):
            validate_value(expr, "test")
        with pytest.raises(DslError, match="two or more distinct colours"):
            _validate_static_value(expr, "test")
