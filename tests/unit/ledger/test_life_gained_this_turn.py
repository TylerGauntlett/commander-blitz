"""The turn's life-gained tally: "if you gained life this turn".

Witch of the Moors -- "At the beginning of your end step, **if you gained life
this turn**, each opponent sacrifices a creature of their choice and you return
up to one target creature card from your graveyard to your hand" -- is the
witness. It asks about an *event*, which the board cannot answer: a life total
of 42 at the end step says nothing about whether 2 life was gained and 2 lost,
or nothing happened at all, and a total that went down may still hide a gain.

So it is the per-turn ledger's question and is answered the way
`life_lost_this_turn` is: folded in `GameState.emit` off `LIFE_GAINED`, so every
gain the engine makes -- the `gain_life` op, lifelink -- is counted without
anybody remembering to count it, **whatever was on the battlefield when it
happened**. The near miss the gap record names is a `has_turn_flag` set by an
unprinted `you_gain_life` trigger on the Witch, and it is wrong exactly there:
it misses the gain made before the Witch entered, and it is an ability the card
does not print.

Rule 603.4 is the rest of it: an intervening "if" is checked when the trigger
would fire *and* again on resolution, so the value must still be true at the
end step it is read in. The ledger clears at cleanup, after the end step, and
not at untap. And a gain that did not happen -- a locked life total (118.5), or
a player who can't gain life -- fires no event and so is not a gain here either.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects.conditions import evaluate_condition
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value, validate_value
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_player, gain_life, lose_life
from automtg.engine.structs import LifeLock
from tests.conftest import action_for_card, oids_of, pass_until

WITCH = "t_moors_witch"  # your end step, if you gained life this turn: opponents lose 1
EREBOS = "t_erebos"  # Your opponents can't gain life.
LIFELINK_BEAR = "t_lifelink_bear"

GAINED = {"cmp": ">", "left": {"life_gained_this_turn": "you"}, "right": {"const": 0}}


def position(builder, mine=(), theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 2 + list(mine))
        .battlefield(1, ["plains"] * 2 + list(theirs))
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game


def tally(game, who="you", controller=0) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return evaluate_value(ctx, {"life_gained_this_turn": who})


def run_through_end_step(game) -> None:
    """Pass until the end step's triggers have resolved and cleanup has begun."""
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn != turn
        or (g.state.step is Step.CLEANUP and not g.state.stack and not g.state.pending_triggers),
    )


class TestTheLedgerCountsIt:
    def test_a_gain_is_counted_under_the_player_who_gained(self, builder):
        game = position(builder)
        gain_life(game.state, 0, 3)
        assert game.state.turn_ledger.life_gained == {0: 3}

    def test_amounts_accumulate(self, builder):
        game = position(builder)
        gain_life(game.state, 0, 3)
        gain_life(game.state, 0, 2)
        assert tally(game) == 5

    def test_lifelink_is_a_gain(self, builder):
        """702.15b -- a gain nobody writes as `gain_life`, counted by the fold."""
        game = position(builder, mine=[LIFELINK_BEAR])
        damage_player(game.state, 1, 2, oids_of(game, LIFELINK_BEAR)[0])
        assert tally(game) == 2

    def test_a_doubled_gain_counts_what_was_gained(self, builder):
        """The amount the event carries, which is the replaced one."""
        game = position(builder, mine=["t_archive"])
        gain_life(game.state, 0, 3)
        assert tally(game) == 6

    def test_a_loss_is_not_a_gain(self, builder):
        game = position(builder)
        lose_life(game.state, 0, 3)
        assert tally(game) == 0

    def test_a_gain_then_a_loss_still_gained(self, builder):
        """The life total is back where it was; the event still happened."""
        game = position(builder)
        gain_life(game.state, 0, 2)
        lose_life(game.state, 0, 2)
        assert game.state.players[0].life == 40
        assert tally(game) == 2

    def test_it_is_per_player(self, builder):
        game = position(builder)
        gain_life(game.state, 1, 4)
        assert tally(game, "you") == 0
        assert tally(game, "each_opponent") == 4

    def test_zero_is_not_an_entry(self, builder):
        game = position(builder)
        gain_life(game.state, 0, 0)
        assert game.state.turn_ledger.life_gained == {}


class TestAGainThatDidNotHappen:
    def test_a_locked_life_total_gains_nothing(self, builder):
        game = position(builder)
        game.state.life_locks.append(LifeLock(player=0))
        gain_life(game.state, 0, 3)
        assert tally(game) == 0

    def test_a_player_who_cant_gain_life_gained_nothing(self, builder):
        game = position(builder, theirs=[EREBOS])
        gain_life(game.state, 0, 3)
        assert tally(game) == 0


class TestItIsAnOrdinaryCondition:
    def test_the_comparison_turns_on(self, builder):
        game = position(builder)
        assert not evaluate_condition(game.state, GAINED, controller=0)
        gain_life(game.state, 0, 1)
        assert evaluate_condition(game.state, GAINED, controller=0)

    def test_an_unknown_spelling_is_refused(self):
        with pytest.raises(DslError):
            validate_value({"life_gained_last_turn": "you"}, "test")


class TestTheEndStepTrigger:
    """603.4 against a real turn: the Witch's shape, read at its own end step."""

    def test_it_fires_after_a_gain(self, builder):
        game = position(builder, mine=[WITCH])
        gain_life(game.state, 0, 2)
        run_through_end_step(game)
        assert game.state.players[1].life == 39

    def test_it_does_not_fire_without_one(self, builder):
        game = position(builder, mine=[WITCH])
        run_through_end_step(game)
        assert game.state.players[1].life == 40

    def test_a_gain_before_the_witch_arrived_counts(self, builder):
        """The whole reason this is a ledger and not a flag the Witch sets."""
        game = (
            builder(players=2)
            .battlefield(0, ["swamp"] * 5)
            .hand(0, [WITCH])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .life(0, 40)
            .life(1, 40)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        gain_life(game.state, 0, 2)
        game.apply(action_for_card(game, ActionKind.CAST, WITCH))
        pass_until(game, lambda g: not g.state.stack)
        assert oids_of(game, WITCH), "the Witch arrived after the gain"
        run_through_end_step(game)
        assert game.state.players[1].life == 39


class TestItWearsOff:
    def test_the_tally_is_gone_next_turn(self, builder):
        game = position(builder)
        gain_life(game.state, 0, 2)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert tally(game) == 0
