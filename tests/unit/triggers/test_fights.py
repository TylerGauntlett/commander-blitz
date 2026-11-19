""""Whenever a creature you control fights, put two +1/+1 counters on it at the
beginning of the next end step."

Foe-Razer Regent is the witness. Rule 701.12 makes a fight one exchange
between two creatures, and the card watches each creature that takes part, so
the trigger needs an event fired *by the fight*, once per creature, naming the
creature that fought.

`deals_damage` is the near miss, and it is wrong both ways: it fires for
combat damage and for every burn spell, so the Regent would pay for a Shock;
and it never fires for a 0-power creature, which fought and dealt nothing.

The claims this file pins:

- **One event per creature, after both blows**, each naming the creature that
  fought and the one it fought.
- **The subject is the fighter.** "It" is the creature that fought, and
  `controller: "you"` reads that creature's controller: my creature fighting
  theirs is one trigger, two of mine fighting each other is two.
- **A 0-power creature still fought.**
- **No fight, no event.** A fight 701.12c cancels (a creature gone) or 701.12d
  cancels (one creature told to fight itself) fires nothing.
- **`source: "self"` is this creature fighting**, never this creature's
  ability making two others fight.
- **The counters wait for the end step**, through `delay`, and land on "it".
"""

from __future__ import annotations

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_life import op_fight
from commanderblitz.engine.enums import Step
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, pass_until, plus_one_counters

REGENT = "t_fight_regent"  # Whenever a creature you control fights, ...
WATCHER = "t_fight_watcher"  # Whenever this creature fights, you gain 1 life.
BEAR = "t_f_2_2"
OGRE = "t_f_3_3"
WALL = "t_f_0_4"


def position(builder, mine, theirs):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def fight(game, a: int, b: int, *, source: int | None = None) -> None:
    """Resolve a fight between ``a`` and ``b``, as a spell or ability would."""
    op_fight(
        EffectContext(
            state=game.state,
            controller=0,
            source_oid=source,
            targets={
                "a": (TargetRef(kind="object", id=a),),
                "b": (TargetRef(kind="object", id=b),),
            },
        ),
        {"objects": {"target": "a"}, "other": {"target": "b"}},
    )


def fought(game) -> list:
    return [e for e in game.state.events if e.type == EventType.FOUGHT]


def queued(game, card_id) -> list:
    return [
        t
        for t in game.state.pending_triggers
        if game.state.objects[t.source_oid].def_id == card_id
    ]


def one(game, card_id: str, pid: int) -> int:
    (oid,) = oids_of(game, card_id, pid)
    return oid


class TestOneEventPerFighter:
    def test_a_fight_fires_once_for_each_creature(self, builder):
        game = position(builder, [REGENT, OGRE], [WALL])
        ogre, wall = one(game, OGRE, 0), one(game, WALL, 1)
        fight(game, ogre, wall)
        events = fought(game)
        assert [(e.data["oid"], e.data["other"]) for e in events] == [
            (ogre, wall),
            (wall, ogre),
        ]
        assert [e.player for e in events] == [0, 1]

    def test_it_fires_after_both_blows(self, builder):
        game = position(builder, [OGRE], [BEAR])
        fight(game, one(game, OGRE, 0), one(game, BEAR, 1))
        kinds = [e.type for e in game.state.events]
        first = kinds.index(EventType.FOUGHT)
        assert kinds[:first].count(EventType.DAMAGE_DEALT) >= 2
        assert EventType.DAMAGE_DEALT not in kinds[first:]


class TestTheSubjectIsTheFighter:
    def test_my_creature_fighting_theirs_is_one_trigger(self, builder):
        game = position(builder, [REGENT, OGRE], [WALL])
        ogre = one(game, OGRE, 0)
        fight(game, ogre, one(game, WALL, 1))
        (trigger,) = queued(game, REGENT)
        assert trigger.bindings["subject"] == ogre

    def test_two_of_mine_fighting_each_other_is_two(self, builder):
        game = position(builder, [REGENT, OGRE, WALL], [])
        ogre, wall = one(game, OGRE, 0), one(game, WALL, 0)
        fight(game, ogre, wall)
        assert sorted(t.bindings["subject"] for t in queued(game, REGENT)) == sorted(
            [ogre, wall]
        )

    def test_a_fight_between_their_creatures_is_not_mine(self, builder):
        game = position(builder, [REGENT], [OGRE, WALL])
        fight(game, one(game, OGRE, 1), one(game, WALL, 1))
        assert len(fought(game)) == 2
        assert queued(game, REGENT) == []


class TestAZeroPowerCreatureStillFought:
    def test_the_wall_dealt_nothing_and_fought(self, builder):
        game = position(builder, [REGENT, WALL], [BEAR])
        wall = one(game, WALL, 0)
        fight(game, wall, one(game, BEAR, 1))
        dealt_by_wall = [
            e for e in game.state.events if e.type == EventType.DAMAGE_DEALT and e.source == wall
        ]
        assert dealt_by_wall == []
        (trigger,) = queued(game, REGENT)
        assert trigger.bindings["subject"] == wall


class TestNoFightNoEvent:
    def test_a_creature_told_to_fight_itself_fires_nothing(self, builder):
        """701.12d."""
        game = position(builder, [REGENT, OGRE], [])
        ogre = one(game, OGRE, 0)
        fight(game, ogre, ogre)
        assert fought(game) == []
        assert queued(game, REGENT) == []

    def test_a_creature_gone_fires_nothing(self, builder):
        """701.12c: neither deals damage, and neither fought."""
        game = position(builder, [REGENT, OGRE], [BEAR])
        ogre, bear = one(game, OGRE, 0), one(game, BEAR, 1)
        destroy(game.state, bear)
        fight(game, ogre, bear)
        assert fought(game) == []
        assert queued(game, REGENT) == []


class TestThisCreatureFights:
    def test_its_own_fight_triggers_it(self, builder):
        game = position(builder, [WATCHER], [WALL])
        me = one(game, WATCHER, 0)
        fight(game, me, one(game, WALL, 1), source=me)
        assert len(queued(game, WATCHER)) == 1

    def test_making_two_others_fight_does_not(self, builder):
        game = position(builder, [WATCHER, OGRE], [WALL])
        me = one(game, WATCHER, 0)
        fight(game, one(game, OGRE, 0), one(game, WALL, 1), source=me)
        assert len(fought(game)) == 2
        assert queued(game, WATCHER) == []


class TestTheCountersWaitForTheEndStep:
    def test_two_counters_on_it_at_this_turns_end_step(self, builder):
        game = position(builder, [REGENT, OGRE], [WALL])
        ogre = one(game, OGRE, 0)
        fight(game, ogre, one(game, WALL, 1))
        turn = game.state.turn
        game._advance()
        pass_until(game, lambda g: plus_one_counters(g, ogre) > 0)
        assert plus_one_counters(game, ogre) == 2
        (placed,) = [
            e
            for e in game.state.events
            if e.type == EventType.COUNTER_PLACED and e.data.get("oid", e.source) == ogre
        ]
        assert (placed.turn, Step(placed.step)) == (turn, Step.END_STEP)
