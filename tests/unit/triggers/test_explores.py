""""Whenever a creature you control explores, ..." -- and "...explores a land card"
and "...explores a nonland card".

Merfolk Cave-Diver watches every explore; Nicanzil, Current Conductor watches
the two halves separately and is the witness for telling them apart. Rule
701.40 makes exploring one act -- reveal, then the land to hand or the counter
and the choice -- and 701.40b says the permanent has explored once that is
done, even if some or all of it was impossible. So the trigger needs an event
fired *by the explore*, once, after it is done, naming the permanent that
explored and the card it revealed.

The near misses are wrong rather than merely absent:

- `counter_placed` never fires on a land explore, and fires on every other
  +1/+1 counter at the table.
- The revealed card's `zone_change` fires only for a land or a binned nonland,
  so a nonland kept on top would be missed.

The claims this file pins:

- **One explore, one event, after it completes**, naming the explorer.
- **The subject is the explorer**, and `controller: "you"` reads its
  controller, not whose ability made it explore.
- **Land and nonland are told apart by the revealed card**: `explores_land`
  hears only a land, `explores_nonland` only a nonland, `explores` both.
- **An empty library is still an explore** (701.40b): `explores` hears it and
  neither half does, because no card was revealed.
- **`source: "self"` is this permanent exploring**, never its ability making
  something else explore.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.events import EventType
from tests.conftest import only_oid, plus_one_counters, settle

WATCHER = "t_explore_watcher"  # Whenever a creature you control explores, gain 1.
SORTER = "t_explore_sorter"  # land card: gain 1; nonland card: +1/+1 on itself
SELFISH = "t_self_explorer"  # Whenever this creature explores, you gain 1 life.
BEAR = "t_bear"
FOREST = "forest"

BEARS = {"zone": "battlefield", "subtypes": ["Bear"]}
MY_BEARS = {**BEARS, "controller": "you"}


def position(builder, library, *, mine=(WATCHER, BEAR), theirs=(BEAR,)):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, list(library))
        .library(1, [BEAR] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def explore(game, objects, *, controller=0, source=None):
    """Resolve an explore, keeping every revealed nonland on top."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    gen = OPS["explore"](ctx, {"op": "explore", "objects": objects})
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return
        send = [1] if decision.kind is DecisionKind.MAY else list(range(decision.min_count))


def resolve(game) -> None:
    """Let the queued triggers reach the stack and resolve (see `test_connives`)."""
    game._advance()
    settle(game)


def explores(game) -> list:
    return [e for e in game.state.events if e.type == EventType.EXPLORED]


def queued(game, card_id) -> list:
    return [
        t
        for t in game.state.pending_triggers
        if game.state.objects[t.source_oid].def_id == card_id
    ]


def bear(game, pid=0) -> int:
    return only_oid(game, BEAR, pid)


class TestOneExploreOneEvent:
    def test_an_explore_fires_once_naming_the_explorer(self, builder):
        game = position(builder, [BEAR, FOREST])
        explore(game, MY_BEARS)
        (event,) = explores(game)
        assert event.data["oid"] == bear(game)
        assert event.data["card"] == BEAR, "the explorer, as on CONNIVED"
        assert event.data["revealed"] == BEAR
        assert event.data["land"] is False
        assert event.player == 0
        assert len(queued(game, WATCHER)) == 1

    def test_it_fires_after_the_counter(self, builder):
        game = position(builder, [BEAR, FOREST])
        explore(game, MY_BEARS)
        kinds = [e.type for e in game.state.events]
        fired = kinds.index(EventType.EXPLORED)
        assert EventType.COUNTER_PLACED in kinds[:fired]

    def test_a_land_explore_fires_too(self, builder):
        """No counter is placed, so a `counter_placed` spelling would miss it."""
        game = position(builder, [FOREST, BEAR])
        explore(game, MY_BEARS)
        (event,) = explores(game)
        assert event.data["land"] is True
        assert len(queued(game, WATCHER)) == 1

    def test_each_exploring_creature_is_its_own_explore(self, builder):
        game = position(builder, [FOREST, BEAR, BEAR], mine=(WATCHER, BEAR, BEAR))
        explore(game, MY_BEARS)
        assert [e.data["land"] for e in explores(game)] == [True, False]
        subjects = sorted(t.bindings["subject"] for t in queued(game, WATCHER))
        mine = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR]
        assert subjects == sorted(mine)


