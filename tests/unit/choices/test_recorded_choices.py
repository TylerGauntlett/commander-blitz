"""Amplify and devour — counting a set the player picked a moment ago.

    Amplify 2 — "As this creature enters, put two +1/+1 counters on it for each
    Beast card you reveal in your hand."
    Devour 2 — "As this creature enters, you may sacrifice any number of
    creatures. It enters with twice that many +1/+1 counters on it."

Both are "twice **that** many", and *that* is a set a player chose during this
same resolution. Nothing in the selector or value language can name it
afterwards, and the two fail differently, which is why they are one capability:

- the revealed cards go straight back into a hand full of other Beasts, so no
  filter distinguishes the ones that were shown;
- the devoured creatures are in a graveyard among everything else that died this
  turn, and `creatures_died_this_turn` counts combat and removal too — so on a
  real board it is a plausible number and the wrong one.

So the op writes down what it consumed (`as`), and `{"count": {"binding": …}}`
reads it back. A binding that holds a *list* is the only new idea; every trigger
binding before this held exactly one object.

The other half is that `reveal` now goes through `choose_objects`, so a
selector's `count` means what it means everywhere else. Amplify's "reveal **any
number**" was previously unsayable: `reveal` resolved its pool and showed the
whole hand without asking.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader.effects import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from tests.conftest import action_for_card, find_action, only_oid, pass_until, plus_one_counters

FOREST = "forest"
MOUNTAIN = "mountain"
BEAR = "t_bear"
BEAST = "t_amplifier"
DEVOURER = "t_devourer"


def answer_subset(game, take: int) -> None:
    """Take ``take`` options of the pending subset question, then close it.

    Choosing the last available option closes the decision on its own, so the
    "done" action is only offered while something is still choosable.
    """
    for _ in range(take):
        game.apply(find_action(game, ActionKind.CHOOSE))
    done = next(
        (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION), None
    )
    if done is not None:
        game.apply(done)


def drive(game, op: str, spec, source=None, *, take: int | None = None):
    """Run one op, choosing the first ``take`` options of any subset question."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = OPS[op](ctx, spec)
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return ctx
        n = len(decision.options) if take is None else take
        send = list(range(n))


class TestABindingCanHoldASet:
    def test_reveal_records_what_was_shown(self, builder):
        game = builder(players=2).hand(0, [BEAR, BEAR, FOREST]).build(advance=False)
        spec = {
            "op": "reveal",
            "as": "shown",
            "objects": {"zone": "hand", "controller": "you", "subtypes": ["Bear"],
                        "count": "any"},
        }

        ctx = drive(game, "reveal", spec)

        assert len(ctx.bindings["shown"]) == 2

    def test_the_recorded_set_is_countable(self, builder):
        game = builder(players=2).hand(0, [BEAR, BEAR, FOREST]).build(advance=False)
        spec = {
            "op": "reveal",
            "as": "shown",
            "objects": {"zone": "hand", "controller": "you", "subtypes": ["Bear"],
                        "count": "any"},
        }
        ctx = drive(game, "reveal", spec)

        assert len(resolve_pool(ctx, {"binding": "shown"})) == 2

    def test_a_single_object_binding_still_reads_as_one(self, builder):
        """Every trigger binding before this held one oid. They must keep working."""
        game = builder(players=2).battlefield(0, [BEAR]).build(advance=False)
        bear = only_oid(game, BEAR)
        ctx = EffectContext(state=game.state, controller=0)
        ctx.bindings["subject"] = bear

        assert resolve_pool(ctx, {"binding": "subject"}) == [bear]

    def test_an_unwritten_binding_is_empty(self, builder):
        game = builder(players=2).battlefield(0, [BEAR]).build(advance=False)
        ctx = EffectContext(state=game.state, controller=0)
        assert resolve_pool(ctx, {"binding": "nothing"}) == []


