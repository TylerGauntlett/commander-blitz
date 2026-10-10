"""Level up — bands, which are conditional statics rather than a subsystem.

    "Level up {2} ({2}: Put a level counter on this. Level up only as a
    sorcery.)
     LEVEL 1-3  3/4
     LEVEL 4+   6/6, flying"

The census filed this as blocked: "levels are a characteristic-defining
subsystem, not counters with a static". The second half of that sentence is the
implementation, and the reason it works is `set_pt`.

A level band is not an anthem. It **replaces** the printed P/T rather than
adding to it, which is exactly what `set_pt` does and what `buff` does not — so
a levelled creature is 3/4 and not 2/2 plus 3/4. And a band is an interval,
which the static condition language already says with `all` over two `counters`
comparisons; the top band is the same thing with no upper bound.

What that leaves is a level counter, which is an ordinary counter, and an
activated ability that adds one, which is an ordinary ability. Nothing here is
characteristic-*defining* in the sense that would need a subsystem: the
characteristics pipeline already runs `set_pt` and `grant_keyword` after
reading a static's condition, and a counter is a pipeline input.

The boundaries worth pinning are the band edges, because an off-by-one is
invisible: level 3 is the *last* turn of the middle band, and level 4 is the
first of the top one.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Keyword
from tests.conftest import only_oid, pass_until

PLAINS = "plains"
KNIGHT = "t_leveler"


def position(builder, levels: int = 0):
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * 6)
        .battlefield(0, [KNIGHT], counters={"level": levels} if levels else None)
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )
    return game, only_oid(game, KNIGHT)


def level_up(game, knight: int) -> bool:
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.player == 0,
        limit=200,
    )
    action = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == knight
        ),
        None,
    )
    if action is None:
        return False
    game.apply(action)
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)
    return True


class TestTheBands:
    def test_unlevelled_it_is_the_printed_creature(self, builder):
        game, knight = position(builder)
        assert (chars(game.state, knight).power, chars(game.state, knight).toughness) == (2, 2)

    def test_level_one_enters_the_middle_band(self, builder):
        game, knight = position(builder, levels=1)
        assert (chars(game.state, knight).power, chars(game.state, knight).toughness) == (3, 4)

    def test_level_three_is_still_the_middle_band(self, builder):
        """The last turn of it -- an off-by-one here is invisible on a board."""
        game, knight = position(builder, levels=3)
        assert (chars(game.state, knight).power, chars(game.state, knight).toughness) == (3, 4)

    def test_level_four_enters_the_top_band(self, builder):
        game, knight = position(builder, levels=4)
        assert (chars(game.state, knight).power, chars(game.state, knight).toughness) == (6, 6)

    def test_the_top_band_has_no_ceiling(self, builder):
        game, knight = position(builder, levels=9)
        assert (chars(game.state, knight).power, chars(game.state, knight).toughness) == (6, 6)


class TestItReplacesRatherThanAdds:
    def test_the_printed_size_is_gone(self, builder):
        """`set_pt`, not `buff`: a levelled Knight is 3/4, not 5/6."""
        game, knight = position(builder, levels=1)
        assert chars(game.state, knight).power == 3

    def test_a_counter_still_layers_on_top(self, builder):
        """The band sets the base; +1/+1 counters apply after it, as they should."""
        from commanderblitz.engine.objects import PLUS_ONE
        from commanderblitz.engine.primitives import add_counters

        game, knight = position(builder, levels=1)
        add_counters(game.state, knight, PLUS_ONE, 2)

        assert (chars(game.state, knight).power, chars(game.state, knight).toughness) == (5, 6)


class TestTheGrantedKeyword:
    def test_the_top_band_grants_flying(self, builder):
        game, knight = position(builder, levels=4)
        assert Keyword.FLYING.value in chars(game.state, knight).keywords

    def test_the_middle_band_does_not(self, builder):
        game, knight = position(builder, levels=3)
        assert Keyword.FLYING.value not in chars(game.state, knight).keywords


class TestLevellingUp:
    def test_the_ability_adds_a_counter(self, builder):
        game, knight = position(builder)
        assert level_up(game, knight)
        assert game.state.objects[knight].counter("level") == 1

    def test_levelling_moves_the_band(self, builder):
        game, knight = position(builder)
        level_up(game, knight)
        assert (chars(game.state, knight).power, chars(game.state, knight).toughness) == (3, 4)
