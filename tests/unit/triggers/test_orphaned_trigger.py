"""A trigger whose source is gone by the time it reaches the stack.

    "When this creature dies, create a 1/1 Vampire" -- on a **token**.

A token that triggers on its own death is unlike every other permanent: the
token state-based action pops it out of `state.objects` rather than moving it to
a graveyard, so by the time the trigger is drained there is no object left to
read the card off.

`push_triggered_ability` fell back to the string `"?"`, which is not a card id.
`_resolve_ability` looks the id up in the registry *before* it asks whether the
ability still exists, so the fallback did not degrade into "resolve nothing" --
it raised `DslError: unknown card id '?'` and took the game down.

The fix is the engine's explicit-LKI pattern, in the one place a card cannot
reach with a `snapshot` op of its own: the card id is written onto the
`TriggerInstance` when the trigger fires, while the object is still there.

Found by the arena, which is what the arena is for. `main` was green, so was the
commit before "A triggered ability's controller chooses its targets" -- that
commit made `_advance` return mid-drain when a trigger stops to choose, which
opened a window for state-based actions to run between a trigger being collected
and being pushed.
"""

from __future__ import annotations

from commanderblitz.engine.stack import push_triggered_ability, resolve_top
from commanderblitz.engine.structs import TriggerInstance

BEAR = "t_bear"


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 5)
        .library(0, ["forest"] * 20)
        .build()
    )


def drive(game, trig: TriggerInstance) -> None:
    """Push the trigger and resolve it, answering nothing."""
    for _ in push_triggered_ability(game.state, trig):
        raise AssertionError("this trigger chooses nothing")
    gen = resolve_top(game.state)
    while True:
        try:
            next(gen)
        except StopIteration:
            return


class TestASourceThatVanished:
    def test_it_does_not_take_the_game_down(self, builder):
        """The whole bug: `"?"` reached `registry.get` and raised."""
        game = board(builder)
        trig = TriggerInstance(
            source_oid=9999,  # never existed, the way a popped token no longer does
            ability_index=0,
            controller=0,
            def_id=BEAR,
        )
        drive(game, trig)

    def test_the_stack_item_names_the_real_card(self, builder):
        game = board(builder)
        trig = TriggerInstance(
            source_oid=9999, ability_index=0, controller=0, def_id=BEAR
        )
        for _ in push_triggered_ability(game.state, trig):
            raise AssertionError("this trigger chooses nothing")
        assert game.state.stack[-1].def_id == BEAR

    def test_with_no_snapshot_it_still_does_not_raise(self, builder):
        """A trigger built by hand with no `def_id` falls back to `"?"`, which
        `_resolve_ability` must survive rather than look up."""
        game = board(builder)
        trig = TriggerInstance(source_oid=9999, ability_index=0, controller=0)
        drive(game, trig)