class TestRevealHonoursCount:
    def test_it_asks_for_any_number(self, builder):
        """Amplify's "reveal any number". Before this it revealed the lot."""
        game = builder(players=2).hand(0, [BEAR, BEAR, BEAR]).build(advance=False)
        ctx = EffectContext(state=game.state, controller=0)
        gen = OPS["reveal"](
            ctx,
            {"op": "reveal", "objects": {"zone": "hand", "controller": "you",
                                         "count": "any"}},
        )
        decision = next(gen)

        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert (decision.min_count, decision.max_count) == (0, 3)

    def test_a_plain_reveal_still_asks_nothing(self, builder):
        """`count` defaults to "all", so every reveal already in the pool is unchanged."""
        game = builder(players=2).battlefield(0, [BEAR]).build(advance=False)
        bear = only_oid(game, BEAR)
        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        gen = OPS["reveal"](ctx, {"op": "reveal", "objects": {"self_only": True}})
        with pytest.raises(StopIteration):
            next(gen)


class TestSacrificeRecordsWhatItAte:
    def test_it_records_the_creatures_consumed(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, BEAR, BEAR]).build(advance=False)
        spec = {
            "op": "sacrifice",
            "as": "eaten",
            "objects": {"zone": "battlefield", "controller": "you",
                        "types": ["Creature"], "count": "any"},
        }

        ctx = drive(game, "sacrifice", spec, take=2)

        assert len(ctx.bindings["eaten"]) == 2
        assert len(game.state.battlefield) == 1, "two really died"

    def test_the_record_survives_the_creatures(self, builder):
        """The whole point: they are in a graveyard by the time it is read."""
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)
        spec = {
            "op": "sacrifice",
            "as": "eaten",
            "objects": {"zone": "battlefield", "controller": "you",
                        "types": ["Creature"], "count": "any"},
        }
        ctx = drive(game, "sacrifice", spec)

        assert len(resolve_pool(ctx, {"binding": "eaten"})) == 2
        assert all(
            game.state.objects[o].zone is Zone.GRAVEYARD for o in ctx.bindings["eaten"]
        )


class TestAmplifyOnACard:
    def test_revealing_two_beasts_gives_four_counters(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 4)
            .hand(0, [BEAST, BEAST, BEAST])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, BEAST))
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None
            and d.kind is DecisionKind.CHOOSE_OBJECTS,
        )
        answer_subset(game, 2)   # reveal both remaining Beasts in hand
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert plus_one_counters(game, only_oid(game, BEAST)) == 4, "amplify 2, two revealed"

    def test_revealing_none_gives_none(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST] * 4)
            .hand(0, [BEAST, BEAST])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, BEAST))
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None
            and d.kind is DecisionKind.CHOOSE_OBJECTS,
        )
        answer_subset(game, 0)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert plus_one_counters(game, only_oid(game, BEAST)) == 0


class TestDevourOnACard:
    def test_eating_two_creatures_gives_four_counters(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [MOUNTAIN] * 5)
            .battlefield(0, [BEAR, BEAR])
            .hand(0, [DEVOURER])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, DEVOURER))
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None
            and d.kind is DecisionKind.CHOOSE_OBJECTS,
        )
        answer_subset(game, 2)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        devourer = only_oid(game, DEVOURER)
        assert plus_one_counters(game, devourer) == 4
        assert not [o for o in game.state.battlefield_objects(0) if o.def_id == BEAR]

    def test_it_does_not_eat_itself(self, builder):
        """`exclude_self`. A devourer that ate itself would be a 0-counter corpse."""
        game = (
            builder(players=2)
            .battlefield(0, [MOUNTAIN] * 5)
            .hand(0, [DEVOURER])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, DEVOURER))
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        devourer = only_oid(game, DEVOURER)
        assert game.state.objects[devourer].zone is Zone.BATTLEFIELD
        assert plus_one_counters(game, devourer) == 0


class TestTheLoaderGuard:
    def test_a_well_formed_as_loads(self):
        _validate_effect(
            {"op": "reveal", "as": "shown", "objects": {"zone": "hand"}}, "test", {}
        )

    def test_a_non_string_as_is_refused(self):
        """Stringified it would name a binding nothing reads, and count 0."""
        with pytest.raises(DslError, match="'as' must be a non-empty binding name"):
            _validate_effect({"op": "reveal", "as": 3, "objects": {}}, "test", {})

    def test_an_empty_as_is_refused(self):
        with pytest.raises(DslError, match="'as' must be a non-empty binding name"):
            _validate_effect({"op": "reveal", "as": "", "objects": {}}, "test", {})
