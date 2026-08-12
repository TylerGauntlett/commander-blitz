"""Rule 509.1h, from the attacker's side: flanking, rampage, bushido, frenzy.

`docs/keywords.md` groups these four and says why: "each want a *trigger event*
the engine does not have ('becomes blocked', 'attacks and isn't blocked'), which
is a different tier of work". They are one capability rather than four, because
both events are decided at the same instant -- when the block declaration closes
-- and neither is knowable a moment earlier. "Isn't blocked" in particular is
not an event that happens; it is the absence of one, which only becomes a fact
when the declaration is over.

The engine already had `BLOCKS`, and it could not stand in for either. `BLOCKS`
fires once per *blocker* and is about the blocker: an attacker blocked by three
creatures sees three unrelated events concerning somebody else, and an attacker
blocked by nobody sees nothing at all. Everything the four keywords ask is about
the attacker.

`blockers` on the event is the count, because rampage is "+N/+N for each
creature blocking it **beyond the first**" and the card should do that
arithmetic rather than the engine guessing which off-by-one was meant.

Flanking needed one thing more. "Blocked by a creature without flanking" is a
question about *which* creatures are blocking this attacker, and the `blocking`
selector was a bare boolean -- true for every blocker in every combat, so on a
board with two attackers flanking would shrink the wrong creatures. It now also
takes a binding naming the attacker, which is the shape `shares_a_type_with` and
`exclude_binding` already established.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.events import EventType
from automtg.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, oids_of, only_oid, pass_until

RAMPAGER = "t_rampager"  # 3/3, rampage 2
FRENZIED = "t_frenzied"  # 2/2, frenzy 3
FLANKER = "t_flanker"  # 2/2, flanking
BEAR = "t_bear"  # 2/2
WALL = "t_wall"  # a defender, so several blockers are available


def to_attackers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)


def to_blockers(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)


def attack_with(game, oid: int, defender: int = 1):
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(defender),))
    )


def block_with(game, blocker_oid: int, attacker_oid: int):
    game.apply(
        find_action(
            game,
            ActionKind.ADD_BLOCKER,
            source=blocker_oid,
            targets=(TargetRef.obj(attacker_oid),),
        )
    )


def done(game):
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def settle(game, limit: int = 40) -> None:
    """Resolve the triggers the declaration queued, without leaving the turn.

    Everything these keywords do is "until end of turn", so an assertion made
    after the turn has rolled over reads a board `clear_until_eot` has
    correctly wiped -- rampage looks like it did nothing, which is exactly what
    a broken rampage looks like. The turn is asserted rather than hoped for,
    and every position holds an instant and a land so priority genuinely stops
    instead of auto-passing into the next turn.
    """
    turn = game.state.turn
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        assert game.state.turn == turn, "the turn rolled over before the assertion"
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the block triggers never resolved")


def combat_of(builder, attacker: str, blockers: list[str]):
    """`attacker` attacks; each of `blockers` blocks it. Returns (game, oid)."""
    game = (
        builder(players=2)
        .hand(0, ["t_bolt"])
        .battlefield(0, ["mountain", attacker])
        .battlefield(1, blockers)
        .build()
    )
    oid = only_oid(game, attacker, 0)
    to_attackers(game)
    attack_with(game, oid)
    done(game)
    # The defending player is asked whether to block whether or not they can,
    # and `finish_blockers` -- which fires both of these events -- runs only
    # once that declaration closes. Skipping it when there is nothing to block
    # with leaves the step open and no event fired, which is not the engine
    # declining to say "unblocked": it is nobody having finished declaring.
    to_blockers(game)
    for blocker_oid in [b for name in set(blockers) for b in oids_of(game, name, 1)]:
        block_with(game, blocker_oid, oid)
    done(game)
    settle(game)
    assert game.state.turn == 1, "still the turn the declaration happened in"
    return game, oid


def events_of(game, kind: str) -> list:
    return [e for e in game.state.events if e.type == kind]


class TestTheEventsAreExclusiveAndUniversal:
    def test_a_blocked_attacker_gets_became_blocked(self, builder):
        game, oid = combat_of(builder, BEAR, [WALL])
        fired = events_of(game, EventType.BECAME_BLOCKED)
        assert len(fired) == 1
        assert fired[0].data["attacker"] == oid
        assert not events_of(game, EventType.ATTACKED_UNBLOCKED)

    def test_an_unblocked_attacker_gets_the_other_one(self, builder):
        """The half that lives outside the `if combat.blockers` guard."""
        game, oid = combat_of(builder, BEAR, [])
        fired = events_of(game, EventType.ATTACKED_UNBLOCKED)
        assert len(fired) == 1
        assert fired[0].data["attacker"] == oid
        assert not events_of(game, EventType.BECAME_BLOCKED)

    def test_a_creature_that_did_not_attack_gets_neither(self, builder):
        game = (
            builder(players=2)
            .hand(0, ["t_bolt"])
            .battlefield(0, ["mountain", BEAR, WALL])
            .build()
        )
        wall = only_oid(game, WALL, 0)
        to_attackers(game)
        attack_with(game, only_oid(game, BEAR, 0))
        done(game)
        settle(game)
        for kind in (EventType.BECAME_BLOCKED, EventType.ATTACKED_UNBLOCKED):
            assert all(e.data["attacker"] != wall for e in events_of(game, kind))

    def test_the_blocker_count_is_on_the_event(self, builder):
        game, _ = combat_of(builder, BEAR, [WALL, WALL])
        (fired,) = events_of(game, EventType.BECAME_BLOCKED)
        assert fired.data["blockers"] == 2


class TestRampage:
    def test_one_blocker_is_no_bonus(self, builder):
        """The boundary the keyword is written around: "beyond the first"."""
        game, oid = combat_of(builder, RAMPAGER, [WALL])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (3, 3)

    def test_two_blockers_is_one_step(self, builder):
        game, oid = combat_of(builder, RAMPAGER, [WALL, WALL])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (5, 5)

    def test_three_blockers_is_two_steps(self, builder):
        game, oid = combat_of(builder, RAMPAGER, [WALL, WALL, WALL])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (7, 7)

    def test_unblocked_is_no_bonus(self, builder):
        game, oid = combat_of(builder, RAMPAGER, [])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (3, 3)


class TestFrenzy:
    def test_unblocked_gets_the_bonus(self, builder):
        game, oid = combat_of(builder, FRENZIED, [])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (5, 2)

    def test_blocked_does_not(self, builder):
        """The exact complement of rampage, off the same declaration."""
        game, oid = combat_of(builder, FRENZIED, [WALL])
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 2)


class TestFlanking:
    def test_the_blocker_shrinks(self, builder):
        game, attacker = combat_of(builder, FLANKER, [BEAR])
        blocker = only_oid(game, BEAR, 1)
        c = chars(game.state, blocker)
        assert (c.power, c.toughness) == (1, 1)
        del attacker

    def test_a_creature_blocking_somebody_else_does_not_shrink(self, builder):
        """What the bare `blocking: true` selector got wrong.

        Two attackers, two blockers, one block each. The boolean form matches
        every creature that is blocking anything, so it would shrink both --
        and on a one-attacker board, which is every test that would have been
        written for this, it looks perfect.
        """
        game = (
            builder(players=2)
            .hand(0, ["t_bolt"])
            .battlefield(0, ["mountain", FLANKER, BEAR])
            .battlefield(1, [WALL, "t_big"])
            .build()
        )
        flanker = only_oid(game, FLANKER, 0)
        other = only_oid(game, BEAR, 0)
        wall = only_oid(game, WALL, 1)
        big = only_oid(game, "t_big", 1)
        to_attackers(game)
        attack_with(game, flanker)
        attack_with(game, other)
        done(game)
        to_blockers(game)
        block_with(game, wall, flanker)
        block_with(game, big, other)
        done(game)
        settle(game)
        shrunk = chars(game.state, wall)
        untouched = chars(game.state, big)
        assert shrunk.toughness == _printed(game, wall).toughness - 1
        assert untouched.toughness == _printed(game, big).toughness, (
            "the creature blocking the *other* attacker is none of flanking's business"
        )

    def test_unblocked_shrinks_nobody(self, builder):
        game, _ = combat_of(builder, FLANKER, [])
        assert not events_of(game, EventType.BECAME_BLOCKED)


def _printed(game, oid: int):
    return game.state.card_of(game.state.objects[oid])
