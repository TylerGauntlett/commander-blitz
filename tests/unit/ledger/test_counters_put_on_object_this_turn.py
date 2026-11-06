"""One recipient's counters this turn: "if a counter was put on Wakka this turn".

    "Blitzball Captain -- At the beginning of your end step, if a counter was
    put on Wakka this turn, put a +1/+1 counter on each other creature you
    control."                                  -- Wakka, Devoted Guardian

The question is about an *event* on one object, so neither neighbour answers
it. `counters_on` reads the counters present now: a +1/+1 counter put on
Wakka and annihilated by a -1/-1 (704.5q) is gone, yet one was put, and a
counter from an earlier turn is present, yet none was put. The putter-keyed
`counters_put_this_turn` without `on` cannot tell Wakka from any other
creature. So `on` filters `TurnLedger.counters_put` by the recipient's oid,
which `GameState._tally` records off COUNTER_PLACED.

"Was put" names no putter, so the card reads `"player": "all"` (122.6a: an
opponent's counter on Wakka counts). 400.7: a permanent that leaves the
battlefield and returns is a new object, so the ledger forgets the recipient
as it leaves -- while the placement still counts for whoever put it.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, remove_counters
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until

WAKKA = "wakka_devoted_guardian"
BEAR = "t_rc_bear"
ROCK = "t_rc_rock"

ON_SELF = {"counters_put_this_turn": {"player": "all", "on": {"self": True}}}


def position(builder):
    game = (
        builder(players=2)
        .battlefield(0, [BEAR, ROCK])
        .battlefield(1, [BEAR])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game, only_oid(game, BEAR, 0)


def tally(game, source, spec=ON_SELF, controller=0) -> int:
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    return evaluate_value(ctx, spec)


class TestOneRecipient:
    def test_a_counter_on_it_counts(self, builder):
        game, bear = position(builder)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        assert tally(game, bear) == 1

    def test_a_counter_on_another_permanent_does_not(self, builder):
        game, bear = position(builder)
        add_counters(game.state, only_oid(game, ROCK, 0), "charge", 1, by=0)
        add_counters(game.state, only_oid(game, BEAR, 1), "+1/+1", 1, by=0)
        assert tally(game, bear) == 0
        assert tally(game, bear, {"counters_put_this_turn": {"player": "all"}}) == 2

    def test_anybodys_counter_counts_under_all(self, builder):
        game, bear = position(builder)
        add_counters(game.state, bear, "-1/-1", 1, by=1)
        assert tally(game, bear) == 1
        spec = {"counters_put_this_turn": {"player": "you", "on": {"self": True}}}
        assert tally(game, bear, spec) == 0

    def test_a_counter_removed_since_still_counts(self, builder):
        """The `counters_on` near miss's failure."""
        game, bear = position(builder)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        remove_counters(game.state, bear, "+1/+1", 1)
        assert tally(game, bear) == 1

    def test_a_counter_from_before_this_turn_does_not(self, builder):
        game, bear = position(builder)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        game.state.turn_ledger.clear()
        assert game.state.objects[bear].counters.get("+1/+1") == 1
        assert tally(game, bear) == 0

    def test_a_target_reference_reads_that_object(self, builder):
        game, bear = position(builder)
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, theirs, "+1/+1", 2, by=0)
        ctx = EffectContext(state=game.state, controller=0, source_oid=bear, bindings={"it": theirs})
        spec = {"counters_put_this_turn": {"player": "all", "on": {"binding": "it"}}}
        assert evaluate_value(ctx, spec) == 2


class TestANewObject:
    def test_leaving_and_returning_forgets_it(self, builder):
        """400.7."""
        game, bear = position(builder)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        move_object(game.state, bear, Zone.HAND)
        move_object(game.state, bear, Zone.BATTLEFIELD)
        assert tally(game, bear) == 0

    def test_the_putter_still_put_it(self, builder):
        game, bear = position(builder)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        move_object(game.state, bear, Zone.GRAVEYARD)
        assert tally(game, bear, {"counters_put_this_turn": {"player": "you"}}) == 1


def run_through_end_step(game) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn != turn
        or (g.state.step is Step.CLEANUP and not g.state.stack and not g.state.pending_triggers),
    )


def wakka_board(builder):
    game = (
        builder(players=2)
        .battlefield(0, [WAKKA, BEAR])
        .battlefield(1, [BEAR])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game, only_oid(game, WAKKA, 0), only_oid(game, BEAR, 0)


class TestWakka:
    def test_a_counter_on_wakka_spreads_to_each_other_creature(self, builder):
        game, wakka, bear = wakka_board(builder)
        add_counters(game.state, wakka, "+1/+1", 1, by=1)
        run_through_end_step(game)
        assert game.state.objects[bear].counters.get("+1/+1") == 1
        assert game.state.objects[wakka].counters.get("+1/+1") == 1
        assert not game.state.objects[only_oid(game, BEAR, 1)].counters.get("+1/+1")

    def test_a_counter_put_and_annihilated_still_counts(self, builder):
        game, wakka, bear = wakka_board(builder)
        add_counters(game.state, wakka, "+1/+1", 1, by=0)
        add_counters(game.state, wakka, "-1/-1", 1, by=0)
        run_through_end_step(game)
        assert game.state.objects[bear].counters.get("+1/+1") == 1

    def test_a_counter_on_another_creature_does_nothing(self, builder):
        game, _wakka, bear = wakka_board(builder)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        run_through_end_step(game)
        assert game.state.objects[bear].counters.get("+1/+1") == 1

    def test_nothing_without_a_counter(self, builder):
        game, _wakka, bear = wakka_board(builder)
        run_through_end_step(game)
        assert not game.state.objects[bear].counters.get("+1/+1")


class TestTheLoader:
    @pytest.mark.parametrize(
        "on",
        [True, {"self_only": True}, {}, {"self": False}, {"binding": ""}, {"self": True, "target": "t"}],
    )
    def test_a_malformed_reference_is_refused(self, on):
        with pytest.raises(DslError, match="on"):
            validate_value({"counters_put_this_turn": {"player": "all", "on": on}}, "x")

    def test_the_printed_shape_loads(self):
        validate_value(ON_SELF, "x")
