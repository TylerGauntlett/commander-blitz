""""…if it had counters on it" -- `counters_had: "any"`.

    Angelic Sleuth -- "Whenever another permanent you control leaves the
    battlefield, if it had counters on it, investigate."

`test_counters_had.py` makes the case for reading counters off the leave
event's `had_counters` snapshot rather than off the object, which
`reset_permanent_state` has already wiped. That value took one kind. This
card asks about every kind, and the kinds are open-ended -- a `+1/+1`, an oil,
a shield, a lore counter all count -- so ``"any"`` sums the snapshot rather
than an `any` condition naming a list of kinds, which would be a narrower card.
"""

from __future__ import annotations

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, settle

SLEUTH = "t_hac_sleuth"
BEAR = "t_bear"


def position(builder):
    game = (
        builder(players=2)
        .battlefield(0, [SLEUTH, BEAR])
        .library(0, ["plains"] * 20)
        .build()
    )
    return game, only_oid(game, BEAR, 0)


def drawn_on_leaving(game, oid: int, to: Zone = Zone.GRAVEYARD) -> int:
    """Cards drawn, counted off the library: a bounce adds the permanent itself
    to the hand."""
    before = len(game.state.players[0].library)
    move_object(game.state, oid, to)
    settle(game)
    return before - len(game.state.players[0].library)


class TestAnyKindCounts:
    def test_a_plus_one_counter_counts(self, builder):
        game, bear = position(builder)
        game.state.objects[bear].add_counter("+1/+1", 1)
        assert drawn_on_leaving(game, bear) == 1

    def test_a_kind_nobody_listed_counts_too(self, builder):
        """The reason it is a sum and not a list of kinds."""
        game, bear = position(builder)
        game.state.objects[bear].add_counter("oil", 2)
        assert drawn_on_leaving(game, bear) == 1

    def test_no_counters_means_no_trigger(self, builder):
        game, bear = position(builder)
        assert drawn_on_leaving(game, bear) == 0

    def test_any_departure_counts_not_only_death(self, builder):
        game, bear = position(builder)
        game.state.objects[bear].add_counter("shield", 1)
        assert drawn_on_leaving(game, bear, to=Zone.HAND) == 1


class TestTheValue:
    def test_it_sums_every_kind(self, builder):
        game, _ = position(builder)
        ctx = EffectContext(state=game.state, controller=0)
        ctx.bindings["had_counters"] = {"+1/+1": 2, "oil": 1}
        assert evaluate_value(ctx, {"counters_had": "any"}) == 3

    def test_it_is_zero_with_no_snapshot(self, builder):
        game, _ = position(builder)
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"counters_had": "any"}) == 0
