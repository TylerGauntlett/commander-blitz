""""Whenever a creature you control connives, put a +1/+1 counter on that creature."

Glorious Purpose is the witness, with Iron Monger and Ultron beside it. Rule
701.47 makes conniving one act -- draw, then discard, then the counter -- and
these cards watch the act, so the trigger needs an event fired *by the
connive*, once, after it is done, naming the permanent that connived.

The near misses are wrong rather than merely absent:

- `draw` and `discard` fire per card, so connive 2 would pay twice; they fire on
  every draw and discard at the table, so the cleanup-step discard would pay
  too; and neither names the creature, so "that creature" has nothing to be.
- A connive whose discard an opponent's shield stopped discarded nothing and is
  still a connive, so a `discard` spelling would miss it outright.

The claims this file pins:

- **One connive, one event, after it completes.** Connive 2 fires once; the
  event comes after the discard and after the counter.
- **The subject is the conniver.** "That creature" is the permanent that
  connived, and `controller: "you"` reads that permanent's controller.
- **A connive that discards nothing still fires.**
- **`source: "self"` is this permanent conniving**, never this permanent's
  ability making something else connive.
- **No connive, no trigger.** A permanent that has left the battlefield does
  not connive here (the divergence `docs/rules-coverage.md` records), so it
  fires nothing.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step
from commanderblitz.engine.events import EventType
from tests.conftest import only_oid, plus_one_counters, settle

PLANNER = "t_connive_planner"  # Whenever a creature you control connives, ...
SELFISH = "t_self_conniver"  # Whenever this creature connives, you gain 1 life.
TAMIYO = "t_tamiyo_shield"  # opponents can't cause you to discard
BEAR = "t_bear"

BEARS = {"zone": "battlefield", "subtypes": ["Bear"]}


def position(builder, *, mine=(PLANNER, BEAR), theirs=(BEAR,)):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, [BEAR] * 10)
        .library(1, [BEAR] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def connive(game, objects, *, controller=0, source=None, amount=1):
    """Resolve a connive, discarding the first cards offered."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    spec = {"op": "connive", "objects": objects, "amount": {"const": amount}}
    gen = OPS["connive"](ctx, spec)
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return
        send = list(range(decision.min_count))


def resolve(game) -> None:
    """Let the queued triggers reach the stack and resolve.

    `_advance` first, because the connive ran through the op rather than a game
    action, so nothing has offered priority yet (see `test_becomes_tapped`).
    """
    game._advance()
    settle(game)


def connives(game) -> list:
    return [e for e in game.state.events if e.type == EventType.CONNIVED]


def queued(game, card_id) -> list:
    return [
        t
        for t in game.state.pending_triggers
        if game.state.objects[t.source_oid].def_id == card_id
    ]


def bear(game, pid=0) -> int:
    return only_oid(game, BEAR, pid)


def plan_counters(game, oid) -> int:
    return game.state.objects[oid].counters.get("plan", 0)


class TestOneConniveOneEvent:
    def test_a_connive_fires_once_naming_the_conniver(self, builder):
        game = position(builder)
        connive(game, {**BEARS, "controller": "you"})
        (event,) = connives(game)
        assert event.data["oid"] == bear(game)
        assert event.player == 0
        assert len(queued(game, PLANNER)) == 1

    def test_connive_two_is_one_connive(self, builder):
        game = position(builder)
        connive(game, {**BEARS, "controller": "you"}, amount=2)
        assert len(connives(game)) == 1
        assert len(queued(game, PLANNER)) == 1

    def test_it_fires_after_the_discard_and_the_counter(self, builder):
        game = position(builder)
        connive(game, {**BEARS, "controller": "you"})
        kinds = [e.type for e in game.state.events]
        fired = kinds.index(EventType.CONNIVED)
        assert EventType.DISCARD in kinds[:fired]
        assert EventType.COUNTER_PLACED in kinds[:fired], "a Bear was discarded"
        assert EventType.DISCARD not in kinds[fired:]

    def test_each_conniving_creature_is_its_own_connive(self, builder):
        game = position(builder, mine=(PLANNER, BEAR, BEAR))
        connive(game, {**BEARS, "controller": "you"})
        assert len(connives(game)) == 2
        subjects = sorted(t.bindings["subject"] for t in queued(game, PLANNER))
        mine = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR]
        assert subjects == sorted(mine)


