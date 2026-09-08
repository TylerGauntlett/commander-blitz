"""Copying a spell you **target**, rather than the one that fired you.

"Copy target instant or sorcery spell" — Fork, Expansion, Kitsa, Mizzix's
Mastery. `copy_spell` has existed since storm did and could not say this.

The reason is worth keeping, because it is not "the op was missing". `copy_spell`
named its victim only through `sid`, a **value** expression, and the value
language has no leaf for a declared target's stack id. Every shipped user of the
op — storm, replicate, conspire, casualty, gravestorm, epic, demonstrate — is a
triggered ability copying the spell that fired it, and reads `{"binding": "sid"}`
off its own trigger. So a card that named a target instead loaded clean,
validated clean, found no `sid`, fell back to an empty binding, and **silently
copied nothing**. That is precisely the "looks implemented and does nothing"
failure the authoring pipeline exists to catch, sitting inside the engine.

`counter` had already solved the identical problem for the identical kind of
object, with a `target` key routed through `ctx.target_sids`. This is that,
spelled the same way on purpose: two spellings of one question would be a second
bug waiting.

`TestStormStillCopiesItself` is the regression guard — the `sid` path is what
every existing copier uses and must not have moved.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind
from tests.conftest import event_types, pass_until

FORK = "t_fork"  # {U}{R}, copy target instant or sorcery spell
DRAW = "t_demo_draw"  # {R} instant, draw a card
BEAR = "t_bear"  # {1}{G} creature -- a spell Fork may not target
STORMCAT = "t_stormcat"  # "Whenever you cast an instant spell, copy that spell."
BOLT = "t_stormbolt"  # {2}{R} instant, 1 damage to any target


def position(builder, hand):
    """``hand`` for player 0, mana enough for all of it, a deep library."""
    return (
        builder(players=2)
        .battlefield(
            0, ["island", "island", "island", "mountain", "mountain", "mountain", "forest"]
        )
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, hand)
        .build()
    )


def cast_holding(game, card_id: str):
    """Cast ``card_id`` and stop while it is still on the stack."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)


def settle(game):
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


class TestCopyingATargetedSpell:
    def test_the_copy_is_made(self, builder):
        game = position(builder, [DRAW, FORK])
        cast_holding(game, DRAW)
        mark = len(game.state.events)

        cast_holding(game, FORK)
        settle(game)

        assert "spell_copied" in event_types(game.state.events[mark:])

    def test_the_copied_effect_happens_twice(self, builder):
        """The claim that matters: a silently-empty copy would still emit nothing."""
        game = position(builder, [DRAW, FORK])
        library_before = len(game.state.players[0].library)

        cast_holding(game, DRAW)
        cast_holding(game, FORK)
        settle(game)

        drawn = library_before - len(game.state.players[0].library)
        assert drawn == 2, "the original draw and its copy"

    def test_fork_is_offered_a_spell_on_the_stack_as_a_target(self, builder):
        game = position(builder, [DRAW, FORK])
        cast_holding(game, DRAW)

        forks = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FORK
        ]
        assert forks, "Fork is castable with a spell on the stack"
        assert all(a.targets for a in forks), "and it targets that spell"


class TestTheTargetRestrictionHolds:
    def test_a_creature_spell_is_not_a_legal_target(self, builder):
        """"target **instant or sorcery** spell" -- the selector is the whole check."""
        game = position(builder, [BEAR, FORK])
        cast_holding(game, BEAR)

        forks = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FORK
        ]
        assert forks == [], "no legal target, so no cast line"

    def test_with_nothing_on_the_stack_fork_cannot_be_cast(self, builder):
        """The boundary. A copier with no victim is not a castable spell."""
        game = position(builder, [FORK])
        forks = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FORK
        ]
        assert forks == []


class TestStormStillCopiesItself:
    """The `sid` path every existing copier uses, unmoved."""

    def test_a_cast_trigger_still_copies_the_spell_that_fired_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [STORMCAT, "mountain", "mountain", "mountain", "island"])
            .battlefield(1, ["plains"])
            .library(0, ["forest"] * 20)
            .hand(0, [BOLT])
            .build()
        )
        mark = len(game.state.events)
        cast_holding(game, BOLT)
        settle(game)

        kinds = event_types(game.state.events[mark:])
        assert kinds.count("spell_copied") == 1
