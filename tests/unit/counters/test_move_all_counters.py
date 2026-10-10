"""Moving **all** counters, including off a permanent that has already left.

The Ozolith, both lines:

- "Whenever a creature you control leaves the battlefield, if it had counters on
  it, put **those counters** on The Ozolith."
- "…you may move **all counters** from The Ozolith onto target creature."

Every other card in the `move_counters` family names one kind — graft moves a
+1/+1, modular moves its +1/+1s. "Those counters" and "all counters" mean the
whole multiset: every kind, each with its own amount. Writing The Ozolith as
`{"counter": "+1/+1"}` compiles, resolves, and silently drops charge, oil,
loyalty and every other kind a creature was carrying — a card that looks
implemented and is quietly smaller than printed. `TestTheOneKindVersionIsWrong`
keeps that spelling alive and shows the difference.

The first line has a second problem on top: by the time it resolves the creature
is **gone**, and `reset_permanent_state` emptied its counters on the way out. So
the counts come from the leave event's `had_counters` snapshot — the same place
`counters_had` reads, and the explicit last-known-information pattern `snapshot`
established rather than a general LKI system.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.primitives import add_counters
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until

OZOLITH = "t_ozolith"  # all kinds, off a departed creature
ONE_KIND = "t_ozolith_one_kind"  # the same trigger naming +1/+1 only
MOVER = "t_counter_mover"  # all kinds, off a live permanent
BEAR = "t_bear"


def position(builder, artifact: str):
    game = (
        builder(players=2)
        .battlefield(0, [artifact, BEAR, "forest", "forest"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 10)
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def kill_and_settle(game, oid: int) -> None:
    """Send ``oid`` to the graveyard and let the leave trigger actually resolve.

    Waiting on an empty stack is wrong twice over here. A trigger is *queued*
    when the event fires and only reaches the stack at a later priority window,
    so the stack is empty immediately after `move_object` and a stack-watching
    predicate returns before the ability has been put on it -- reading exactly
    like a trigger that never fired. Waiting for `ability_resolved` instead
    watches the thing the test is actually about.
    """
    mark = len(game.state.events)
    move_object(game.state, oid, Zone.GRAVEYARD, cause="test")
    pass_until(
        game,
        lambda g: "ability_resolved" in [e.type for e in g.state.events[mark:]],
    )


def counters_on(game, oid) -> dict[str, int]:
    return {k: v for k, v in game.state.objects[oid].counters.items() if v > 0}


class TestOffADepartedCreature:
    def test_every_kind_arrives(self, builder):
        """Two kinds on the Bear, both on the artifact after it dies."""
        game = position(builder, OZOLITH)
        bear, rock = only_oid(game, BEAR), only_oid(game, OZOLITH)
        add_counters(game.state, bear, "+1/+1", 3)
        add_counters(game.state, bear, "charge", 2)

        kill_and_settle(game, bear)

        assert counters_on(game, rock) == {"+1/+1": 3, "charge": 2}

    def test_a_creature_with_no_counters_moves_nothing(self, builder):
        """The intervening-if: "**if it had counters on it**"."""
        game = position(builder, OZOLITH)
        bear, rock = only_oid(game, BEAR), only_oid(game, OZOLITH)

        kill_and_settle(game, bear)

        assert counters_on(game, rock) == {}


class TestTheOneKindVersionIsWrong:
    def test_it_drops_every_other_kind(self, builder):
        """Kept as a live card because it is the mistake this option prevents.

        The +1/+1s arrive and the charge counters are simply gone -- no error,
        no warning, a card that reads as implemented.
        """
        game = position(builder, ONE_KIND)
        bear, rock = only_oid(game, BEAR), only_oid(game, ONE_KIND)
        add_counters(game.state, bear, "+1/+1", 3)
        add_counters(game.state, bear, "charge", 2)

        kill_and_settle(game, bear)

        assert counters_on(game, rock) == {"+1/+1": 3}, "the charge counters were dropped"


class TestOffALivePermanent:
    def test_all_kinds_move_and_the_source_is_emptied(self, builder):
        """The second line: a live source, so the counters must also LEAVE it."""
        from commanderblitz.engine.enums import ActionKind

        game = position(builder, MOVER)
        rock, bear = only_oid(game, MOVER), only_oid(game, BEAR)
        add_counters(game.state, rock, "+1/+1", 2)
        add_counters(game.state, rock, "charge", 1)
        game.state.bump_chars()

        action = next(
            a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == rock
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert counters_on(game, bear) == {"+1/+1": 2, "charge": 1}
        assert counters_on(game, rock) == {}, "moved, not copied"
