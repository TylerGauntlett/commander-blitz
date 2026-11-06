"""The turn's counter-placement ledger: "if you put a counter on a creature
this turn".

    "At the beginning of each end step, if you put a counter on a creature this
    turn, this enchantment deals 2 damage to each opponent."
                                                    -- Lasting Tarfire

A question about an *event* the board cannot answer: a creature that carries a
+1/+1 counter at the end step may have had it since turn three, and one a
counter was put on this turn may have died or had the counter removed since.
So it is the per-turn ledger's, folded in `GameState._tally` off
COUNTER_PLACED -- every placement the engine makes, `add_counters` and the
counters a permanent enters with alike (122.6) -- **whatever was on the
battlefield when it happened**. The near miss the gap record names, a
`counter_placed` trigger setting a turn flag, is an ability the card does not
print and misses counters put before the enchantment arrived.

Who put them is 122.6a's `put_by`, not the recipient's controller: putting a
counter on an opponent's creature counts for you, and an opponent putting one
on yours does not. "On a creature" is read off the recipient's derived types
at the moment of placement, so a counter put on a noncreature artifact does
not count even if it is animated later. 603.4: the intervening "if" is checked
when the end step begins and again on resolution; the ledger clears at cleanup.
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

TARFIRE = "t_cpt_tarfire"
BEAR = "t_rc_bear"
ROCK = "t_rc_rock"
HYDRA = "t_ceo_hydra"  # enters with two +1/+1 counters

ON_A_CREATURE = {"counters_put_this_turn": {"player": "you", "types": ["Creature"]}}


def position(builder, mine=(), theirs=(), active=0, hand=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .hand(0, list(hand))
        .battlefield(1, list(theirs))
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build()
    )


def in_hand(game, card_id: str, pid: int = 0) -> int:
    return next(o for o in game.state.players[pid].hand if game.state.objects[o].def_id == card_id)


def tally(game, spec=ON_A_CREATURE, controller=0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), spec)


def run_through_end_step(game) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn != turn
        or (g.state.step is Step.CLEANUP and not g.state.stack and not g.state.pending_triggers),
    )


class TestTheLedger:
    def test_a_counter_you_put_on_a_creature_counts(self, builder):
        game = position(builder, mine=[BEAR])
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 2, by=0)
        assert tally(game) == 2

    def test_every_kind_counts(self, builder):
        game = position(builder, theirs=[BEAR])
        add_counters(game.state, only_oid(game, BEAR, 1), "-1/-1", 1, by=0)
        add_counters(game.state, only_oid(game, BEAR, 1), "stun", 1, by=0)
        assert tally(game) == 2

    def test_who_put_it_is_the_putter_not_the_creatures_controller(self, builder):
        """122.6a."""
        game = position(builder, mine=[BEAR])
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 1, by=1)
        assert tally(game) == 0
        assert tally(game, controller=1) == 1

    def test_a_noncreature_does_not_count(self, builder):
        game = position(builder, mine=[ROCK])
        add_counters(game.state, only_oid(game, ROCK, 0), "charge", 1, by=0)
        assert tally(game) == 0
        assert tally(game, {"counters_put_this_turn": {"player": "you"}}) == 1

    def test_a_named_kind_counts_only_that_kind(self, builder):
        game = position(builder, mine=[BEAR])
        add_counters(game.state, only_oid(game, BEAR, 0), "stun", 1, by=0)
        spec = {"counters_put_this_turn": {"player": "you", "counter": "+1/+1"}}
        assert tally(game, spec) == 0
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 2, by=0)
        assert tally(game, spec) == 2

    def test_it_survives_the_counter_and_the_creature_leaving(self, builder):
        """The event happened; the board forgetting it does not undo it."""
        game = position(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, "+1/+1", 1, by=0)
        remove_counters(game.state, bear, "+1/+1", 1)
        move_object(game.state, bear, Zone.GRAVEYARD)
        assert tally(game) == 1

    def test_entering_with_counters_is_putting_them(self, builder):
        """122.6: an object given counters as it enters had them put on it, by
        its controller (122.6a)."""
        game = position(builder, hand=[HYDRA])
        move_object(game.state, in_hand(game, HYDRA), Zone.BATTLEFIELD)
        assert tally(game) == 2


class TestLastingTarfire:
    def test_it_deals_two_to_each_opponent(self, builder):
        game = position(builder, mine=[TARFIRE, BEAR])
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 1, by=0)
        run_through_end_step(game)
        assert game.state.players[1].life == 38
        assert game.state.players[0].life == 40

    def test_nothing_without_a_counter(self, builder):
        game = position(builder, mine=[TARFIRE, BEAR])
        run_through_end_step(game)
        assert game.state.players[1].life == 40

    def test_a_counter_put_before_it_entered_counts(self, builder):
        """The near miss's failure: no trigger of its own was there to see it."""
        game = position(builder, mine=[BEAR], hand=[TARFIRE])
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 1, by=0)
        move_object(game.state, in_hand(game, TARFIRE), Zone.BATTLEFIELD)
        run_through_end_step(game)
        assert game.state.players[1].life == 38

    def test_it_triggers_on_an_opponents_end_step_too(self, builder):
        game = position(builder, mine=[TARFIRE], theirs=[BEAR], active=1)
        add_counters(game.state, only_oid(game, BEAR, 1), "-1/-1", 1, by=0)
        run_through_end_step(game)
        assert game.state.players[1].life == 38

    def test_an_opponents_counter_does_not(self, builder):
        game = position(builder, mine=[TARFIRE, BEAR])
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 1, by=1)
        run_through_end_step(game)
        assert game.state.players[1].life == 40

    def test_the_ledger_clears_at_cleanup(self, builder):
        game = position(builder, mine=[TARFIRE, BEAR])
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 1, by=0)
        run_through_end_step(game)
        pass_until(game, lambda g: g.state.step is not Step.CLEANUP)
        assert tally(game) == 0


class TestTheLoader:
    @pytest.mark.parametrize(
        ("spec", "match"),
        [
            ("you", "must be an object"),
            ({}, "needs 'player'"),
            ({"player": "you", "colors": ["R"]}, "unsupported keys"),
            ({"player": "you", "counter": "Shield"}, "shield counter"),
            ({"player": "you", "types": "Creature"}, "types"),
        ],
    )
    def test_malformed_specs_are_refused(self, spec, match):
        with pytest.raises(DslError, match=match):
            validate_value({"counters_put_this_turn": spec}, "x")

    def test_the_printed_shape_loads(self):
        validate_value(ON_A_CREATURE, "x")
