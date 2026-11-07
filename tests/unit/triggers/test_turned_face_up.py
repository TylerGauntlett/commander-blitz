""""When this creature is turned face up" and "whenever a permanent you control
is turned face up" -- the `turned_face_up` trigger event.

Turning a face-down permanent face up (702.37e for morph, 701.34a for
manifest) is a special action that changes no zone: the 2/2 shell becomes the
card underneath, where it already stands. 708.8 is explicit that nothing about
*entering* happens again, so `self_enters` and `permanent_enters` cannot stand in
for it, and `counter_placed` hears megamorph alone. `Game._turn_face_up` had
always logged the event and nothing could listen to it, so Kheru Spellsnatcher's
counterspell, Growing Dread's counter, Trail of Mystery's pump, Temur War
Shaman's fight and Deathmist Raptor's return from the graveyard had no trigger
to hang on.

Two things here are rules arguments rather than plumbing:

* **Self.** "When this creature is turned face up" is printed on the hidden
  card, and a face-down permanent has no abilities (707.2), so the ability can
  only hear the event if the event fires once the permanent is already face up
  (603.2, triggers look at the game after the event). Fired any earlier, every
  morph's own turned-up ability would be dead text.
* **The subject is the face-up card.** "If it's a creature", "a Beast you
  control" -- a filter must read what was turned up, never the colourless 2/2
  it used to be, or a subtype filter never matches anything.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.events import EventType
from commanderblitz.engine.objects import PLUS_ONE
from tests.conftest import only_oid, pass_until

FOREST = "forest"
SNATCHER = "t_tfu_snatcher"  # morph {G}; "when this is turned face up, draw a card"
DREAD = "t_tfu_dread"  # "whenever you turn a permanent face up, +1/+1 counter on it"
TRAIL = "t_tfu_beast_trail"  # "whenever a Beast you control is turned face up, draw"
RAPTOR = "t_tfu_raptor"  # the same draw, heard from the graveyard
BEAST = "t_morpher"  # a Beast with morph {2}{G}, and no ability of its own


def board(builder, mine=(), theirs=(), *, graveyard=(), hand=()):
    """Player 0 with Forests, ``mine`` on the battlefield and ``hand``; player 1
    with Forests and ``theirs``. Returns the game; nothing is face down yet."""
    return (
        builder(players=2)
        .battlefield(0, [FOREST] * 8 + list(mine))
        .battlefield(1, [FOREST] * 8 + list(theirs))
        .graveyard(0, list(graveyard))
        .hand(0, list(hand))
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )


def turn_down(game, oid: int) -> None:
    """Make a permanent already on the battlefield face down, as a morph cast
    for {3} would have left it."""
    obj = game.state.objects[oid]
    obj.face_down = True
    obj.revealed_to.add(obj.controller)
    game.state.bump_chars()


def turn_up(game, oid: int) -> None:
    """Turn ``oid`` face up through the legal action its controller is offered,
    then let anything that triggered resolve."""
    pid = game.state.objects[oid].controller
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None
        and d.player == pid
        and d.kind is DecisionKind.PRIORITY,
    )
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)
    settle(game)


def settle(game) -> None:
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def hand(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def plus_ones(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(PLUS_ONE, 0)


class TestTheEvent:
    def test_turning_up_fires_it_naming_the_permanent(self, builder):
        game = board(builder, [BEAST])
        beast = only_oid(game, BEAST)
        turn_down(game, beast)

        turn_up(game, beast)

        fired = [e for e in game.state.events if e.type == EventType.TURNED_FACE_UP]
        assert len(fired) == 1
        assert (fired[0].player, fired[0].source, fired[0].data["oid"]) == (0, beast, beast)


class TestSelf:
    def test_its_own_turned_up_ability_hears_it(self, builder):
        """The ability lives on the hidden card, so this passes only because the
        event fires after the permanent is face up."""
        game = board(builder, [SNATCHER])
        snatcher = only_oid(game, SNATCHER)
        turn_down(game, snatcher)
        before = hand(game)

        turn_up(game, snatcher)

        assert hand(game) == before + 1

    def test_it_is_scoped_to_itself(self, builder):
        """`source: "self"`: another morph turning up is not this one."""
        game = board(builder, [SNATCHER, BEAST])
        turn_down(game, only_oid(game, BEAST))
        before = hand(game)

        turn_up(game, only_oid(game, BEAST))

        assert hand(game) == before

    def test_cast_face_up_it_never_fires(self, builder):
        """A morph creature cast for its mana cost was never turned face up, and
        entering is not turning up (708.8)."""
        game = board(builder, hand=[SNATCHER])
        line = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and not a.face_down
            and game.state.objects[a.source].def_id == SNATCHER
        )
        game.apply(line)
        settle(game)

        assert not [e for e in game.state.events if e.type == EventType.TURNED_FACE_UP]
        assert hand(game) == 0

    def test_a_real_morph_cast_face_down_then_turned_up(self, builder):
        """The whole route, through the {3} face-down cast rather than a test
        helper."""
        game = board(builder, hand=[SNATCHER])
        line = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.face_down)
        game.apply(line)
        settle(game)
        snatcher = only_oid(game, SNATCHER)
        assert game.state.objects[snatcher].face_down
        before = hand(game)

        turn_up(game, snatcher)

        assert hand(game) == before + 1


class TestAPermanentYouControl:
    def test_the_subject_is_the_turned_up_permanent(self, builder):
        """Growing Dread: the counter lands on the permanent turned up, not on
        the enchantment."""
        game = board(builder, [DREAD, BEAST])
        beast = only_oid(game, BEAST)
        turn_down(game, beast)

        turn_up(game, beast)

        assert plus_ones(game, beast) == 1
        assert chars(game.state, beast).power == 6

    def test_an_opponent_turning_theirs_up_does_not_count(self, builder):
        """`controller: "you"` -- the other seat's morph is not yours."""
        game = board(builder, [DREAD], [BEAST])
        beast = only_oid(game, BEAST)
        turn_down(game, beast)

        turn_up(game, beast)

        assert not game.state.objects[beast].face_down, "the turn-up happened"
        assert plus_ones(game, beast) == 0

    def test_it_also_fires_off_its_own_turn_up(self, builder):
        """Two triggers, one event: the snatcher's own and the Dread's."""
        game = board(builder, [DREAD, SNATCHER])
        snatcher = only_oid(game, SNATCHER)
        turn_down(game, snatcher)
        before = hand(game)

        turn_up(game, snatcher)

        assert hand(game) == before + 1
        assert plus_ones(game, snatcher) == 1


