"""Proliferate (701.27a): "another counter of each kind already there".

The census had this `blocked`, on the grounds that "counter kinds are not
enumerable off an object". They always were — `GameObject.counters` is a dict
keyed by kind — and the row was describing a difficulty that did not exist.

What *is* real about proliferate is the thing that makes it not an
`add_counters` with a filter: the kinds are read **per permanent, at
resolution**, and differ between them. One proliferate adds a +1/+1 counter to
one creature, a charge counter to an artifact, and nothing at all to the
untouched permanent beside them. No amount of filtering says that; only reading
each object's own dict does.

Two things it must not do, and both would be quiet:

**Nothing gets a counter it did not already have.** Proliferate never starts a
kind, it only adds to one, so a creature with no counters stays at none.

**A kind at zero is not a kind.** `add_counter` prunes an entry when it reaches
zero, and a stale key left behind would silently make a permanent proliferable
for a counter it no longer has.

One documented simplification, in the house style. Rule 701.27a lets the player
choose *any number* of permanents; this proliferates every one they control that
has a counter. The choice only matters for counters you would rather not grow —
a -1/-1 counter on your own creature — and a free multi-select over the whole
board is a large decision for a rare downside. `objects` narrows it where a card
needs that.
"""

from __future__ import annotations

import contextlib

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from tests.conftest import only_oid

BEAR = "t_bear"
WALL = "t_wall"
BIG = "t_big"


def proliferate(game, controller: int = 0, **spec) -> None:
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [{"op": "proliferate", **spec}])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def counters_of(game, oid: int) -> dict:
    return dict(game.state.objects[oid].counters)


class TestItAddsOneOfEachKindAlreadyThere:
    def test_a_single_kind_grows_by_one(self, builder):
        game = builder(players=2).battlefield(0, [BEAR], counters={"+1/+1": 1}).build()
        oid = only_oid(game, BEAR, 0)
        proliferate(game)
        assert counters_of(game, oid) == {"+1/+1": 2}

    def test_every_kind_grows_together(self, builder):
        """The claim that makes this an op: the kinds are read off the object,
        and a card cannot name them in advance."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"+1/+1": 1, "charge": 2})
            .build()
        )
        oid = only_oid(game, BEAR, 0)
        proliferate(game)
        assert counters_of(game, oid) == {"+1/+1": 2, "charge": 3}

    def test_different_permanents_grow_different_kinds(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(0, [BIG], counters={"charge": 4})
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        big = only_oid(game, BIG, 0)
        proliferate(game)
        assert counters_of(game, bear) == {"+1/+1": 2}
        assert counters_of(game, big) == {"charge": 5}

    def test_one_counter_each_however_many_are_there(self, builder):
        """"**Another** counter", singular, not a doubling."""
        game = builder(players=2).battlefield(0, [BEAR], counters={"+1/+1": 6}).build()
        oid = only_oid(game, BEAR, 0)
        proliferate(game)
        assert counters_of(game, oid) == {"+1/+1": 7}


class TestItStartsNothing:
    def test_a_permanent_with_no_counters_stays_empty(self, builder):
        game = builder(players=2).battlefield(0, [WALL]).build()
        oid = only_oid(game, WALL, 0)
        proliferate(game)
        assert counters_of(game, oid) == {}

    def test_a_kind_pruned_to_zero_is_not_a_kind(self, builder):
        """`add_counter` removes the entry at zero. A stale key would make a
        permanent proliferable for a counter it no longer has."""
        game = builder(players=2).battlefield(0, [BEAR], counters={"+1/+1": 1}).build()
        oid = only_oid(game, BEAR, 0)
        game.state.objects[oid].add_counter("+1/+1", -1)
        assert counters_of(game, oid) == {}
        proliferate(game)
        assert counters_of(game, oid) == {}


class TestWhoIsAffected:
    def test_it_leaves_opponents_alone_by_default(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(1, [BEAR], counters={"+1/+1": 1})
            .build()
        )
        mine = only_oid(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        proliferate(game)
        assert counters_of(game, mine) == {"+1/+1": 2}
        assert counters_of(game, theirs) == {"+1/+1": 1}

    def test_objects_narrows_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], counters={"+1/+1": 1})
            .battlefield(0, [BIG], counters={"+1/+1": 1})
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        big = only_oid(game, BIG, 0)
        proliferate(game, objects={"controller": "you", "subtypes": ["Bear"]})
        assert counters_of(game, bear) == {"+1/+1": 2}
        assert counters_of(game, big) == {"+1/+1": 1}


class TestTheCardLoads:
    def test_the_proliferate_card_compiles(self, registry):
        card = registry.get("t_proliferator")
        assert [e["op"] for e in card.spell_effects] == ["proliferate"]
