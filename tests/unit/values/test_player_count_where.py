""""The number of **opponents who control more creatures than you**" -- a
headcount of the players whose own count passes a comparison.

Heidegger, Shinra Executive: "create a number of 1/1 white Soldier creature
tokens equal to the number of opponents who control more creatures than you".
`player_count` counted every seat a spec named, with no test; `max_count_of`
and `min_count_of` answer "an opponent" and "each opponent", the existential
and the universal, but never *how many*. The near miss, a `for_each_player`
with an `if` and a `create_token` of one, is a different card twice over: the
tokens arrive in separate events, and each token made raises your creature
count before the next opponent is compared, so at a pod the later opponents
are measured against a board the card never saw.

The comparing form of `player_count` takes `max_count_of`'s per-player count
(`player` + `objects`, the pool scoped to one player at a time) and a `cmp`
against `than`, which is read **once**. It is one value, so it is the amount of
one `create_token` and the headcount is taken at one moment.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError
from tests.conftest import battlefield_ids

BEAR = "t_bear"  # vanilla 2/2

#: Heidegger's X.
MORE_CREATURES_THAN_YOU = {
    "player_count": {
        "player": "each_opponent",
        "objects": {"types": ["Creature"]},
        "cmp": ">",
        "than": {"count": {"types": ["Creature"], "controller": "you"}},
    }
}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def pod(builder, *creatures: int):
    """A table where seat ``i`` controls ``creatures[i]`` Bears."""
    b = builder(players=len(creatures))
    for pid, n in enumerate(creatures):
        b = b.battlefield(pid, [BEAR] * n)
    return b.build(advance=False)


class TestItCountsThePlayersWhoPass:
    def test_only_the_opponents_with_more(self, builder):
        assert value(pod(builder, 2, 3, 1, 4), MORE_CREATURES_THAN_YOU) == 2

    def test_equal_is_not_more(self, builder):
        assert value(pod(builder, 2, 2, 2, 2), MORE_CREATURES_THAN_YOU) == 0

    def test_every_opponent_ahead(self, builder):
        assert value(pod(builder, 0, 1, 1, 1), MORE_CREATURES_THAN_YOU) == 3

    def test_each_opponent_is_measured_alone_not_summed(self, builder):
        """Three opponents on one Bear each total three, which beats your two;
        none of them alone does."""
        assert value(pod(builder, 2, 1, 1, 1), MORE_CREATURES_THAN_YOU) == 0

    def test_it_reads_from_the_controllers_seat(self, builder):
        game = pod(builder, 2, 3, 1, 4)
        assert value(game, MORE_CREATURES_THAN_YOU, controller=2) == 3

    def test_the_comparison_is_the_cards(self, builder):
        at_least = {
            "player_count": {**MORE_CREATURES_THAN_YOU["player_count"], "cmp": ">="}
        }
        assert value(pod(builder, 2, 2, 1, 3), at_least) == 2


class TestAPlayerWhoLeftIsNotCounted:
    def test_an_eliminated_opponent_drops_out(self, builder):
        game = pod(builder, 0, 1, 1, 1)
        game.state.players[3].has_lost = True
        assert value(game, MORE_CREATURES_THAN_YOU) == 2


class TestItIsOneBatchedCreateToken:
    def test_the_tokens_come_from_one_headcount(self, builder):
        """Two opponents with two Bears against your one: X is 2. Counted one
        token at a time, the first token would bring you level and the second
        opponent would no longer be ahead."""
        game = pod(builder, 1, 2, 2)
        effect = {"op": "create_token", "token": "soldier_1_1_w",
                  "amount": MORE_CREATURES_THAN_YOU}
        list(execute(EffectContext(state=game.state, controller=0), [effect]))
        assert battlefield_ids(game, 0).count("soldier_1_1_w") == 2


class TestTheLoaderGuardsIt:
    def test_the_witness_shape_validates(self):
        validate_value(MORE_CREATURES_THAN_YOU, "probe")

    def test_the_plain_seat_spec_still_validates(self):
        validate_value({"player_count": "each_opponent"}, "probe")

    @pytest.mark.parametrize("op", [None, "more", "=>"])
    def test_an_unknown_comparison_is_refused(self, op):
        spec = dict(MORE_CREATURES_THAN_YOU["player_count"])
        if op is None:
            del spec["cmp"]
        else:
            spec["cmp"] = op
        with pytest.raises(DslError, match=r"player_count\.cmp"):
            validate_value({"player_count": spec}, "probe")

    def test_than_is_required(self):
        """Defaulted to 0, "more creatures than you" would be "any creatures"."""
        spec = {k: v for k, v in MORE_CREATURES_THAN_YOU["player_count"].items() if k != "than"}
        with pytest.raises(DslError, match="needs 'than'"):
            validate_value({"player_count": spec}, "probe")

    def test_an_injected_controller_is_refused(self):
        spec = dict(MORE_CREATURES_THAN_YOU["player_count"])
        spec["objects"] = {"types": ["Creature"], "controller": "opponent"}
        with pytest.raises(DslError, match="injected per player"):
            validate_value({"player_count": spec}, "probe")

    def test_a_bad_than_is_refused(self):
        spec = {**MORE_CREATURES_THAN_YOU["player_count"], "than": {"nonsense": 1}}
        with pytest.raises(DslError):
            validate_value({"player_count": spec}, "probe")
