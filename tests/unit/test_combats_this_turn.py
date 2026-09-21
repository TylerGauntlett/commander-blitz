"""Which combat phase of the turn this is.

    "Whenever equipped creature attacks, **if it's the first combat phase of the
    turn**, untap it. After this phase, there is an additional combat phase."
                                                            -- Genji Glove

The intervening if is the whole card. Without it the Glove untaps its creature
in the extra combat it just granted, which grants another, and the loop does not
stop -- so a card written without the clause is not a weaker Genji Glove, it is
an infinite combat engine.

`GameState.combat_number` is the near miss and cannot answer it. That counter is
**monotonic for the whole game on purpose**: a delayed trigger names the combat
it must fire in by that integer, so "at end of combat" would fire in the wrong
one if it ever reset. Two counters, because they answer two different questions
-- one identifies a combat for ever, and this one counts them within a turn.

`TurnLedger.combats` is therefore a second tally, cleared at cleanup with the
rest. It is written by `combat.start_combat` rather than folded in `emit` like
every other tally there, and deliberately: beginning a combat emits no event,
and inventing one to carry a counter would put an entry on the trigger bus that
no card subscribes to.

A value rather than a boolean condition head, so the ordinary `cmp` says it. The
printed clause is `== 1`; "the second combat" needs no new vocabulary.

`max_per_turn: 1` is the other near miss and is a different card: it caps how
often the ability fires, so a creature that sat out the first combat and
attacked in a later one would still get its extra combat.
"""

from __future__ import annotations

from automtg.engine.combat import start_combat
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value
from automtg.engine.enums import Step
from tests.conftest import pass_until

FIRST = {"cmp": "==", "left": {"combats_this_turn": True}, "right": {"const": 1}}


def combats(game) -> int:
    return evaluate_value(
        EffectContext(state=game.state, controller=0), {"combats_this_turn": True}
    )


def fresh(builder):
    return builder(players=2).battlefield(0, ["forest"]).build(advance=False)


class TestTheCountWithinATurn:
    def test_no_combat_yet_is_nought(self, builder):
        assert combats(fresh(builder)) == 0

    def test_the_first_combat_is_one(self, builder):
        """Counting the combat in progress, so the printed clause is `== 1`."""
        game = fresh(builder)
        start_combat(game.state)
        assert combats(game) == 1

    def test_an_extra_combat_is_two(self, builder):
        game = fresh(builder)
        start_combat(game.state)
        start_combat(game.state)
        assert combats(game) == 2

    def test_it_resets_between_turns(self, builder):
        """Cleared at cleanup with the rest of the ledger.

        Without this the clause would be true on turn one and false for ever
        after -- a card that works once and then quietly stops.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .library(0, ["forest"] * 40)
            .library(1, ["forest"] * 40)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        pass_until(game, lambda g: g.state.turn > turn + 1, limit=800)
        assert combats(game) <= 1, "each turn starts its own count"


class TestItIsNotTheMonotonicCounter:
    def test_combat_number_keeps_climbing(self, builder):
        """The contrast, measured rather than asserted in a comment.

        `combat_number` must never reset -- a delayed trigger names its combat
        by it -- so the two counters part company the moment a second turn's
        combat begins.
        """
        game = fresh(builder)
        start_combat(game.state)
        start_combat(game.state)
        assert game.state.combat_number == 2
        assert combats(game) == 2

        game.state.turn_ledger.clear()  # what cleanup does
        start_combat(game.state)
        assert game.state.combat_number == 3, "still climbing"
        assert combats(game) == 1, "but this turn's first combat"


class TestAsThePrintedClause:
    def test_it_is_true_in_the_first_combat(self, builder):
        from automtg.engine.effects.conditions import evaluate_condition

        game = fresh(builder)
        start_combat(game.state)
        assert evaluate_condition(game.state, FIRST, controller=0)

    def test_it_is_false_in_the_second(self, builder):
        """The assertion Genji Glove's loop turns on."""
        from automtg.engine.effects.conditions import evaluate_condition

        game = fresh(builder)
        start_combat(game.state)
        start_combat(game.state)
        assert not evaluate_condition(game.state, FIRST, controller=0)
