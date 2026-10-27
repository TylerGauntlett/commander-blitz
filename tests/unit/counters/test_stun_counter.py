"""Stun counters -- 122.1d, a replacement of untapping that lives on a counter.

    Pugnacious Hammerskull -- "Whenever this creature attacks while you don't
    control another Dinosaur, put a stun counter on it. (If a permanent with a
    stun counter would become untapped, remove one from it instead.)"

Counter kinds are free strings, so the trigger half always loaded: an
`add_counters` naming "stun". Without the replacement the counter is an inert
tally and the Hammerskull's drawback vanishes -- a strictly better card that
passes every authoring gate, which is why this is a unit test.

The rule names no cause: "would become untapped" is the untap step, an untap
effect and an {Q} cost alike, so all three go through
`primitives.untap_or_stun` rather than writing ``tapped = False``. One counter
per untap, and a permanent that is already untapped is not "becoming" untapped,
so its counter waits.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import validate_counter_kind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import STUN
from commanderblitz.engine.primitives import add_counters, untap_all, untap_permanent

BEAR = "t_bear"


def stunned(builder, counters: int = 1, *, tapped: bool = True):
    game = (
        builder(players=2)
        .battlefield(0, ["forest", BEAR])
        .library(0, ["forest"] * 5)
        .build(advance=False)
    )
    bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
    obj = game.state.objects[bear]
    obj.tapped = tapped
    add_counters(game.state, bear, STUN, counters)
    return game, obj


class TestTheUntapStep:
    def test_a_stun_counter_is_removed_instead(self, builder):
        game, obj = stunned(builder)

        untap_all(game.state, 0)

        assert obj.tapped
        assert obj.counter(STUN) == 0

    def test_the_next_untap_step_untaps_it(self, builder):
        game, obj = stunned(builder)

        untap_all(game.state, 0)
        untap_all(game.state, 0)

        assert not obj.tapped

    def test_one_counter_per_untap(self, builder):
        game, obj = stunned(builder, 2)

        untap_all(game.state, 0)

        assert obj.tapped
        assert obj.counter(STUN) == 1

    def test_the_rest_of_the_board_still_untaps(self, builder):
        game, _ = stunned(builder)
        forest = next(o for o in game.state.battlefield_objects(0) if o.def_id == "forest")
        forest.tapped = True

        untap_all(game.state, 0)

        assert not forest.tapped


class TestAnyUntap:
    def test_an_untap_effect_spends_a_counter_instead(self, builder):
        game, obj = stunned(builder)

        assert not untap_permanent(game.state, obj.oid)
        assert obj.tapped
        assert obj.counter(STUN) == 0

    def test_the_untap_op(self, builder):
        game, obj = stunned(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=obj.oid)

        for _ in execute_one(ctx, {"op": "untap", "objects": {"self_only": True}}):
            pass

        assert obj.tapped
        assert obj.counter(STUN) == 0

    def test_an_untapped_permanent_keeps_its_counter(self, builder):
        """Nothing "would become untapped", so nothing is replaced."""
        game, obj = stunned(builder, tapped=False)

        untap_all(game.state, 0)
        untap_permanent(game.state, obj.oid)

        assert obj.counter(STUN) == 1


class TestTheSpellingIsExact:
    def test_a_near_miss_is_refused(self):
        validate_counter_kind("stun", "probe")
        for near in ("Stun", "stun counter", "stun counters"):
            with pytest.raises(DslError, match="stun counter"):
                validate_counter_kind(near, "probe")
