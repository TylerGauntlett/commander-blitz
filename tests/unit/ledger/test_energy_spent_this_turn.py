"""`energy_spent_this_turn`: "{E} you've paid or lost this turn".

Energy is a counter on a player (107.14, 122.1), and two printed cards ask how
much of it went away this turn rather than how much is left: Blaster Hulk
("This spell costs {1} less to cast for each {E} you've paid or lost this
turn") and Izzet Generatorium ("Activate only if you've paid or lost four or
more {E} this turn"). Neither is answerable from `Player.energy`: getting
{E}{E} and paying {E}{E} leaves the total where it was, and the Hulk would cost
what it prints after the payment that was meant to discount it.

So the ledger keeps `TurnLedger.energy_spent`, folded in `GameState.emit` off
ENERGY_PAID (a `pay_energy` cost) and off a COUNTER_REMOVED of a *player's*
energy (`lose_all_player_counters`). The claims below are that both count and
add up, that getting energy offsets nothing, that a permanent's counters and
another player's energy are not yours, that the one tally reaches both an
activation restriction (602.5c) and a card-level `cost_reduction` (601.2f), and
that it wears off at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import (
    add_counters,
    add_energy,
    pay_energy,
    remove_counters,
    remove_player_counters,
)
from tests.conftest import activations, cost_reduction_probe, only_oid, settle

HULK = "t_es_hulk"  # {4}{R}, {1} less per {E} you paid or lost this turn
GENERATORIUM = "t_es_generatorium"  # {T}: draw, only after four {E} paid or lost
CELL = "t_energy_cell"  # Pay {E}{E}: draw a card
SPENT = {"energy_spent_this_turn": "you"}


def position(builder, *, energy: int = 9, mine=(), hand=(), players: int = 2):
    """Player 0's precombat main phase, with ``energy`` each and nothing spent.

    Energy is set *before* the build advances, and an Energy Cell is always on
    the battlefield, so player 0 has an activation to make and the auto-pass
    stops at their priority instead of rolling the turn on.
    """
    b = (
        builder(players=players)
        .battlefield(0, [CELL, *mine])
        .hand(0, list(hand))
        .library(0, ["forest"] * 5)
        .active(0)
    )
    for p in b.state.players:
        p.energy = energy
    game = b.build()
    assert game.state.turn_ledger.energy_spent == {}
    return game


def spent(game, who="you", pid: int = 0) -> int:
    return evaluate_value(
        EffectContext(state=game.state, controller=pid), {"energy_spent_this_turn": who}
    )


def can_cast(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


class TestWhatCounts:
    def test_nothing_spent_reads_zero(self, builder):
        assert spent(position(builder, energy=6)) == 0

    def test_a_payment_counts(self, builder):
        game = position(builder, energy=6)
        pay_energy(game.state, 0, 3)
        assert spent(game) == 3

    def test_a_loss_counts(self, builder):
        """"Paid **or lost**": energy an effect takes away is counted too --
        Final Act's "each opponent loses all counters", aimed at you."""
        game = position(builder, energy=5)
        ctx = EffectContext(state=game.state, controller=1)
        for _ in execute(ctx, [{"op": "lose_all_player_counters", "player": "each_opponent"}]):
            raise AssertionError("lose_all_player_counters asks no question")
        assert game.state.players[0].energy == 0
        assert spent(game) == 5

    def test_payments_and_losses_add_up(self, builder):
        game = position(builder, energy=6)
        pay_energy(game.state, 0, 2)
        remove_player_counters(game.state, 0, "energy", 4)
        assert spent(game) == 6

    def test_a_loss_counts_what_came_off_not_what_was_asked(self, builder):
        game = position(builder, energy=2)
        remove_player_counters(game.state, 0, "energy", 9)
        assert spent(game) == 2

    def test_getting_energy_offsets_nothing(self, builder):
        """The total is the near miss: get two, pay two, and it has not moved."""
        game = position(builder, energy=2)
        add_energy(game.state, 0, 2)
        pay_energy(game.state, 0, 2)
        assert game.state.players[0].energy == 2
        assert spent(game) == 2

    def test_losing_poison_is_not_energy(self, builder):
        game = position(builder)
        game.state.players[0].poison = 3
        remove_player_counters(game.state, 0, "poison", 3)
        assert spent(game) == 0

    def test_a_permanents_counters_are_not_a_players_energy(self, builder):
        game = position(builder)
        oid = only_oid(game, CELL)
        add_counters(game.state, oid, "energy", 3)
        remove_counters(game.state, oid, "energy", 3)
        assert spent(game) == 0

    def test_an_opponents_spending_is_not_yours(self, builder):
        game = position(builder, energy=5, players=4)
        pay_energy(game.state, 1, 4)
        remove_player_counters(game.state, 2, "energy", 5)
        assert spent(game) == 0
        assert spent(game, "each_opponent") == 9

    def test_the_real_cost_is_counted(self, builder):
        """Through `Game.apply`, as a `pay_energy` cost is paid on activation."""
        game = position(builder, energy=5)
        game.apply(activations(game, only_oid(game, CELL))[0])
        settle(game)
        assert spent(game) == 2


