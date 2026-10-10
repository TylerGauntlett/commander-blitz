"""A static filter for "with counters on them".

    "Permanents you control with counters on them have ward {1}."
                                            -- Innkeeper's Talent, level 2

`STATIC_FILTER_KEYS` had nothing for counters: `counters_on` is a value, not a
filter, so the ward static's `affects` could not be narrowed, and without the
clause the card grants ward to every permanent you control -- a strictly better
card. ``has_counters: true`` is one or more counters of **any** kind (122.1: a
loyalty counter, a charge counter, a -1/-1 counter all count).

Admissible for `tapped`'s reason: counters are board state no layer writes --
no static puts a counter on anything -- so reading them cannot make one static
depend on another's output. The answer moves the moment a counter arrives or
leaves, which is the boundary pinned below. The same key is honoured by the
other three readers of the filter language (triggers, cost reduction and the
effect-side selector), so it is never silently ignored.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import matches_static, ward_abilities
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import Step
from commanderblitz.engine.primitives import add_counters, remove_counters
from tests.conftest import only_oid

WARDEN = "t_hc_warden"
BEAR = "t_rc_bear"
ROCK = "t_rc_rock"


def position(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def warded(game, oid: int) -> bool:
    return bool(ward_abilities(game.state, oid))


class TestTheWardFollowsTheCounters:
    def test_no_counters_no_ward(self, builder):
        game = position(builder, mine=[WARDEN, BEAR])
        assert not warded(game, only_oid(game, BEAR))

    def test_a_counter_grants_it(self, builder):
        game = position(builder, mine=[WARDEN, BEAR])
        oid = only_oid(game, BEAR)
        add_counters(game.state, oid, "+1/+1", 1)
        assert warded(game, oid)

    def test_any_kind_counts(self, builder):
        game = position(builder, mine=[WARDEN, ROCK])
        oid = only_oid(game, ROCK)
        add_counters(game.state, oid, "charge", 1)
        assert warded(game, oid)

    def test_removing_the_last_counter_takes_it_away(self, builder):
        game = position(builder, mine=[WARDEN, BEAR])
        oid = only_oid(game, BEAR)
        add_counters(game.state, oid, "+1/+1", 2)
        remove_counters(game.state, oid, "+1/+1", 2)
        assert not warded(game, oid)

    def test_an_opponents_permanent_with_counters_is_not_warded(self, builder):
        game = position(builder, mine=[WARDEN], theirs=[BEAR])
        oid = only_oid(game, BEAR)
        add_counters(game.state, oid, "+1/+1", 1)
        assert not warded(game, oid)


class TestTheNegation:
    def test_false_matches_only_counterless_permanents(self, builder):
        game = position(builder, mine=[WARDEN, BEAR, ROCK])
        bear, rock = only_oid(game, BEAR), only_oid(game, ROCK)
        add_counters(game.state, bear, "+1/+1", 1)
        source = game.state.objects[only_oid(game, WARDEN)]
        filt = {"has_counters": False, "types": ["Creature"]}
        assert not matches_static(game.state, game.state.objects[bear], source, filt)
        filt = {"has_counters": False, "types": ["Artifact"]}
        assert matches_static(game.state, game.state.objects[rock], source, filt)


class TestTheEffectSideSelector:
    def test_it_picks_out_permanents_with_counters(self, builder):
        game = position(builder, mine=[BEAR, ROCK])
        bear = only_oid(game, BEAR)
        add_counters(game.state, bear, "+1/+1", 1)
        ctx = EffectContext(state=game.state, controller=0)
        assert resolve_pool(ctx, {"controller": "you", "has_counters": True}) == [bear]