class TestTheSubjectIsTheConniver:
    def test_that_creature_gets_the_counter_and_the_plan_its_counter(self, builder):
        game = position(builder)
        mine = bear(game)
        connive(game, {**BEARS, "controller": "you"})
        before = plus_one_counters(game, mine)
        resolve(game)
        assert plus_one_counters(game, mine) == before + 1
        assert plan_counters(game, only_oid(game, PLANNER)) == 1

    def test_an_opponents_creature_conniving_is_not_mine(self, builder):
        game = position(builder)
        connive(game, {**BEARS, "controller": "you"}, controller=1)
        assert len(connives(game)) == 1
        assert queued(game, PLANNER) == []

    def test_my_creature_conniving_for_their_ability_is_mine(self, builder):
        """The controller clause reads the conniver, not whose ability it was."""
        game = position(builder)
        connive(game, {**BEARS, "controller": "opponent"}, controller=1)
        (trigger,) = queued(game, PLANNER)
        assert trigger.bindings["subject"] == bear(game)


class TestADiscardlessConniveStillConnives:
    def test_a_shielded_connive_discards_nothing_and_fires(self, builder):
        game = position(builder, mine=(PLANNER, TAMIYO, BEAR))
        hand = len(game.state.players[0].hand)
        connive(game, {**BEARS, "controller": "opponent"}, controller=1)
        assert len(game.state.players[0].hand) == hand + 1, "drew and kept it"
        (event,) = connives(game)
        assert event.data["discarded"] == 0
        assert len(queued(game, PLANNER)) == 1


class TestThisCreatureConnives:
    def test_its_own_connive_triggers_it(self, builder):
        game = position(builder, mine=(SELFISH,))
        me = only_oid(game, SELFISH)
        connive(game, {"zone": "battlefield", "self_only": True}, source=me)
        assert len(queued(game, SELFISH)) == 1

    def test_making_another_creature_connive_does_not(self, builder):
        """Doctor Doom's shape: its ability, a Villain's connive."""
        game = position(builder, mine=(SELFISH, BEAR))
        me = only_oid(game, SELFISH)
        connive(game, {**BEARS, "controller": "you"}, source=me)
        assert len(connives(game)) == 1
        assert queued(game, SELFISH) == []

    def test_gaining_the_life(self, builder):
        game = position(builder, mine=(SELFISH,))
        life = game.state.players[0].life
        me = only_oid(game, SELFISH)
        connive(game, {"zone": "battlefield", "self_only": True}, source=me)
        resolve(game)
        assert game.state.players[0].life == life + 1


class TestNoConniveNoTrigger:
    def test_an_empty_pool_fires_nothing(self, builder):
        game = position(builder, mine=(PLANNER,))
        connive(game, {**BEARS, "controller": "you"})
        assert connives(game) == []
        assert game.state.pending_triggers == []

    def test_no_watcher_no_trigger(self, builder):
        game = position(builder, mine=(BEAR,))
        connive(game, {**BEARS, "controller": "you"})
        assert len(connives(game)) == 1, "the event is the game's, not the card's"
        assert game.state.pending_triggers == []


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))


def _card() -> dict:
    text = "Whenever a creature you control connives, put a +1/+1 counter on each Villain you control."
    return {
        "id": "t_bare_connive_watcher",
        "name": "Test Bare Connive Watcher",
        "oracle_text": text,
        "mana_cost": "{3}{B}",
        "types": ["Creature"],
        "power": 3,
        "toughness": 3,
        "abilities": [
            {
                "kind": "triggered",
                "text": text,
                "trigger": {
                    "event": "connives",
                    "controller": "you",
                    "filter": {"types": ["Creature"]},
                },
                "effects": [
                    {
                        "op": "add_counters",
                        "counter": "+1/+1",
                        "amount": {"const": 1},
                        "objects": {
                            "zone": "battlefield",
                            "controller": "you",
                            "subtypes": ["Villain"],
                        },
                    }
                ],
            }
        ],
    }
