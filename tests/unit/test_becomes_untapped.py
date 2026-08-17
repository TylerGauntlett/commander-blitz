"""Inspired (702.117): "Whenever this creature becomes untapped, …".

The census called this "needs a 'becomes untapped' event", and the event had
existed since combat was written -- `untap_permanent` has always fired
`UNTAPPED`. Subscribing to it looked like a one-line job and was not, for a
reason that would have shipped a keyword that never triggers.

**Inspired fires in the untap step, and the untap step did not say what it
untapped.** `untap_all` emitted a single aggregate carrying a `count` and no
`oid`, through `state.emit` rather than `triggers.fire` -- so it never reached
the trigger bus at all, and even if it had there was no permanent named for
`source: "self"` to match. Every other path to becoming untapped goes through
`untap_permanent`, which fires per permanent; the untap step was the one
exception, and it is the one that matters, because a creature that attacked
untaps in its controller's next untap step and almost nowhere else.

So `untap_all` now fires one event per permanent, exactly as
`untap_permanent` does. Nothing on the frontend changed: `untapped` is in the
`SILENT` set in `logic/events.ts` and `describeEvent` has never had a case for
it, so the aggregate's `count` had no consumer to lose.

The boundary that matters in the other direction is that a permanent which was
already untapped does not become untapped. `untap_all` skips those, and so does
`untap_permanent` -- an inspired creature that sat out a turn draws nothing.
"""

from __future__ import annotations

from automtg.engine.enums import Step
from automtg.engine.events import EventType
from automtg.engine.primitives import tap_permanent, untap_permanent
from tests.conftest import _default_answer, only_oid, pass_until

INSPIRED = "t_inspired"  # 1/3, "whenever this becomes untapped, draw a card"
BEAR = "t_bear"


def cards_in_hand(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def untap_events(game) -> list:
    return [e for e in game.state.events if e.type == EventType.UNTAPPED]


def at_untap(game):
    """Arm a position built at `Step.UNTAP` so the untap step actually runs.

    `GameBuilder.build` leaves `step_started` true: the position is described as
    already *being* in that step, not as about to enter it, so the turn-based
    actions have notionally happened. For every other step that is invisible --
    nothing is asserted about them -- but the untap step's turn-based action is
    the entire subject of this file, and without this every position below would
    silently skip it and read as "nothing untapped".
    """
    game.state.step_started = False
    return game


def to_main(game) -> None:
    """Run the turn-based actions from the untap step into the first main.

    `pass_until` cannot start from here. The untap step grants no priority
    (`NO_PRIORITY_STEPS`), so `game.pending()` is `None` and it returns without
    advancing anything at all -- the position is left exactly as built and every
    assertion afterwards reads a turn that never happened.
    """
    game._advance()
    pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN)


def settle(game, limit: int = 30) -> None:
    """Resolve whatever is waiting, advancing when nobody has priority."""
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


class TestTheUntapStepNamesWhatItUntapped:
    def test_it_fires_one_event_per_permanent(self, builder):
        """The change: an aggregate with a `count` became N events with oids."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, BEAR, BEAR], tapped=True)
            .turn(3)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        at_untap(game)
        before = len(untap_events(game))
        game._advance()
        fired = untap_events(game)[before:]
        assert len(fired) == 3
        assert all(e.data.get("oid") is not None for e in fired), (
            "the aggregate carried a count and no oid, so nothing could match "
            "`source: \"self\"`"
        )

    def test_an_already_untapped_permanent_fires_nothing(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .turn(3)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        at_untap(game)
        before = len(untap_events(game))
        game._advance()
        assert len(untap_events(game)) == before


class TestInspired:
    def test_the_untap_step_triggers_it(self, builder):
        """Where inspired actually fires, and what the aggregate event broke."""
        game = (
            builder(players=2)
            .battlefield(0, [INSPIRED], tapped=True)
            .turn(3)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        at_untap(game)
        before = cards_in_hand(game)
        to_main(game)
        assert cards_in_hand(game) == before + 2, (
            "one for the draw step, one for inspired"
        )

    def test_untapping_it_directly_triggers_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [INSPIRED])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oid = only_oid(game, INSPIRED, 0)
        tap_permanent(game.state, oid)
        before = cards_in_hand(game)
        untap_permanent(game.state, oid)
        settle(game)
        assert cards_in_hand(game) == before + 1

    def test_an_untapped_creature_draws_nothing(self, builder):
        """The boundary: it did not *become* untapped, it already was.

        An inspired creature that sat out a turn draws nothing, which is the
        whole reason the keyword is worth attacking with.
        """
        game = (
            builder(players=2)
            .battlefield(0, [INSPIRED])
            .turn(3)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        at_untap(game)
        before = cards_in_hand(game)
        to_main(game)
        assert cards_in_hand(game) == before + 1, "the draw step only"

    def test_somebody_elses_creature_untapping_does_not_trigger_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [INSPIRED])
            .battlefield(1, [BEAR], tapped=True)
            .turn(3)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        at_untap(game)
        oid = only_oid(game, BEAR, 1)
        before = cards_in_hand(game)
        untap_permanent(game.state, oid)
        settle(game)
        assert cards_in_hand(game) == before

    def test_a_skipped_untap_triggers_nothing(self, builder):
        """`skip_untap` is spent by the step whether or not it skipped
        anything, and a permanent it held down never became untapped."""
        game = (
            builder(players=2)
            .battlefield(0, [INSPIRED], tapped=True)
            .turn(3)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        at_untap(game)
        game.state.objects[only_oid(game, INSPIRED, 0)].skip_next_untap = True
        before = cards_in_hand(game)
        to_main(game)
        assert cards_in_hand(game) == before + 1, "the draw step only"
        assert game.state.objects[only_oid(game, INSPIRED, 0)].tapped
