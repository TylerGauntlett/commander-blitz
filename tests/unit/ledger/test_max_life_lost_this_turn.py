"""`max_life_lost_this_turn`: "a player lost N or more life this turn".

Y'shtola, Night's Blessed is the witness: "At the beginning of each end step, if
a player lost 4 or more life this turn, you draw a card." The condition is about
ONE player. `life_lost_this_turn` over `each_player` sums the table, so two
players losing 2 each reads 4 and draws a card the printed one never would.

So this leaf reads each player's total off the same ledger
(`TurnLedger.life_lost`, folded from LIFE_LOST in `GameState.emit`) and takes the
greatest -- the life-loss twin of `max_damage_taken_this_turn`. The claims below
are that it does not sum, that it counts every way life is lost (damage, 119.3;
drains and payments, 119.4) where its damage twin counts only damage, that the
spec decides whose losses count, and that it wears off at cleanup with the rest
of the ledger.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Step
from commanderblitz.engine.primitives import damage_player, lose_life

#: Y'shtola's intervening-if, as the card writes it.
YSHTOLA = {
    "cmp": ">=",
    "left": {"max_life_lost_this_turn": "each_player"},
    "right": {"const": 4},
}


def position(builder, players: int = 4):
    """A frozen main phase at a pod, with nothing having happened yet."""
    game = (
        builder(players=players)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    for p in game.state.players:
        p.life = 40
    return game


def draws(game) -> bool:
    return evaluate_condition(game.state, YSHTOLA, controller=0)


def value(game, expr) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=0), expr)


class TestOnePlayerNotTheTable:
    def test_loss_spread_across_players_does_not_add_up(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 2)
        lose_life(game.state, 2, 2)
        assert value(game, {"life_lost_this_turn": "each_player"}) == 4, (
            "the summing tally is the near miss this leaf exists beside"
        )
        assert value(game, {"max_life_lost_this_turn": "each_player"}) == 2
        assert not draws(game), "no single player lost 4"

    def test_one_player_reaching_the_threshold_opens_it(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 1)
        lose_life(game.state, 3, 4)
        assert value(game, {"max_life_lost_this_turn": "each_player"}) == 4
        assert draws(game)

    def test_one_below_the_threshold_does_not(self, builder):
        game = position(builder)
        lose_life(game.state, 2, 3)
        assert not draws(game)

    def test_one_players_losses_accumulate(self, builder):
        game = position(builder)
        lose_life(game.state, 2, 1)
        lose_life(game.state, 2, 3)
        assert draws(game), "1 then 3 from the same player is 4 this turn"


class TestWhatCounts:
    def test_damage_is_life_lost(self, builder):
        """119.3: damage to a player causes that much life loss."""
        game = position(builder)
        damage_player(game.state, 1, 4, None)
        assert value(game, {"max_life_lost_this_turn": "each_player"}) == 4
        assert draws(game)

    def test_damage_and_a_drain_to_one_player_add_up(self, builder):
        game = position(builder)
        damage_player(game.state, 1, 2, None)
        lose_life(game.state, 1, 2)
        assert draws(game)

    def test_a_drain_is_life_lost_but_not_damage(self, builder):
        """Where it parts from its damage twin: a drain deals no damage."""
        game = position(builder)
        lose_life(game.state, 1, 5)
        assert value(game, {"max_damage_taken_this_turn": "each_player"}) == 0
        assert value(game, {"max_life_lost_this_turn": "each_player"}) == 5

    def test_your_own_loss_counts_for_each_player(self, builder):
        """"A player" includes you: paying 4 life opens Y'shtola's draw."""
        game = position(builder)
        lose_life(game.state, 0, 4)
        assert draws(game)
        assert value(game, {"max_life_lost_this_turn": "each_opponent"}) == 0

    def test_nothing_happened_reads_zero(self, builder):
        game = position(builder)
        assert value(game, {"max_life_lost_this_turn": "each_player"}) == 0

    def test_a_single_seat_spec_agrees_with_the_summing_tally(self, builder):
        game = position(builder)
        lose_life(game.state, 0, 3)
        lose_life(game.state, 1, 6)
        mine = value(game, {"max_life_lost_this_turn": "you"})
        assert mine == value(game, {"life_lost_this_turn": "you"}) == 3


class TestWearingOff:
    def test_the_ledger_clearing_at_cleanup_closes_it(self, builder):
        game = position(builder)
        lose_life(game.state, 1, 4)
        assert draws(game)
        game.state.turn_ledger.clear()
        assert not draws(game), "last turn's loss is not this turn's"


class TestLoading:
    def test_it_is_a_known_value_key(self):
        validate_value({"max_life_lost_this_turn": "each_player"}, "test")

    def test_a_misspelling_is_refused(self):
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError):
            validate_value({"max_life_loss_this_turn": "each_player"}, "test")
