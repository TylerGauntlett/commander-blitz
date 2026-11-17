"""Time travel (701.55a): "For each permanent you control with a time counter on
it and each suspended card you own with a time counter on it, you may put a time
counter on it or remove a time counter from it."

Three things it would be wrong without, each quietly.

**Who is offered.** Only "you": permanents you control and suspended cards you
own, each with a time counter already on it. An exiled card carrying time
counters that is *not* suspended -- the near miss a `has_counters` selector in
exile makes -- is not one, and nothing without a time counter is ever started.

**The choice is a direction, per object.** Put one on, take one off, or leave
it, asked of the controller object by object. Proliferate only adds, so the
suspended card you want sooner and the vanishing clock you want longer cannot
both be served by it.

**The last counter means what it always means.** Under 702.62a removing the
last time counter from a suspended card casts it for free, with haste, and
under 702.63a the last one off a vanishing permanent sacrifices it. A time
travel that took a suspended card to zero and left it in exile would strand
the card for the rest of the game; this one casts it through suspend's own
machinery, once the time travel's every choice is made.

The witnesses are Wibbly-wobbly, Timey-wimey and The Tenth Doctor ("time travel
three times").
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.objects import TIME_COUNTER
from commanderblitz.engine.suspend import make_suspended
from commanderblitz.engine.zones import exile
from tests.conftest import settle

BEAR = "grizzly_bears"  # a vanilla creature: what a free cast puts on the stack
SPRITE = "t_vanishing_sprite"  # vanishing 2
WATCHER = "watcher_of_hours"  # "whenever you remove a time counter from this card while it's exiled"
WALL = "t_wall"

#: An answer is one meaning per object: "add", "remove" or "leave".
Answer = Callable[[int], str]


def board(builder, *, mine=(), theirs=(), hand0=(), hand1=(), advance=False):
    """Seat 0's and seat 1's permanents (``(card_id, time counters)``), and hands.

    Frozen where the builder starts unless ``advance``: a test that resolves a
    trigger needs the game running, and one that only reads counters does not.
    """
    b = builder(players=2)
    for seat, cards in ((0, mine), (1, theirs)):
        for card_id, n in cards:
            b = b.battlefield(seat, [card_id], counters={TIME_COUNTER: n} if n else None)
    b = b.hand(0, list(hand0)).hand(1, list(hand1))
    return b.build(advance=advance)


def in_hand(game, pid: int, card_id: str) -> int:
    return next(o for o in game.state.players[pid].hand if game.state.objects[o].def_id == card_id)


def on_battlefield(game, pid: int, card_id: str) -> int:
    return next(o.oid for o in game.state.battlefield_objects(pid) if o.def_id == card_id)


def suspend(game, pid: int, card_id: str, counters: int) -> int:
    """Suspend ``pid``'s ``card_id`` from hand with ``counters`` time counters."""
    oid = in_hand(game, pid, card_id)
    assert make_suspended(game.state, oid, counters)
    return oid


def answering(default: str = "leave", **by_oid: str) -> Answer:
    """``o<oid>="remove"`` and so on; every other object gets ``default``."""
    return lambda oid: by_oid.get(f"o{oid}", default)


_MEANING = {"Put": "add", "Remove": "remove", "Leave": "leave"}


def time_travel(game, answer: Answer = answering(), *, amount: int | None = None, controller: int = 0):
    """Resolve one time travel outside the stack; return the decisions it asked."""
    ctx = EffectContext(state=game.state, controller=controller)
    spec = {"op": "time_travel"}
    if amount is not None:
        spec["amount"] = {"const": amount}
    gen = execute(ctx, [spec])
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            want = answer(decision.context["oid"])
            [index] = [
                i
                for i, option in enumerate(decision.options)
                if _MEANING[option.label.split()[0]] == want
            ]
            decision = gen.send([index])
    except StopIteration:
        pass
    return asked


def offered(asked) -> list[int]:
    return [d.context["oid"] for d in asked]


def time_counters(game, oid: int) -> int:
    return game.state.objects[oid].counter(TIME_COUNTER)