class TestTheSubjectIsTheExplorer:
    def test_an_opponents_creature_exploring_is_not_mine(self, builder):
        game = position(builder, [BEAR])
        explore(game, MY_BEARS, controller=1)
        assert len(explores(game)) == 1
        assert queued(game, WATCHER) == []

    def test_my_creature_exploring_for_their_ability_is_mine(self, builder):
        """The controller clause reads the explorer, not whose ability it was."""
        game = position(builder, [BEAR])
        explore(game, {**BEARS, "controller": "opponent"}, controller=1)
        (trigger,) = queued(game, WATCHER)
        assert trigger.bindings["subject"] == bear(game)

    def test_the_watcher_pays(self, builder):
        game = position(builder, [FOREST])
        life = game.state.players[0].life
        explore(game, MY_BEARS)
        resolve(game)
        assert game.state.players[0].life == life + 1


class TestLandOrNonland:
    def test_a_land_pays_the_land_trigger_only(self, builder):
        game = position(builder, [FOREST, BEAR], mine=(SORTER, BEAR))
        life = game.state.players[0].life
        explore(game, MY_BEARS)
        assert len(queued(game, SORTER)) == 1
        resolve(game)
        assert game.state.players[0].life == life + 1
        assert plus_one_counters(game, only_oid(game, SORTER)) == 0

    def test_a_nonland_pays_the_nonland_trigger_only(self, builder):
        game = position(builder, [BEAR, FOREST], mine=(SORTER, BEAR))
        life = game.state.players[0].life
        explore(game, MY_BEARS)
        assert len(queued(game, SORTER)) == 1
        resolve(game)
        assert game.state.players[0].life == life
        assert plus_one_counters(game, only_oid(game, SORTER)) == 1

    def test_the_sorter_exploring_itself_counts(self, builder):
        """"A creature you control" includes Nicanzil."""
        game = position(builder, [BEAR], mine=(SORTER,))
        explore(game, {"zone": "battlefield", "self_only": True}, source=only_oid(game, SORTER))
        assert len(queued(game, SORTER)) == 1


class TestAnEmptyLibraryStillExplores:
    def test_it_fires_with_no_card(self, builder):
        game = position(builder, [])
        explore(game, MY_BEARS)
        (event,) = explores(game)
        assert event.data["revealed"] is None
        assert event.data["land"] is None
        assert plus_one_counters(game, bear(game)) == 0

    def test_the_plain_watcher_hears_it(self, builder):
        game = position(builder, [])
        explore(game, MY_BEARS)
        assert len(queued(game, WATCHER)) == 1

    def test_neither_half_does(self, builder):
        """No card was revealed, so it explored neither a land nor a nonland."""
        game = position(builder, [], mine=(SORTER, BEAR))
        explore(game, MY_BEARS)
        assert len(explores(game)) == 1
        assert queued(game, SORTER) == []


class TestThisCreatureExplores:
    def test_its_own_explore_triggers_it(self, builder):
        game = position(builder, [BEAR], mine=(SELFISH,))
        me = only_oid(game, SELFISH)
        explore(game, {"zone": "battlefield", "self_only": True}, source=me)
        assert len(queued(game, SELFISH)) == 1

    def test_making_another_creature_explore_does_not(self, builder):
        game = position(builder, [BEAR], mine=(SELFISH, BEAR))
        explore(game, MY_BEARS, source=only_oid(game, SELFISH))
        assert len(explores(game)) == 1
        assert queued(game, SELFISH) == []


class TestNoExploreNoTrigger:
    def test_an_empty_pool_fires_nothing(self, builder):
        game = position(builder, [BEAR], mine=(WATCHER,))
        explore(game, MY_BEARS)
        assert explores(game) == []
        assert game.state.pending_triggers == []


class TestTheLoader:
    def test_the_printed_shapes_load(self):
        for event in ("explores", "explores_land", "explores_nonland"):
            compile_card(CardModel.model_validate(_card(event)))


def _card(event: str) -> dict:
    text = "Whenever a creature you control explores, this creature gets +1/+0 until end of turn."
    return {
        "id": f"t_bare_{event}_watcher",
        "name": f"Test Bare {event} Watcher",
        "oracle_text": text,
        "mana_cost": "{U}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "text": text,
                "trigger": {
                    "event": event,
                    "controller": "you",
                    "filter": {"types": ["Creature"]},
                },
                "effects": [
                    {
                        "op": "pump",
                        "power": {"const": 1},
                        "toughness": {"const": 0},
                        "objects": {"zone": "battlefield", "self_only": True},
                    }
                ],
            }
        ],
    }
