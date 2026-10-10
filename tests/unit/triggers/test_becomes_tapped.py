""""Whenever this creature becomes tapped, …" -- the other half of inspired.

The trigger Legolas's Quick Reflexes grants, and the one City of Brass and the
painlands print. `EventType.TAPPED` has fired from `primitives.tap_permanent`
since tapping existed; what it had was no **name** in `TRIGGER_EVENTS`, so no
card could subscribe to it.

Unlike `becomes_untapped`, which needed the untap step taught to say what it
untapped, this really is the one-line job that one looked like: every route to
tapping a permanent already goes through `tap_permanent`, including tapping for
mana and being declared as an attacker. Those are taps, and the printed cards
are played for exactly those two cases.

**"Becomes" is already right at the primitive.** `tap_permanent` returns early on
a permanent that is already tapped, so re-tapping one is not a second event --
which is the whole of the distinction between *being* tapped and *becoming*
tapped, and it is asserted below in both directions.
"""

from __future__ import annotations

from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import tap_permanent, untap_permanent
from tests.conftest import only_oid, pass_until

WATCHER = "t_bt_pinger"  # "whenever this creature becomes tapped, draw a card"
MANALAND = "t_bt_land"  # "whenever this land becomes tapped, draw a card"
BEAR = "t_bt_bear"


def board(builder, mine=()):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .library(0, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def settle(game) -> None:
    """Let a triggered ability reach the stack and resolve.

    Two things here are deliberate, and both are about *when* a trigger reaches
    the stack rather than about tapping.

    `_advance` first, because these tests tap through the primitives rather than
    through a game action: the trigger is collected but nothing has yet offered
    priority.

    And the predicate waits on `pending_triggers` as well as the stack. A
    trigger is put on the stack when its **controller** would receive priority,
    and after a tap made outside the action system priority can land on the
    other player first -- at which point the stack is empty, a PRIORITY decision
    is pending, and a predicate reading only those two would declare the work
    done with the trigger still queued.
    """
    game._advance()
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def hand(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def tap_events(game) -> list:
    return [e for e in game.state.events if e.type == EventType.TAPPED]


class TestItFiresOnATap:
    def test_tapping_the_creature_draws(self, builder):
        game = board(builder, [WATCHER])
        before = hand(game)
        tap_permanent(game.state, only_oid(game, WATCHER))
        settle(game)
        assert hand(game) == before + 1

    def test_it_is_scoped_to_itself(self, builder):
        """`source: "self"` -- tapping somebody else is not this creature
        becoming tapped, and a trigger that read the event's player instead
        would fire on every tap its controller made."""
        game = board(builder, [WATCHER, BEAR])
        before = hand(game)
        tap_permanent(game.state, only_oid(game, BEAR))
        settle(game)
        assert hand(game) == before


class TestBecomingIsNotBeing:
    def test_tapping_an_already_tapped_permanent_fires_nothing(self, builder):
        """The boundary. A permanent that is already tapped does not *become*
        tapped, so a second tap is not a second trigger."""
        game = board(builder, [WATCHER])
        watcher = only_oid(game, WATCHER)
        tap_permanent(game.state, watcher)
        settle(game)
        before = hand(game)

        assert not tap_permanent(game.state, watcher), "the primitive declines it"
        settle(game)
        assert hand(game) == before

    def test_untapping_and_tapping_again_does_fire(self, builder):
        """The other side of the same boundary, so the test above is measuring
        "already tapped" and not "only ever fires once".

        Both taps happen before anything settles, so the two triggers are
        collected in one window -- resolving in between would carry the turn on
        past the main phase and leave the second tap nowhere to be seen.
        """
        game = board(builder, [WATCHER])
        watcher = only_oid(game, WATCHER)
        before = hand(game)

        tap_permanent(game.state, watcher)
        untap_permanent(game.state, watcher)
        tap_permanent(game.state, watcher)
        settle(game)

        assert hand(game) == before + 2


class TestTappingForManaIsATap:
    """The case the printed cards are played for: City of Brass, the painlands.

    A mana ability is activated inside cost payment, where nothing may be
    queued, so the trigger it causes has to survive until priority -- which is
    what makes this worth asserting rather than assuming.
    """

    def test_a_land_tapped_for_mana_triggers(self, builder):
        game = board(builder, [MANALAND])
        land = only_oid(game, MANALAND)
        before = hand(game)

        activate_mana_ability(game.state, land, 1, 0)
        settle(game)

        assert hand(game) == before + 1

    def test_the_event_really_names_the_land(self, builder):
        game = board(builder, [MANALAND])
        land = only_oid(game, MANALAND)
        activate_mana_ability(game.state, land, 1, 0)
        assert [e.data.get("oid") for e in tap_events(game)] == [land]
