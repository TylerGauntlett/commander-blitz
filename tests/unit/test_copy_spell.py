"""Spell copying (706.10): storm, replicate, conspire, casualty, gravestorm.

`docs/keywords.md` names spell copying as one of its six clusters, with six
keywords waiting on it. They are one capability: every one says "copy this
spell", and they differ only in how many times and what it costs.

**A copy is not a card, and that is what makes it disappear correctly.** Rule
706.10 puts a copy on the stack without it being cast and without it existing in
any zone. So the copy is backed by a *token* object, and when an instant's copy
resolves into a graveyard the token state-based action removes it — leaving the
original card as the only one that ends up there. A second ordinary
`GameObject` would quietly put a duplicate card in the graveyard, which every
graveyard count on the board would then be wrong about.

**Copies go on top, so they resolve first**, which is 706.10 and is also why a
storm copy can be countered separately from the spell that made it.

**A copy is not cast**, so it emits `SPELL_COPIED` rather than `SPELL_CAST`.
Reusing the cast event would be convenient and wrong twice over: storm counts
spells cast this turn, so a copy counted as a cast would make the next storm
spell exponential, and a log built from casts would show nine bolts as one.

One thing deliberately not implemented, and the docstring says so: "you may
choose new targets for the copy". Every copy here keeps the original's targets.
The choice is a decision *per copy*, and a storm count of nine would ask nine
times — worth building when a card in the pool needs it, and misleading to
half-implement before then.
"""

from __future__ import annotations

import contextlib

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.events import EventType
from tests.conftest import _default_answer, action_for_card

BOLT = "t_bolt"  # {R} instant, 3 damage to any target
STORMBOLT = "t_stormbolt"  # {2}{R} instant, 1 damage; storm


def position(builder, hand=(BOLT,), lands=6):
    """Player 0 holds `hand`; player 1 holds an instant of their own.

    The opponent's bolt is not decoration. With nothing to respond with, both
    players auto-pass and a spell resolves inside the same `apply` that cast
    it -- so a test that casts and then looks at the stack finds it empty and
    has nothing to copy.
    """
    return (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, ["mountain"] * lands)
        .hand(1, [BOLT])
        .battlefield(1, ["mountain"])
        .build()
    )


def copy_the_top_spell(game, controller: int = 0, **spec) -> None:
    """Run `copy_spell` against whatever is on the stack."""
    top = game.state.stack[-1]
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [{"op": "copy_spell", "sid": {"const": top.sid}, **spec}])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def settle(game, limit: int = 60) -> None:
    for _ in range(limit):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def total_life(game) -> int:
    return sum(p.life for p in game.state.players)


def graveyard_ids(game, pid: int = 0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].graveyard]


class TestTheCopyItself:
    def test_a_copy_goes_on_the_stack(self, builder):
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        before = len(game.state.stack)
        copy_the_top_spell(game)
        assert len(game.state.stack) == before + 1

    def test_the_copy_is_on_top(self, builder):
        """706.10: copies resolve before the spell that made them."""
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        original = game.state.stack[-1]
        copy_the_top_spell(game)
        assert game.state.stack[-1].sid != original.sid
        assert game.state.stack[-2].sid == original.sid

    def test_the_copy_is_backed_by_a_token(self, builder):
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        copy_the_top_spell(game)
        copy = game.state.stack[-1]
        assert game.state.objects[copy.oid].is_token

    def test_it_keeps_the_originals_targets(self, builder):
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        original = game.state.stack[-1]
        copy_the_top_spell(game)
        assert game.state.stack[-1].targets == original.targets

    def test_it_emits_its_own_event(self, builder):
        """Not `SPELL_CAST`: a copy is not cast, and counting it as one would
        make the next storm spell exponential."""
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        casts_before = game.state.turn_ledger.spells_cast.get(0, 0)
        copy_the_top_spell(game)
        assert [e for e in game.state.events if e.type == EventType.SPELL_COPIED]
        assert game.state.turn_ledger.spells_cast.get(0, 0) == casts_before

    def test_amount_makes_several(self, builder):
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        before = len(game.state.stack)
        copy_the_top_spell(game, amount={"const": 3})
        assert len(game.state.stack) == before + 3


class TestTheCopyResolves:
    def test_the_effect_happens_twice(self, builder):
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        before = total_life(game)
        copy_the_top_spell(game)
        settle(game)
        assert before - total_life(game) == 6, "three damage twice"

    def test_only_the_real_card_reaches_the_graveyard(self, builder):
        """The whole reason a copy is a token. A second ordinary object would
        leave a duplicate card in the graveyard and every count would be wrong.
        """
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        copy_the_top_spell(game, amount={"const": 2})
        settle(game)
        assert graveyard_ids(game).count(BOLT) == 1

    def test_the_copy_object_ceases_to_exist(self, builder):
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        copy_the_top_spell(game)
        copy_oid = game.state.stack[-1].oid
        settle(game)
        assert copy_oid not in game.state.objects


class TestNothingToCopy:
    def test_an_absent_sid_copies_nothing(self, builder):
        game = position(builder)
        ctx = EffectContext(state=game.state, controller=0)
        gen = execute(ctx, [{"op": "copy_spell", "sid": {"const": 9999}}])
        with contextlib.suppress(StopIteration):
            while True:
                next(gen)
        assert game.state.stack == []

    def test_zero_copies_is_no_copies(self, builder):
        """Storm on the first spell of the turn: the count is zero."""
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        before = len(game.state.stack)
        copy_the_top_spell(game, amount={"const": 0})
        assert len(game.state.stack) == before


class TestStorm:
    def test_the_first_spell_of_the_turn_makes_no_copies(self, builder):
        game = position(builder, hand=(STORMBOLT,), lands=6)
        before = total_life(game)
        game.apply(action_for_card(game, ActionKind.CAST, STORMBOLT))
        settle(game)
        assert before - total_life(game) == 1, "one damage, no copies"

    def test_the_second_spell_copies_once(self, builder):
        """Both cast in the same turn, without settling in between.

        Settling after the first one passes priority until the stack empties,
        which auto-passes into the next turn -- and the storm count is a
        *per-turn* tally, so it would be back at zero and the copy count would
        be -1. Casting both while the first is still on the stack is also what
        a storm deck actually does.
        """
        game = position(builder, hand=(BOLT, STORMBOLT), lands=6)
        before = total_life(game)
        game.apply(action_for_card(game, ActionKind.CAST, BOLT))
        game.apply(action_for_card(game, ActionKind.CAST, STORMBOLT))
        assert game.state.turn_ledger.spells_cast[0] == 2
        settle(game)
        assert before - total_life(game) == 5, (
            "three from the bolt, one from the stormbolt, one from its copy"
        )

    def test_the_storm_card_compiles(self, registry):
        card = registry.get(STORMBOLT)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert Zone.STACK in ability.active_zones
        assert [e["op"] for e in ability.effects] == ["copy_spell"]
