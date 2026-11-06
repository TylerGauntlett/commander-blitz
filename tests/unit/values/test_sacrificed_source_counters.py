"""Counters on a permanent read after it was sacrificed to pay for its ability.

    Wickersmith's Tools: "{5}, {T}, Sacrifice this artifact: Create X tapped
    2/2 colorless Scarecrow artifact creature tokens, where X is the number of
    charge counters on this artifact."

The artifact is sacrificed while the cost is paid (601.2h, via 602.2b), so when
the ability resolves it is a graveyard card with no counters on it (400.7). X is
its last-known information (608.2h): the counters it had as it last existed on
the battlefield. The sacrifice cost's `as` binding is a `zones.snapshot`, and
the snapshot now records counters, so `counters_on` over that binding answers
from it. Without it X reads 0 and the Tools make nothing.

The near miss is `counters_on {"objects": {"self_only": true}}`: that reads the
live object, which has already lost its counters.
"""

from __future__ import annotations

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.zones import sacrifice, snapshot
from tests.conftest import only_oid

BANNER = "t_charge_banner"


def position(builder, charge: int):
    game = builder(players=2).battlefield(0, [BANNER]).build()
    oid = only_oid(game, BANNER)
    obj = game.state.objects[oid]
    if charge:
        obj.add_counter("charge", charge)
    return game, oid


def x_after_sacrifice(game, oid: int, objects: dict) -> int:
    snap = snapshot(game.state, oid)
    sacrifice(game.state, oid)
    assert game.state.objects[oid].zone is Zone.GRAVEYARD
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    ctx.bindings["sacrificed"] = snap
    return evaluate_value(ctx, {"counters_on": {"counter": "charge", "objects": objects}})


class TestTheSnapshotRemembersCounters:
    def test_it_records_each_kind(self, builder):
        game, oid = position(builder, 3)
        game.state.objects[oid].add_counter("+1/+1", 1)
        assert snapshot(game.state, oid)["counters"] == {"charge": 3, "+1/+1": 1}

    def test_a_permanent_with_none_records_none(self, builder):
        game, oid = position(builder, 0)
        assert snapshot(game.state, oid)["counters"] == {}


class TestCountersOnReadsTheSacrificedSource:
    def test_x_is_the_count_it_last_had(self, builder):
        game, oid = position(builder, 3)
        assert x_after_sacrifice(game, oid, {"binding": "sacrificed"}) == 3

    def test_a_kind_it_never_had_reads_zero(self, builder):
        game, oid = position(builder, 3)
        snap = snapshot(game.state, oid)
        sacrifice(game.state, oid)
        ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
        ctx.bindings["sacrificed"] = snap
        assert evaluate_value(ctx, {"counters_on": {"counter": "+1/+1", "objects": {"binding": "sacrificed"}}}) == 0

    def test_reading_the_live_object_is_the_near_miss(self, builder):
        """The graveyard card has no counters left, so self_only reads 0."""
        game, oid = position(builder, 3)
        assert x_after_sacrifice(game, oid, {"self_only": True}) == 0
