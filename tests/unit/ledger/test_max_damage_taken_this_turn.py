"""`max_damage_taken_this_turn`: "an opponent was dealt N or more damage this turn".

Spinerock Knoll is the witness: "{R}, {T}: You may play the exiled card without
paying its mana cost if an opponent was dealt 7 or more damage this turn." The
condition is about ONE opponent. `damage_taken_this_turn` over `each_opponent`
sums the table, which is the printed card in a duel and a strictly better one at
a pod -- 4 damage to each of two opponents reads 8 and opens a hideaway no single
opponent's total reached.

So this leaf reads each player's total off the same ledger
(`TurnLedger.damage_taken`, folded in `GameState.emit`) and takes the greatest:
the existential, as `min_life_of` is for "an opponent has N or less life". The
claims below are that it does not sum, that it does not count you, that it reads
damage rather than life loss (120.3a: damage causes life loss, never the
reverse), and that it wears off at cleanup with the rest of the ledger.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Step
from commanderblitz.engine.primitives import damage_player, lose_life

#: Spinerock Knoll's condition, as the card writes it.
KNOLL = {
    "cmp": ">=",
    "left": {"max_damage_taken_this_turn": "each_opponent"},
    "right": {"const": 7},
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


def knoll_open(game) -> bool:
    return evaluate_condition(game.state, KNOLL, controller=0)


def value(game, expr) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=0), expr)


class TestOnePlayerNotTheTable:
    def test_damage_spread_across_opponents_does_not_add_up(self, builder):
        game = position(builder)
        damage_player(game.state, 1, 4, None)
        damage_player(game.state, 2, 4, None)
        assert value(game, {"damage_taken_this_turn": "each_opponent"}) == 8, (
            "the summing tally is the near miss this leaf exists beside"
        )
        assert value(game, {"max_damage_taken_this_turn": "each_opponent"}) == 4
        assert not knoll_open(game), "no single opponent was dealt 7"

    def test_one_opponent_reaching_the_threshold_opens_it(self, builder):
        game = position(builder)
        damage_player(game.state, 1, 3, None)
        damage_player(game.state, 2, 7, None)
        assert value(game, {"max_damage_taken_this_turn": "each_opponent"}) == 7
        assert knoll_open(game)

    def test_one_below_the_threshold_does_not(self, builder):
        game = position(builder)
        damage_player(game.state, 3, 6, None)
        assert not knoll_open(game)

    def test_one_opponents_damage_accumulates_across_sources(self, builder):
        game = position(builder)
        damage_player(game.state, 2, 3, None)
        damage_player(game.state, 2, 4, None)
        assert knoll_open(game), "3 then 4 to the same opponent is 7 this turn"


class TestWhatCounts:
    def test_damage_to_you_is_not_an_opponent(self, builder):
        game = position(builder)
        damage_player(game.state, 0, 10, None)
        assert value(game, {"max_damage_taken_this_turn": "each_opponent"}) == 0
        assert value(game, {"max_damage_taken_this_turn": "each_player"}) == 10
        assert not knoll_open(game)

    def test_life_loss_without_damage_is_not_damage(self, builder):
        """A drain costs life and deals no damage; the card says *dealt damage*."""
        game = position(builder)
        lose_life(game.state, 1, 9)
        assert not knoll_open(game)

    def test_nothing_happened_reads_zero(self, builder):
        game = position(builder)
        assert value(game, {"max_damage_taken_this_turn": "each_opponent"}) == 0

    def test_a_duel_agrees_with_the_summing_tally(self, builder):
        game = position(builder, players=2)
        damage_player(game.state, 1, 7, None)
        assert value(game, {"max_damage_taken_this_turn": "each_opponent"}) == value(
            game, {"damage_taken_this_turn": "each_opponent"}
        )
        assert knoll_open(game)


class TestWearingOff:
    def test_the_ledger_clearing_at_cleanup_closes_it(self, builder):
        game = position(builder)
        damage_player(game.state, 1, 7, None)
        assert knoll_open(game)
        game.state.turn_ledger.clear()
        assert not knoll_open(game), "last turn's damage is not this turn's"


class TestLoading:
    def test_it_is_a_known_value_key(self):
        validate_value({"max_damage_taken_this_turn": "each_opponent"}, "test")

    def test_a_misspelling_is_refused(self):
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError):
            validate_value({"max_damage_dealt_this_turn": "each_opponent"}, "test")