class TestTheActivationRestriction:
    """Izzet Generatorium: "Activate only if you've paid or lost four or more {E}"."""

    def test_three_is_not_enough(self, builder):
        game = position(builder, energy=9, mine=[GENERATORIUM])
        pay_energy(game.state, 0, 3)
        assert not activations(game, only_oid(game, GENERATORIUM))

    def test_four_opens_it(self, builder):
        game = position(builder, energy=9, mine=[GENERATORIUM])
        pay_energy(game.state, 0, 3)
        remove_player_counters(game.state, 0, "energy", 1)
        assert activations(game, only_oid(game, GENERATORIUM))

    def test_having_four_is_not_having_paid_four(self, builder):
        game = position(builder, energy=9, mine=[GENERATORIUM])
        assert not activations(game, only_oid(game, GENERATORIUM))


class TestTheCostReduction:
    """Blaster Hulk: "{1} less to cast for each {E} you've paid or lost"."""

    def test_the_discount_is_the_energy_spent(self, registry, builder):
        game = position(builder, energy=6)
        pay_energy(game.state, 0, 3)
        assert cost_reduction(game.state, 0, registry.get(HULK)) == 3

    def test_only_the_casters_spending_discounts_it(self, registry, builder):
        game = position(builder, energy=6)
        pay_energy(game.state, 1, 4)
        assert cost_reduction(game.state, 0, registry.get(HULK)) == 0
        assert cost_reduction(game.state, 1, registry.get(HULK)) == 4

    def test_it_never_touches_the_coloured_pip(self, builder):
        """{4}{R} minus four is {R}: one Mountain casts it, and not before."""
        game = position(builder, energy=4, mine=["mountain"], hand=[HULK])
        assert not can_cast(game, HULK)
        pay_energy(game.state, 0, 4)
        assert can_cast(game, HULK)

    def test_more_than_the_generic_is_still_the_pip(self, builder):
        game = position(builder, energy=9, mine=["mountain"], hand=[HULK])
        pay_energy(game.state, 0, 9)
        assert can_cast(game, HULK)


class TestWearingOff:
    def test_the_ledger_clearing_at_cleanup_closes_it(self, registry, builder):
        game = position(builder, energy=9, mine=[GENERATORIUM])
        pay_energy(game.state, 0, 4)
        assert activations(game, only_oid(game, GENERATORIUM))
        game.state.turn_ledger.clear()
        assert spent(game) == 0
        assert not activations(game, only_oid(game, GENERATORIUM))
        assert cost_reduction(game.state, 0, registry.get(HULK)) == 0


class TestLoading:
    def test_it_is_a_known_value_key(self):
        validate_value(SPENT, "test")

    def test_the_value_needs_a_player_spec(self):
        with pytest.raises(DslError, match="energy_spent_this_turn"):
            validate_value({"energy_spent_this_turn": 3}, "test")

    def test_the_reduction_needs_a_player_spec(self):
        with pytest.raises(DslError, match="energy_spent_this_turn"):
            compile_card(cost_reduction_probe({"energy_spent_this_turn": "nobody"}))

    def test_the_reduction_refuses_a_second_head(self):
        with pytest.raises(DslError):
            compile_card(
                cost_reduction_probe({"energy_spent_this_turn": "you", "count": {}})
            )
