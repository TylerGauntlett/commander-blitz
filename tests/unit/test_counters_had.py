"""Persist and undying: reading counters off a creature that has just died.

The census had both as `routed` with the gap named wrongly — "a dies-trigger
return with a counter; the 'if it had none' gate is `counters_on`". Every piece
of that exists, and the card still could not be written, because `counters_on`
reads a **live object** and `reset_permanent_state` empties `counters` on the
way to the graveyard. Asked after the death it is always zero, so both keywords
would return every creature for ever and the loop guard printed on the card
would do nothing at all.

That is the engine's explicit-LKI pattern, and `zones.move_object` already had
two instances of it: `was_creature` and `was_attacking` are both snapshotted
before the wipe for exactly this reason. `had_counters` is the third, and
`{"counters_had": "-1/-1"}` reads it out of the trigger's bindings.

The counter on the way back is not decoration either. It *is* the loop guard:
persist returns the creature with a -1/-1 counter precisely so that the next
death fails the "if it had none" test. A version that returned it clean would
recur until `RulesLoopError`.
"""

from __future__ import annotations

import pytest

from automtg.engine.enums import Zone
from automtg.engine.errors import DslError
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, only_oid

PERSISTER = "t_persister"  # 3/3, persist


def settle(game, limit: int = 40) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


def position(builder):
    game = builder(players=2).battlefield(0, [PERSISTER]).build()
    return game, only_oid(game, PERSISTER, 0)


class TestPersist:
    def test_it_comes_back(self, builder):
        game, oid = position(builder)
        move_object(game.state, oid, Zone.GRAVEYARD)
        settle(game)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_it_comes_back_with_a_counter(self, builder):
        game, oid = position(builder)
        move_object(game.state, oid, Zone.GRAVEYARD)
        settle(game)
        assert game.state.objects[oid].counter("-1/-1") == 1

    def test_it_does_not_come_back_twice(self, builder):
        """The loop guard, and the reason the counter is not decoration.

        Without the snapshot this test is the one that hangs: the second death
        reads zero counters, persists again, and the creature recurs until the
        trigger loop guard scores the game a draw.
        """
        game, oid = position(builder)
        move_object(game.state, oid, Zone.GRAVEYARD)
        settle(game)
        assert game.state.objects[oid].counter("-1/-1") == 1
        move_object(game.state, oid, Zone.GRAVEYARD)
        settle(game)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD, (
            "it had a -1/-1 counter, so persist did not fire"
        )

    def test_a_creature_that_dies_with_a_counter_never_persists(self, builder):
        game, oid = position(builder)
        game.state.objects[oid].add_counter("-1/-1", 1)
        move_object(game.state, oid, Zone.GRAVEYARD)
        settle(game)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestTheSnapshotIsWhatMakesItWork:
    def test_the_dies_event_carries_the_counters(self, builder):
        from automtg.engine.events import EventType

        game, oid = position(builder)
        game.state.objects[oid].add_counter("+1/+1", 2)
        move_object(game.state, oid, Zone.GRAVEYARD)
        (died,) = [e for e in game.state.events if e.type == EventType.DIES]
        assert died.data["had_counters"] == {"+1/+1": 2}

    def test_the_object_itself_has_been_wiped(self, builder):
        """The reason the snapshot has to exist at all."""
        game, oid = position(builder)
        game.state.objects[oid].add_counter("+1/+1", 2)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].counters == {}, (
            "`reset_permanent_state` runs before the dies trigger sees anything"
        )

    def test_counters_had_is_zero_outside_a_dies_trigger(self, builder):
        """No binding, no snapshot: it reports nothing rather than guessing."""
        from automtg.engine.effects.context import EffectContext
        from automtg.engine.effects.values import evaluate_value

        game, _ = position(builder)
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"counters_had": "-1/-1"}) == 0


class TestTheLoaderKnowsIt:
    def test_the_persist_card_compiles(self, registry):
        card = registry.get(PERSISTER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.condition is not None

    def test_an_unknown_value_key_is_still_refused(self):
        from automtg.engine.effects.values import validate_value

        with pytest.raises(DslError):
            validate_value({"counters_used_to_have": "-1/-1"}, "test")
