"""Half of a number, rounded the way the card says.

Peer into the Abyss: "Target player draws cards equal to **half** the number of
cards in their library and loses **half** their life. **Round up** each time."

Rule 107.1a: "If a spell or ability could generate a fractional number, the
spell or ability will tell you whether to round up or down." The value language
had `sum`, `minus`, `times`, `max` and `min` and no division, so ceil(n/2) could
not be built out of it -- and `{"half": {"of": …, "round": …}}` makes the
direction part of the node rather than a default, because both directions are
printed and a default would silently round the other card the wrong way.

The odd numbers are the whole test. An even library passes under floor, ceiling
and truncation alike; a 7-card library is 4 up and 3 down, and that one card is
the difference between the printed spell and a weaker one.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value, validate_value
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from tests.conftest import pass_until

PEER = "t_peer"


def position(builder, *, library: int, life: int):
    """The opponent holds ``library`` cards and ``life`` life; I hold Peer."""
    game = (
        builder(players=2)
        # The Plains and the instant are there to keep priority from being
        # auto-passed on into the opponent's turn, whose draw step would add a
        # card to exactly the hand being counted.
        .battlefield(0, ["swamp", "plains"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * library)
        .hand(0, [PEER, "t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game.state.players[1].life = life
    game._advance()
    return game


def cast_at(game, pid: int) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == PEER
        and a.targets == (TargetRef.player(pid),)
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)


def ctx_for(builder) -> EffectContext:
    return EffectContext(state=builder(players=2).build().state, controller=0)


class TestTheCard:
    def test_an_odd_library_and_an_odd_life_both_round_up(self, builder):
        """7 cards draw 4 (not 3); 25 life loses 13 (not 12)."""
        game = position(builder, library=7, life=25)
        hand = len(game.state.players[1].hand)
        cast_at(game, 1)

        assert len(game.state.players[1].hand) == hand + 4
        assert len(game.state.players[1].library) == 3
        assert game.state.players[1].life == 12

    def test_even_numbers_are_exact(self, builder):
        game = position(builder, library=8, life=20)
        cast_at(game, 1)

        assert len(game.state.players[1].library) == 4
        assert game.state.players[1].life == 10

    def test_one_life_is_lost_entirely(self, builder):
        """Half of 1, rounded up, is the whole of it -- Peer kills at 1."""
        game = position(builder, library=2, life=1)
        cast_at(game, 1)

        assert game.state.players[1].life == 0

    def test_an_empty_library_draws_nothing_and_still_costs_life(self, builder):
        game = position(builder, library=0, life=10)
        cast_at(game, 1)

        assert game.state.players[1].life == 5


class TestTheValue:
    @pytest.mark.parametrize(
        ("n", "up", "down"),
        # A negative life total halves too; `lose_life` then refuses the negative
        # loss, which is 107.1b.
        [(0, 0, 0), (1, 1, 0), (2, 1, 1), (7, 4, 3), (40, 20, 20), (-3, -1, -2)],
    )
    def test_both_directions(self, builder, n, up, down):
        ctx = ctx_for(builder)
        assert evaluate_value(ctx, {"half": {"of": {"const": n}, "round": "up"}}) == up
        assert evaluate_value(ctx, {"half": {"of": {"const": n}, "round": "down"}}) == down

    def test_it_composes(self, builder):
        """Half of a sum, and a half inside a sum -- it is an ordinary value."""
        ctx = ctx_for(builder)
        half_of_sum = {"half": {"of": {"sum": [{"const": 3}, {"const": 4}]}, "round": "up"}}
        assert evaluate_value(ctx, half_of_sum) == 4
        assert evaluate_value(ctx, {"sum": [half_of_sum, {"const": 1}]}) == 5


class TestTheLoaderRefuses:
    def test_a_missing_direction(self):
        with pytest.raises(DslError, match="round"):
            validate_value({"half": {"of": {"const": 3}}}, "amount")

    def test_a_misspelled_direction(self):
        with pytest.raises(DslError, match="round"):
            validate_value({"half": {"of": {"const": 3}, "round": "nearest"}}, "amount")

    def test_nothing_to_halve(self):
        with pytest.raises(DslError, match="of"):
            validate_value({"half": {"round": "up"}}, "amount")

    def test_a_bare_number(self):
        with pytest.raises(DslError, match="object"):
            validate_value({"half": 3}, "amount")

    def test_an_unknown_key(self):
        with pytest.raises(DslError, match="unsupported"):
            validate_value({"half": {"of": 3, "round": "up", "by": 3}}, "amount")

    def test_a_bad_inner_value(self):
        with pytest.raises(DslError, match="unknown value keys"):
            validate_value({"half": {"of": {"thirds": 3}, "round": "up"}}, "amount")
