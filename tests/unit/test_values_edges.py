"""The value language's edges: the forms the card pool never happens to use.

`values.py` is 89% covered by the cards that exist, and the missing tenth is
almost entirely the refusals -- the `DslError` a malformed card file gets at
load time -- plus four evaluation forms no shipped card reaches. A refusal
that nobody has ever triggered is a refusal whose message nobody has ever
read, so each one is exercised once here (TECH_DEBT CG-06's neighbour).
"""

from __future__ import annotations

import pytest

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import (
    evaluate_value,
    validate_counter_kind,
    validate_counters_on,
    validate_entered_filter,
    validate_mana_symbols,
    validate_per_player_count,
    validate_rolled,
    validate_value,
)
from automtg.engine.errors import DslError


@pytest.fixture
def ctx(builder) -> EffectContext:
    game = builder(players=2).build()
    game.state.players[0].life = 40
    game.state.players[1].life = 25
    return EffectContext(state=game.state, controller=0, x=3)


class TestEvaluate:
    def test_the_scalar_forms(self, ctx):
        assert evaluate_value(ctx, None) == 0
        assert evaluate_value(ctx, True) == 1
        assert evaluate_value(ctx, 7) == 7
        assert evaluate_value(ctx, "x") == 3
        assert evaluate_value(ctx, {"x": True}) == 3
        assert evaluate_value(ctx, {"const": "4"}) == 4

    def test_a_string_that_is_not_x_is_refused(self, ctx):
        with pytest.raises(DslError, match="unparsable value expression"):
            evaluate_value(ctx, "all")
        with pytest.raises(DslError, match="unparsable value expression"):
            evaluate_value(ctx, [1, 2])

    def test_loop_value_reads_the_for_each_iteration(self, ctx):
        assert evaluate_value(ctx, {"loop_value": True}) == 0
        ctx.loop_value = 5
        assert evaluate_value(ctx, {"loop_value": True}) == 5

    def test_life_of_sums_and_max_life_of_takes_the_highest(self, ctx):
        assert evaluate_value(ctx, {"life_of": "you"}) == 40
        assert evaluate_value(ctx, {"life_of": "each_opponent"}) == 25
        assert evaluate_value(ctx, {"life_of": "each_player"}) == 65
        assert evaluate_value(ctx, {"max_life_of": "each_player"}) == 40
        assert evaluate_value(ctx, {"max_life_of": "each_opponent"}) == 25

    def test_toughness_had_reads_the_trigger_snapshot_or_zero(self, ctx):
        assert evaluate_value(ctx, {"toughness_had": True}) == 0
        ctx.bindings["had_toughness"] = 4
        assert evaluate_value(ctx, {"toughness_had": True}) == 4

    def test_max_and_min_over_sub_expressions(self, ctx):
        assert evaluate_value(ctx, {"max": [1, {"const": 9}, "x"]}) == 9
        assert evaluate_value(ctx, {"min": [1, {"const": 9}, "x"]}) == 1
        assert evaluate_value(ctx, {"max": []}) == 0
        assert evaluate_value(ctx, {"min": []}) == 0

    def test_an_unknown_form_is_refused_by_name(self, ctx):
        with pytest.raises(DslError, match=r"unknown value expression \['vibes'\]"):
            evaluate_value(ctx, {"vibes": 1})


class TestValidateValue:
    def test_the_accepted_scalars(self):
        for expr in (None, 0, True, "x", {"const": 1}, {"x": True}):
            validate_value(expr, "t")

    def test_the_refused_scalars(self):
        with pytest.raises(DslError, match="unparsable value 'y'"):
            validate_value("y", "t")
        with pytest.raises(DslError, match="value must be an int or object, got list"):
            validate_value([1], "t")
        with pytest.raises(DslError, match="unknown value keys"):
            validate_value({"vibes": 1}, "t")

    def test_the_list_forms_take_lists_and_check_each_entry(self):
        with pytest.raises(DslError, match="sum takes a list"):
            validate_value({"sum": 3}, "t")
        with pytest.raises(DslError, match=r"t\.max\[1\]: unparsable value 'q'"):
            validate_value({"max": [1, "q"]}, "t")
        validate_value({"min": [1, {"const": 2}]}, "t")

    def test_distinct_must_be_an_object(self):
        with pytest.raises(DslError, match=r"t\.distinct: must be an object"):
            validate_value({"distinct": 3}, "t")


class TestTheLeafValidators:
    def test_mana_symbols(self):
        with pytest.raises(DslError, match="must be an object"):
            validate_mana_symbols(3, "t")
        with pytest.raises(DslError, match="unsupported keys"):
            validate_mana_symbols({"of": "G", "colour": "G"}, "t")
        with pytest.raises(DslError, match="must name a colour"):
            validate_mana_symbols({"of": "Q"}, "t")

    def test_counter_kinds(self):
        validate_counter_kind("+1/+1", "t")
        with pytest.raises(DslError, match="non-empty string"):
            validate_counter_kind("", "t")
        with pytest.raises(DslError, match="non-empty string"):
            validate_counter_kind(3, "t")

    def test_counters_on_and_per_player_counts_must_be_objects(self):
        with pytest.raises(DslError, match="must be an object"):
            validate_counters_on("charge", "t")
        with pytest.raises(DslError, match="must be an object"):
            validate_per_player_count(3, "t")
        with pytest.raises(DslError, match="unsupported keys"):
            validate_per_player_count({"vibes": 1}, "t")

    def test_rolled_and_entered_filters(self):
        with pytest.raises(DslError, match="naming the roll's binding"):
            validate_rolled("d20", "t")
        with pytest.raises(DslError, match="filter on what entered"):
            validate_entered_filter(3, "t")
        with pytest.raises(DslError, match="must name one of"):
            validate_entered_filter({"types": ["Creature"]}, "t")
        with pytest.raises(DslError, match="every entry must be a name"):
            validate_entered_filter({"controller": "you", "types": [1]}, "t")
        validate_entered_filter({"controller": "you", "types": ["Creature"]}, "t")