class TestWhoIsOffered:
    def test_a_permanent_you_control_with_a_time_counter(self, builder):
        game = board(builder, mine=[(SPRITE, 2)])
        sprite = on_battlefield(game, 0, SPRITE)
        assert offered(time_travel(game)) == [sprite]

    def test_a_suspended_card_you_own(self, builder):
        game = board(builder, hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 3)
        assert offered(time_travel(game)) == [bear]

    def test_each_object_is_its_own_question_asked_of_you(self, builder):
        game = board(builder, mine=[(SPRITE, 2)], hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 3)
        asked = time_travel(game)
        assert sorted(offered(asked)) == sorted([on_battlefield(game, 0, SPRITE), bear])
        assert all(d.kind is DecisionKind.CHOOSE_MODE for d in asked)
        assert all(d.player == 0 for d in asked)

    def test_a_permanent_with_no_time_counter_is_not(self, builder):
        """Time travel never starts a counter."""
        game = board(builder, mine=[(WALL, 0)])
        wall = on_battlefield(game, 0, WALL)
        game.state.objects[wall].counters = {"+1/+1": 2}
        assert time_travel(game) == []
        assert time_counters(game, wall) == 0

    def test_an_opponents_permanent_is_not(self, builder):
        game = board(builder, theirs=[(SPRITE, 2)])
        assert time_travel(game) == []

    def test_an_opponents_suspended_card_is_not(self, builder):
        game = board(builder, hand1=[BEAR])
        suspend(game, 1, BEAR, 3)
        assert time_travel(game) == []

    def test_an_exiled_card_with_time_counters_that_is_not_suspended_is_not(self, builder):
        """The `has_counters`-in-exile near miss."""
        game = board(builder, hand0=[BEAR])
        bear = in_hand(game, 0, BEAR)
        exile(game.state, bear)
        game.state.objects[bear].add_counter(TIME_COUNTER, 2)
        assert game.state.objects[bear].suspended_by is None
        assert time_travel(game) == []
        assert time_counters(game, bear) == 2

    def test_a_phased_out_permanent_is_not(self, builder):
        game = board(builder, mine=[(SPRITE, 2)])
        game.state.objects[on_battlefield(game, 0, SPRITE)].phased_out = True
        assert time_travel(game) == []

    def test_the_default_answer_is_the_likelier_wish(self, builder):
        """The first option is what the verifier and a timed-out seat pick."""
        game = board(builder, mine=[(SPRITE, 2)], hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 3)
        sprite = on_battlefield(game, 0, SPRITE)
        by_oid = {d.context["oid"]: d.options[0].label for d in time_travel(game)}
        assert by_oid[bear].startswith("Remove"), "a suspended card, sooner"
        assert by_oid[sprite].startswith("Put"), "a clock, longer"


class TestEachAnswer:
    def test_put_one_on_a_permanent(self, builder):
        game = board(builder, mine=[(SPRITE, 2)])
        sprite = on_battlefield(game, 0, SPRITE)
        time_travel(game, answering(**{f"o{sprite}": "add"}))
        assert time_counters(game, sprite) == 3

    def test_take_one_off_a_permanent(self, builder):
        game = board(builder, mine=[(SPRITE, 2)])
        sprite = on_battlefield(game, 0, SPRITE)
        time_travel(game, answering(**{f"o{sprite}": "remove"}))
        assert time_counters(game, sprite) == 1

    def test_leave_it(self, builder):
        game = board(builder, mine=[(SPRITE, 2)], hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 3)
        sprite = on_battlefield(game, 0, SPRITE)
        time_travel(game, answering("leave"))
        assert (time_counters(game, sprite), time_counters(game, bear)) == (2, 3)

    def test_put_one_on_a_suspended_card_keeps_it_suspended(self, builder):
        game = board(builder, hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 1)
        time_travel(game, answering("add"))
        obj = game.state.objects[bear]
        assert (obj.zone, obj.counter(TIME_COUNTER), obj.suspended_by) == (Zone.EXILE, 2, 0)

    def test_take_one_off_a_suspended_card_is_the_ticks_removal(self, builder):
        """The same events the upkeep tick makes, so the log and the bus agree."""
        game = board(builder, hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 3)
        mark = len(game.state.events)
        time_travel(game, answering("remove"))
        assert time_counters(game, bear) == 2
        types = [e.type for e in game.state.events[mark:]]
        assert EventType.COUNTER_REMOVED in types
        assert EventType.TIME_COUNTER_REMOVED in types

    def test_you_remove_it_for_whenever_you_remove(self, builder):
        """Watcher of Hours: "whenever you remove a time counter from this card
        while it's exiled" hears time travel."""
        game = board(builder, hand0=[WATCHER])
        watcher = suspend(game, 0, WATCHER, 6)
        time_travel(game, answering("remove"))
        assert time_counters(game, watcher) == 5
        assert [t.source_oid for t in game.state.pending_triggers] == [watcher]


