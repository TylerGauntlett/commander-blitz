"""Magecraft: "Whenever you cast **or copy** an instant or sorcery spell…"

Rule 707.10a is the whole argument. A copy put on the stack by an effect is
*not cast* — nobody paid for it, no cast triggers fire for it, and it never
existed in any zone. So a card that says "cast **or copy**" is naming two
distinct events, and `spell_cast` answers exactly one of them.

The engine has emitted `EventType.SPELL_COPIED` from `put_copy_on_stack` since
copying existed, and nothing listened: it was absent from `TRIGGER_EVENTS`, so
no card could name it. Archmage Emeritus, Storm-Kiln Artist and Veyran were all
filed as unimplementable on that basis, correctly — the alternative was a bare
`spell_cast` trigger, which ships a strictly weaker card that silently misses
every copy.

**Why a second event and not a wider `spell_cast`.** Widening the cast event to
fire on copies is the tempting one-line version and it is badly wrong. Storm,
replicate, conspire, casualty, gravestorm and epic are all written as a
`spell_cast` trigger whose effect copies the spell that fired it. If a copy
counted as a cast, each of those copies would retrigger the ability that made
it — a storm count of nine becoming an unbounded loop rather than nine copies.
`TestACopyIsNotACast` is that guard, and it is the test that would fail loudest
if somebody ever "simplified" this.

So magecraft is one printed line implemented as two abilities, which is the
shape Winged Boots already uses for "has flying and ward {4}".

The shipped witnesses are Archmage Emeritus and Storm-Kiln Artist; `t_magecraft`
is their shape and `t_copy_watcher` isolates the copy half, so a passing test
cannot be explained by the cast half firing.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.conftest import action_for_card, count_on_battlefield, event_types, pass_until

BOLT = "t_stormbolt"  # {2}{R} instant, 1 damage to any target
STORMCAT = "t_stormcat"  # "Whenever you cast an instant spell, copy that spell."
ANCHOR = "t_plain_instant"  # {W}; a reason for priority to stop before cleanup


def position(builder, watchers, *, opponent_copies: bool = False):
    """``watchers`` on your battlefield, an instant in hand, mana for both seats.

    The opponent holds `ANCHOR` so auto-pass cannot run to cleanup, and a deep
    library so a draw trigger has something to draw.
    """
    game = (
        builder(players=2)
        .battlefield(0, [*watchers, "mountain", "mountain", "mountain", "island", "island"])
        .battlefield(1, ["plains", "mountain", "mountain", "mountain"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [] if opponent_copies else [BOLT])
        .hand(1, [BOLT] if opponent_copies else [ANCHOR])
        .build()
    )
    return game


def cast(game, card_id: str, pid: int = 0) -> None:
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().player == pid
        and any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
            for a in g.legal_actions()
        ),
    )
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def hand_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


class TestTheCopyHalfFires:
    def test_copying_a_spell_triggers_a_watcher_that_only_watches_copies(self, builder):
        """The load-bearing claim. `t_copy_watcher` has no cast trigger at all."""
        game = position(builder, [STORMCAT, "t_copy_watcher"])
        before = hand_size(game)

        cast(game, BOLT)

        assert hand_size(game) == before, "one card left hand (the bolt), one was drawn"

    def test_without_a_copier_the_copy_watcher_never_fires(self, builder):
        """The boundary: casting alone is not copying."""
        game = position(builder, ["t_copy_watcher"])
        before = hand_size(game)

        cast(game, BOLT)

        assert hand_size(game) == before - 1, "the bolt left hand and nothing was drawn"

    def test_the_event_is_emitted_with_the_copy(self, builder):
        game = position(builder, [STORMCAT])
        mark = len(game.state.events)

        cast(game, BOLT)

        assert "spell_copied" in event_types(game.state.events[mark:])


class TestMagecraftCountsBothHalves:
    def test_one_instant_draws_twice(self, builder):
        """Cast *and* copy, from one printed line and one spell."""
        game = position(builder, [STORMCAT, "t_magecraft"])
        before = hand_size(game)

        cast(game, BOLT)

        assert hand_size(game) == before + 1, "-1 bolt, +1 for the cast, +1 for the copy"

    def test_with_no_copier_it_draws_once(self, builder):
        game = position(builder, ["t_magecraft"])
        before = hand_size(game)

        cast(game, BOLT)

        assert hand_size(game) == before, "-1 bolt, +1 for the cast only"


class TestACopyIsNotACast:
    """707.10a, and the reason this is a second event rather than a wider one."""

    def test_a_cast_trigger_does_not_fire_on_the_copy_it_made(self, builder):
        """Otherwise every storm-shaped card loops instead of copying once."""
        game = position(builder, [STORMCAT])
        mark = len(game.state.events)

        cast(game, BOLT)

        kinds = event_types(game.state.events[mark:])
        assert kinds.count("spell_cast") == 1, "the copy must not count as a cast"
        assert kinds.count("spell_copied") == 1, "and it is copied exactly once"

    def test_two_copiers_make_two_copies_and_still_one_cast(self, builder):
        game = position(builder, [STORMCAT, STORMCAT])
        mark = len(game.state.events)

        cast(game, BOLT)

        kinds = event_types(game.state.events[mark:])
        assert kinds.count("spell_cast") == 1
        assert kinds.count("spell_copied") == 2


class TestWhoCopied:
    def test_an_opponent_copying_their_own_spell_does_not_fire_yours(self, builder):
        """`controller: "you"` is the copy's controller, not the original's.

        706.10 gives a copy to whoever created it, so reading the *original*
        spell's controller would make this fire on the wrong seat entirely.
        """
        game = position(builder, ["t_copy_watcher"], opponent_copies=True)
        game.state.battlefield.append(
            game.state.battlefield.pop(game.state.battlefield.index(game.state.battlefield[0]))
        )
        before = hand_size(game, 0)

        cast(game, BOLT, pid=1)

        assert hand_size(game, 0) == before, "their copy, their trigger, not yours"


class TestTheFilterReadsTheCopiedCard:
    def test_a_creature_filter_does_not_match_a_copied_instant(self, builder):
        """The subject is the original spell, so its printed types are askable."""
        game = position(builder, [STORMCAT, "t_creature_copy_watcher"])
        before = hand_size(game)

        cast(game, BOLT)

        assert hand_size(game) == before - 1, "an instant is not a creature spell"

    def test_the_watcher_is_still_on_the_battlefield_to_have_fired(self, builder):
        game = position(builder, [STORMCAT, "t_copy_watcher"])
        cast(game, BOLT)
        assert count_on_battlefield(game, "t_copy_watcher") == 1
