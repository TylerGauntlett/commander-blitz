""""Search your library **and/or** graveyard for a creature card … and put it
onto the battlefield."

Finale of Devastation fetches **one** creature. The obvious implementation --
a `search_library` followed by a `return_from_graveyard` -- fetches up to two,
because each op carries its own count, and that is a strictly better card than
the one printed. The selector language could not merge the two zones either:
`resolve_pool` reads exactly one `zone`, and `validate_selector` refuses a
`zone` inside an `any_of` branch, so `any_of` unions descriptions and never
zones.

So the count has to be taken over the **union**, which is what "and/or" means:
you look through both and take one. That is the single claim this file exists
to pin, and every other test here is a boundary around it.

`choose_mode` was the near miss worth recording: it gets the count right and is
still the wrong card, because a mode is chosen blind and locks out the other
zone, while "and/or" lets you see both before committing.

The shuffle is deliberately not conditional -- see `op_search_zones` and
rules-coverage.md. This implementation always offers both zones, so it has
always searched the library, so it always shuffles.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.errors import DslError

BEAR = "t_bear"
FOREST = "forest"


def run(game, spec, answer: list[int] | None = None):
    """Run the op to completion. Returns the decision it asked, if any."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = OPS[spec["op"]](ctx, spec)
    try:
        decision = next(gen)
    except StopIteration:
        return None
    if answer is None:
        # Take as many as the decision actually allows. `ask_objects` trusts the
        # answer it is handed -- it is `game.apply` that enforces the bounds --
        # so a helper that over-answered would be testing itself.
        answer = list(range(min(len(decision.options), decision.max_count)))
    with contextlib.suppress(StopIteration):
        gen.send(answer)
    return decision


def finale(**extra):
    """Finale of Devastation's first sentence."""
    return {
        "op": "search_zones",
        "zones": ["library", "graveyard"],
        "count": 1,
        "destination": "battlefield",
        "selector": {"types": ["Creature"]},
        **extra,
    }


def on_battlefield(game) -> int:
    return len(game.state.battlefield)


def library_order(game, pid: int = 0) -> list[int]:
    """Oids, not names. A library of thirteen Forests shuffles into itself."""
    return list(game.state.players[pid].library)


class TestTheCountIsOverTheUnion:
    def test_one_creature_total_not_one_per_zone(self, builder):
        """The claim. Two ops in sequence would fetch two."""
        game = (
            builder(players=2)
            .library(0, [BEAR, FOREST])
            .graveyard(0, [BEAR])
            .build()
        )
        decision = run(game, finale())
        assert decision is not None
        assert len(decision.options) == 2, "both creatures are in the pool"
        assert decision.max_count == 1, "…and only one may be taken"
        assert on_battlefield(game) == 1

    def test_both_zones_reach_the_pool(self, builder):
        game = builder(players=2).library(0, [BEAR]).graveyard(0, [BEAR]).build()
        from_library = game.state.players[0].library[0]
        from_graveyard = game.state.players[0].graveyard[0]
        decision = run(game, finale(), answer=[])
        offered = {opt.value for opt in decision.options}
        assert offered == {from_library, from_graveyard}

    def test_the_graveyard_half_can_be_the_one_taken(self, builder):
        game = builder(players=2).library(0, [FOREST]).graveyard(0, [BEAR]).build()
        buried = game.state.players[0].graveyard[0]
        run(game, finale())
        assert game.state.objects[buried].zone is Zone.BATTLEFIELD
        assert game.state.objects[buried].controller == 0

    def test_finding_nothing_is_legal(self, builder):
        """A search may always fail to find (701.19a)."""
        game = builder(players=2).library(0, [FOREST]).graveyard(0, [FOREST]).build()
        decision = run(game, finale(), answer=[])
        assert decision is None or decision.min_count == 0
        assert on_battlefield(game) == 0

    def test_an_empty_pool_asks_nothing(self, builder):
        game = builder(players=2).library(0, [FOREST]).build()
        assert run(game, finale()) is None
        assert on_battlefield(game) == 0


class TestEachHalfIsJudgedInItsOwnZone:
    def test_the_probe_zone_follows_the_half_being_built(self, builder):
        """The pool is built zone by zone, and each half is tested as a card in
        the zone it actually came from -- a graveyard creature must not be
        judged as though it were in a library."""
        game = builder(players=2).library(0, [BEAR]).graveyard(0, [BEAR]).build()
        from_library = game.state.players[0].library[0]
        from_graveyard = game.state.players[0].graveyard[0]
        decision = run(game, finale(), answer=[])
        assert {opt.value for opt in decision.options} == {from_library, from_graveyard}

    def test_a_zone_in_the_selector_is_refused(self):
        """It would be silently overridden by whichever half was being built,
        so a card writing it would not get what it wrote."""
        with pytest.raises(DslError, match="zone"):
            _validate_effect(
                finale(selector={"types": ["Creature"], "zone": "graveyard"}),
                "test",
                {},
            )


class TestTheShuffle:
    def test_it_shuffles_when_a_library_was_searched(self, builder):
        game = (
            builder(players=2, seed=3)
            .library(0, [BEAR] + [FOREST] * 12)
            .graveyard(0, [BEAR])
            .build()
        )
        before = library_order(game)
        run(game, finale(), answer=[])
        after = library_order(game)
        assert sorted(after) == sorted(before)
        assert after != before, "701.19c: searching a library ends in a shuffle"

    def test_it_does_not_shuffle_when_no_library_was_searched(self, builder):
        game = (
            builder(players=2, seed=3)
            .library(0, [BEAR] + [FOREST] * 12)
            .graveyard(0, [BEAR])
            .hand(0, [BEAR])
            .build()
        )
        before = library_order(game)
        run(game, finale(zones=["graveyard", "hand"]), answer=[])
        assert library_order(game) == before, "the library was never looked at"


class TestSearchLibraryStillWorks:
    """It delegates to the same helper now, so its behaviour is a regression."""

    def test_it_finds_and_shuffles(self, builder):
        game = builder(players=2, seed=3).library(0, [BEAR] + [FOREST] * 12).build()
        spec = {
            "op": "search_library",
            "count": 1,
            "destination": "hand",
            "selector": {"types": ["Creature"]},
        }
        decision = run(game, spec)
        assert len(decision.options) == 1
        assert len(game.state.players[0].hand) == 1

    def test_it_still_shuffles_when_it_finds_nothing(self, builder):
        game = builder(players=2, seed=3).library(0, [FOREST] * 13).build()
        before = library_order(game)
        run(game, {"op": "search_library", "selector": {"types": ["Creature"]}})
        assert library_order(game) != before, "an empty search still shuffles"


class TestTheLoaderGuards:
    def test_a_well_formed_effect_loads(self):
        _validate_effect(finale(), "test", {})

    def test_one_zone_is_refused(self):
        """That is `search_library`, and saying it this way hides the union."""
        with pytest.raises(DslError, match="at least two"):
            _validate_effect(finale(zones=["library"]), "test", {})

    def test_a_missing_zones_list_is_refused(self):
        spec = finale()
        del spec["zones"]
        with pytest.raises(DslError, match="at least two"):
            _validate_effect(spec, "test", {})

    def test_an_unsearchable_zone_is_refused(self):
        with pytest.raises(DslError, match="cannot search"):
            _validate_effect(finale(zones=["library", "battlefield"]), "test", {})

    def test_a_repeated_zone_is_refused(self):
        """It would put every card in that zone into the pool twice."""
        with pytest.raises(DslError, match="twice"):
            _validate_effect(finale(zones=["library", "library"]), "test", {})