class TestTheLastCounter:
    def test_a_suspended_card_emptied_is_cast_for_free(self, builder):
        """702.62a: not stranded in exile at zero."""
        game = board(builder, hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 1)
        time_travel(game, answering("remove"))
        obj = game.state.objects[bear]
        assert obj.zone is Zone.STACK
        assert obj.suspended_by is None
        assert obj.hasted_by_suspend, "suspend's haste comes with suspend's cast"
        assert [s.oid for s in game.state.stack][-1] == bear

    def test_the_cast_waits_for_every_choice(self, builder):
        """Both last counters come off before either card is cast."""
        game = board(builder, hand0=[BEAR, BEAR])
        first = suspend(game, 0, BEAR, 1)
        second = suspend(game, 0, BEAR, 1)
        zones_seen = []

        def answer(oid):
            zones_seen.append(game.state.objects[first].zone)
            return "remove"

        time_travel(game, answer)
        assert zones_seen == [Zone.EXILE, Zone.EXILE]
        assert game.state.objects[first].zone is Zone.STACK
        assert game.state.objects[second].zone is Zone.STACK

    def test_a_vanishing_permanent_emptied_is_sacrificed(self, builder):
        """702.63a's `last_counter_removed` trigger hears time travel."""
        game = board(builder, mine=[(SPRITE, 1)], advance=True)
        sprite = on_battlefield(game, 0, SPRITE)
        time_travel(game, answering("remove"))
        assert game.state.objects[sprite].zone is Zone.BATTLEFIELD, "a trigger, not yet resolved"
        settle(game)
        assert game.state.objects[sprite].zone is Zone.GRAVEYARD

    def test_a_removal_that_leaves_one_casts_nothing(self, builder):
        game = board(builder, hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 2)
        time_travel(game, answering("remove"))
        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.stack == []


class TestTimeTravelNTimes:
    def test_each_time_is_a_whole_time_travel(self, builder):
        """The Tenth Doctor: three questions for one object, three counters."""
        game = board(builder, hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 5)
        asked = time_travel(game, answering("remove"), amount=3)
        assert offered(asked) == [bear] * 3
        assert time_counters(game, bear) == 2

    def test_a_card_emptied_early_is_offered_no_more_and_cast_once(self, builder):
        """Once at zero it is no longer suspended (702.62b)."""
        game = board(builder, hand0=[BEAR])
        bear = suspend(game, 0, BEAR, 1)
        asked = time_travel(game, answering("remove"), amount=2)
        assert offered(asked) == [bear]
        assert game.state.objects[bear].zone is Zone.STACK
        assert [s.oid for s in game.state.stack].count(bear) == 1


def _probe(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {"id": "probe", "name": "Probe", "types": ["Sorcery"], "spell_effects": [effect]}
    )


class TestTheLoader:
    def test_the_bare_keyword_loads(self):
        compile_card(_probe({"op": "time_travel"}))
        compile_card(_probe({"op": "time_travel", "amount": {"const": 3}}))

    @pytest.mark.parametrize(
        "key, value",
        [
            ("objects", {"controller": "you"}),
            ("counter", "time"),
            ("player", "you"),
            ("up_to", True),
        ],
    )
    def test_a_key_that_would_narrow_it_is_refused(self, key, value):
        with pytest.raises(DslError, match=f"time_travel .* takes no '{key}'"):
            compile_card(_probe({"op": "time_travel", key: value}))
