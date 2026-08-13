"""Cascade and ripple — the two keywords that walk a library.

    Cascade — "exile cards from the top of your library until you exile a
    nonland card with lesser mana value. You may cast it without paying its
    mana cost. Put the exiled cards on the bottom in a random order."
    Ripple 4 — "reveal the top four cards. You may cast any with the same name
    as this spell without paying their mana costs. Put the rest on the bottom
    in a random order."

The census filed both as blocked on "free casts off a library scan". The free
cast was already there — `suspend.cast_for_free` — and the **scan** was not:
every other way the DSL reaches a library either takes the top N
(`look_at_top`) or searches the whole of it (`search_library`), and cascade does
neither. It walks down until a condition is met, and the depth is not knowable
when the card is written.

Two things are shared between them and one is not:

- `_bottom_in_random_order` is "put the rest on the bottom in a random order",
  and it is deliberately **not** a shuffle: shuffling reorders the whole library
  and would destroy a stacked top somebody else set up.
- The free cast is shared, but **haste is not**. That flag belongs to suspend,
  and a cascaded creature that could attack immediately would be a strictly
  better card — so `cast_for_free` grew an opt-in rather than granting it to
  everything that casts for nothing.

Ripple is not cascade with a parameter, and the test is why: "the same name as
this spell" is a comparison against the *source*, which no selector key names.
`name` takes a literal written into the card — true for ripple, and wrong the
moment anything copies the card.
"""

from __future__ import annotations

from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone

FOREST = "forest"
BEAR = "t_bear"           # {1}{G}, mana value 2
GIANT = "t_big"           # {5}{G}, mana value 6
CASCADER = "t_cascader"   # {4}{R}, mana value 5
RIPPLER = "t_rippler"     # {1}{W}


def board(builder, library: list[str], source: str):
    game = (
        builder(players=2)
        .battlefield(0, [source])
        .library(0, library)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, op: str, spec, source: int, *, cast: bool = True):
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = OPS[op](ctx, spec)
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration:
            return
        send = [0] if cast else [1]


def library_ids(game, pid: int = 0):
    return [game.state.objects[o].def_id for o in game.state.players[pid].library]


class TestCascade:
    def test_it_stops_at_the_first_cheaper_nonland(self, builder):
        game, src = board(builder, [FOREST, FOREST, BEAR, GIANT], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=False)

        # Three cards were exiled -- two Forests and the Bear -- and all three
        # go to the bottom, because the Bear was not cast.
        assert library_ids(game) == [GIANT, FOREST, FOREST, BEAR] or sorted(
            library_ids(game)
        ) == sorted([GIANT, FOREST, FOREST, BEAR])
        assert library_ids(game)[0] == GIANT, "the scan stopped before it"

    def test_a_land_never_stops_the_scan(self, builder):
        """"a **nonland** card" -- Forests are exiled and walked past."""
        game, src = board(builder, [FOREST, FOREST, FOREST, BEAR], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=True)

        stack = [item.def_id for item in game.state.stack]
        assert stack == [BEAR]

    def test_a_more_expensive_card_never_stops_it_either(self, builder):
        """"lesser mana value" -- the Giant costs 6 against the cascader's 5."""
        game, src = board(builder, [GIANT, BEAR], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=True)

        assert [item.def_id for item in game.state.stack] == [BEAR]

    def test_casting_it_puts_it_on_the_stack(self, builder):
        game, src = board(builder, [BEAR, FOREST], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=True)

        assert [item.def_id for item in game.state.stack] == [BEAR]
        assert library_ids(game) == [FOREST], "nothing else was touched"

    def test_declining_bottoms_it_with_the_rest(self, builder):
        game, src = board(builder, [BEAR, FOREST], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=False)

        assert game.state.stack == []
        assert sorted(library_ids(game)) == sorted([BEAR, FOREST])

    def test_a_cascaded_creature_has_no_haste(self, builder):
        """Haste belongs to suspend. A cascaded creature that could attack is
        a strictly better card than the printed one."""
        game, src = board(builder, [BEAR], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=True)

        bear = next(o for o in game.state.objects.values() if o.def_id == BEAR)
        assert not bear.hasted_by_suspend

    def test_an_empty_library_is_survivable(self, builder):
        game, src = board(builder, [], CASCADER)
        run(game, "cascade", {"op": "cascade"}, src)
        assert library_ids(game) == []


class TestRipple:
    def test_it_casts_the_matching_cards(self, builder):
        game, src = board(builder, [RIPPLER, FOREST, RIPPLER, BEAR], RIPPLER)

        run(game, "ripple", {"op": "ripple", "amount": {"const": 4}}, src, cast=True)

        assert [item.def_id for item in game.state.stack] == [RIPPLER, RIPPLER]

    def test_the_rest_go_to_the_bottom(self, builder):
        game, src = board(builder, [RIPPLER, FOREST, BEAR, FOREST, GIANT], RIPPLER)

        run(game, "ripple", {"op": "ripple", "amount": {"const": 4}}, src, cast=True)

        assert library_ids(game)[0] == GIANT, "the fifth card was never looked at"
        assert sorted(library_ids(game)[1:]) == sorted([FOREST, FOREST, BEAR])

    def test_declining_bottoms_the_match_too(self, builder):
        game, src = board(builder, [RIPPLER, FOREST], RIPPLER)

        run(game, "ripple", {"op": "ripple", "amount": {"const": 4}}, src, cast=False)

        assert game.state.stack == []
        assert sorted(library_ids(game)) == sorted([RIPPLER, FOREST])

    def test_only_the_named_card_matches(self, builder):
        game, src = board(builder, [BEAR, GIANT, FOREST], RIPPLER)

        run(game, "ripple", {"op": "ripple", "amount": {"const": 4}}, src, cast=True)

        assert game.state.stack == []
        assert sorted(library_ids(game)) == sorted([BEAR, GIANT, FOREST])

    def test_the_depth_is_the_card(self, builder):
        game, src = board(builder, [FOREST, FOREST, RIPPLER], RIPPLER)

        run(game, "ripple", {"op": "ripple", "amount": {"const": 2}}, src, cast=True)

        assert game.state.stack == [], "the match was third, and ripple 2 looks at two"
        assert library_ids(game)[0] == RIPPLER


class TestBottomingIsNotShuffling:
    def test_the_untouched_library_keeps_its_order(self, builder):
        """A shuffle would reorder the whole thing, which is a different action."""
        game, src = board(builder, [BEAR, GIANT, FOREST, FOREST, FOREST], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=True)

        # Only the Bear left; the deep cards are untouched and in order.
        assert library_ids(game) == [GIANT, FOREST, FOREST, FOREST]

    def test_the_exiled_cards_really_are_at_the_bottom(self, builder):
        game, src = board(builder, [FOREST, BEAR, GIANT, GIANT], CASCADER)

        run(game, "cascade", {"op": "cascade"}, src, cast=False)

        assert library_ids(game)[:2] == [GIANT, GIANT]
        assert sorted(library_ids(game)[2:]) == sorted([FOREST, BEAR])
        assert all(
            game.state.objects[o].zone is Zone.LIBRARY
            for o in game.state.players[0].library
        )
