"""A dies trigger on the creature that died: rule 603.10a's look-back.

"Whenever this creature **or another creature** you control dies" (Zulaport
Cutthroat, Blood Artist, Falkenrath Noble) is written as a `creature_dies`
trigger with a filter rather than `source: "self"`, so the leave-the-battlefield
look-back used to skip it and the card never saw its own death. Leaves-the-
battlefield abilities look back in time, so the departed permanent's own dies
triggers are offered, and the trigger's filter decides:

* no `exclude_self` -- it fires on its own death;
* `exclude_self` ("another creature") -- it does not;
* nothing fires twice: a `source: "self"` trigger keeps the one path it had, and
  an ability that also functions in the graveyard is already heard there.

Each test card gains 1 life per firing, so the life gained counts firings.
"""

from __future__ import annotations

from automtg.engine.zones import destroy
from tests.conftest import only_oid, pass_until


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def life(game) -> int:
    return game.state.players[0].life


def gained_destroying(game, *card_ids: str) -> int:
    """Destroy one of each id in turn, settling after each; the life player 0 gained."""
    start = life(game)
    for card_id in card_ids:
        destroy(game.state, only_oid(game, card_id))
        settle(game)
    return life(game) - start


def gained_when_it_dies(builder, card_id: str) -> int:
    game = builder(players=2).battlefield(0, [card_id]).build()
    return gained_destroying(game, card_id)


class TestItsOwnDeath:
    def test_this_or_another_fires_on_its_own_death(self, builder):
        assert gained_when_it_dies(builder, "t_this_or_another_dies") == 1

    def test_another_does_not_fire_on_its_own_death(self, builder):
        assert gained_when_it_dies(builder, "t_another_dies") == 0

    def test_a_self_trigger_fires_once(self, builder):
        assert gained_when_it_dies(builder, "t_this_dies") == 1

    def test_a_graveyard_functioning_trigger_fires_once(self, builder):
        assert gained_when_it_dies(builder, "t_dies_watcher_anywhere") == 1


class TestAnotherCreaturesDeath:
    def test_both_wordings_fire_on_another_creature(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["t_this_or_another_dies", "t_another_dies", "t_bear"])
            .build()
        )
        assert gained_destroying(game, "t_bear") == 2

    def test_an_opponents_creature_dying_fires_neither(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["t_this_or_another_dies", "t_another_dies"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        assert gained_destroying(game, "t_bear") == 0

    def test_the_another_wording_still_hears_the_other_ones_death(self, builder):
        """The "this or another" card dies first (heard by both: 2), then the
        "another" card dies (heard by nobody: the first is in the graveyard)."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_this_or_another_dies", "t_another_dies"])
            .build()
        )
        assert gained_destroying(game, "t_this_or_another_dies", "t_another_dies") == 2