class TestTheFilterReadsTheFaceUpCard:
    def test_a_beast_turned_up_matches(self, builder):
        """The shell has no subtypes; only the face-up card is a Beast."""
        game = board(builder, [TRAIL, BEAST])
        turn_down(game, only_oid(game, BEAST))
        before = hand(game)

        turn_up(game, only_oid(game, BEAST))

        assert hand(game) == before + 1

    def test_a_non_beast_turned_up_does_not(self, builder):
        game = board(builder, [TRAIL, SNATCHER])
        snatcher = only_oid(game, SNATCHER)
        turn_down(game, snatcher)
        before = hand(game)

        turn_up(game, snatcher)

        # The snatcher's own draw, and nothing from the Trail.
        assert hand(game) == before + 1


class TestFromTheGraveyard:
    def test_a_graveyard_watcher_hears_it(self, builder):
        """Deathmist Raptor's shape: `active_zones: ["graveyard"]`, and "you"
        is the card's owner there."""
        game = board(builder, [BEAST], graveyard=[RAPTOR])
        turn_down(game, only_oid(game, BEAST))
        before = hand(game)

        turn_up(game, only_oid(game, BEAST))

        assert hand(game) == before + 1


class TestNothingElseFiresIt:
    def test_a_morph_cast_face_down_entering_is_not_turned_up(self, builder):
        game = board(builder, [DREAD], hand=[BEAST])
        line = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.face_down)
        game.apply(line)
        settle(game)

        beast = only_oid(game, BEAST)
        assert game.state.objects[beast].face_down
        assert not [e for e in game.state.events if e.type == EventType.TURNED_FACE_UP]
        assert plus_ones(game, beast) == 0
