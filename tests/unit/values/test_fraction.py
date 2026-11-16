"""A value divided by any printed divisor, rounded the way the card says.

Dire Fleet Ravager: "When this creature enters, each player loses **a third**
of their life, **rounded up**." Legate Lanius: "each opponent sacrifices **a
tenth** of the creatures they control …, rounded up."

Rule 107.1a: a fractional result is rounded the way the card says. `half` is
fixed at a divisor of 2, and `sum`, `minus`, `times`, `min` and `max` cannot
build ceil(n/3) for every n, so without `fraction` a third of a life total had
no spelling. The remainders are the whole test: 30 life is a third under any
rounding, 40 is 14 up and 13 down.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError


def ctx_for(builder, lives=(40, 40)) -> EffectContext:
    game = builder(players=len(lives)).build()
    for pid, life in enumerate(lives):
        game.state.players[pid].life = life
    return EffectContext(state=game.state, controller=0)


def third(of, direction="up"):
    return {"fraction": {"of": of, "divisor": 3, "round": direction}}


class TestTheValue:
    @pytest.mark.parametrize(
        ("n", "divisor", "up", "down"),
        [(0, 3, 0, 0), (1, 3, 1, 0), (30, 3, 10, 10), (40, 3, 14, 13), (11, 10, 2, 1), (10, 10, 1, 1), (-4, 3, -1, -2)],
    )
    def test_both_directions(self, builder, n, divisor, up, down):
        ctx = ctx_for(builder)
        for direction, want in (("up", up), ("down", down)):
            spec = {"fraction": {"of": {"const": n}, "divisor": divisor, "round": direction}}
            assert evaluate_value(ctx, spec) == want

    def test_it_composes(self, builder):
        ctx = ctx_for(builder)
        assert evaluate_value(ctx, third({"sum": [{"const": 3}, {"const": 4}]})) == 3
        assert evaluate_value(ctx, {"sum": [third({"const": 7}), {"const": 1}]}) == 4


class TestEachPlayersOwnThird:
    def test_each_seat_is_a_third_of_its_own_total(self, builder):
        """The Ravager's amount, bound per seat: 40 is 14, 20 is 7, 1 is all of it."""
        ctx = ctx_for(builder, lives=(40, 20, 1))
        amount = third({"life_of": {"binding": "each_player"}})
        got = []
        for pid in range(3):
            ctx.bindings["each_player"] = pid
            got.append(evaluate_value(ctx, amount))
        assert got == [14, 7, 1]


class TestTheLoaderRefuses:
    def test_a_divisor_of_two_is_half(self):
        with pytest.raises(DslError, match="half"):
            validate_value({"fraction": {"of": {"const": 3}, "divisor": 2, "round": "up"}}, "amount")

    @pytest.mark.parametrize("divisor", [None, 0, 1, -3, 3.0, True, {"const": 3}])
    def test_a_divisor_that_is_not_a_literal_of_three_or_more(self, divisor):
        spec = {"of": {"const": 3}, "round": "up"}
        if divisor is not None:
            spec["divisor"] = divisor
        with pytest.raises(DslError, match="divisor"):
            validate_value({"fraction": spec}, "amount")

    def test_a_missing_direction(self):
        with pytest.raises(DslError, match="round"):
            validate_value({"fraction": {"of": {"const": 3}, "divisor": 3}}, "amount")

    def test_nothing_to_divide(self):
        with pytest.raises(DslError, match="of"):
            validate_value({"fraction": {"divisor": 3, "round": "up"}}, "amount")

    def test_a_bare_number(self):
        with pytest.raises(DslError, match="object"):
            validate_value({"fraction": 3}, "amount")

    def test_an_unknown_key(self):
        with pytest.raises(DslError, match="unsupported"):
            validate_value({"fraction": {"of": 3, "divisor": 3, "round": "up", "by": 3}}, "amount")
