"""The turn's loyalty-activation tally: "if you didn't activate a loyalty ability".

The Chain Veil -- "At the beginning of your end step, **if you didn't activate a
loyalty ability of a planeswalker this turn**, you lose 2 life" -- is the
witness. It asks about an *event*, and the board cannot answer it: a
planeswalker that minused itself to zero is in the graveyard by the end step,
and one that was flickered is a new object (400.7) with no record of what the
old one did. The per-ability tally `ability_activations` is keyed by exactly
those oids, so reading it back at the end step would forget both.

So it is a per-player tally on the turn ledger, counted in `Game._activate` at
the moment of activation (602.2), beside the per-ability tally: an activation
whose ability was countered, or whose cost killed its own source, was still an
activation. It counts only abilities with a loyalty cost (606.1) whose source
is a planeswalker as it is activated -- a planeswalker's `{T}` ability is not a
loyalty ability, and "of a planeswalker" is printed.

The near miss the gap record names is a `has_turn_flag` set by an unprinted
`ability_activated` trigger on the Veil, which misses every activation made
before the Veil entered. Rule 603.4 does the rest: the intervening if is read
when the end step begins and again on resolution, and the ledger clears at
cleanup, after the end step.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, pass_until

VEIL = "t_veil_keeper"  # your end step, if you activated no loyalty ability: lose 2
WALKER = "t_walker"  # loyalty 4; "+1: gain 2 life" and "-3: draw a card"
TAPPER = "t_tapper_walker"  # "+1: gain 2 life" and "{T}: gain 1 life"

DIDNT = {"cmp": "==", "left": {"loyalty_activations_this_turn": "you"}, "right": {"const": 0}}


def position(builder, mine=(WALKER,), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 2 + list(mine))
        .battlefield(1, ["plains"] * 2 + list(theirs))
        # A land in hand anchors the main phase: with no play left, the engine
        # would auto-pass the rest of the turn away once the stack empties.
        .hand(0, ["plains"])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def tally(game, who="you", controller=0) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return evaluate_value(ctx, {"loyalty_activations_this_turn": who})


def activate(game, oid: int, label: str) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid and label in (a.label or "")
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def run_through_end_step(game) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn != turn
        or (g.state.step is Step.CLEANUP and not g.state.stack and not g.state.pending_triggers),
    )


class TestTheLedgerCountsIt:
    def test_a_loyalty_activation_is_counted_for_its_player(self, builder):
        game = position(builder)
        activate(game, only_oid(game, WALKER, 0), "+1")
        assert game.state.turn_ledger.loyalty_activations == {0: 1}
        assert tally(game) == 1

    def test_nothing_activated_is_zero(self, builder):
        game = position(builder)
        assert tally(game) == 0

    def test_it_is_per_player(self, builder):
        game = position(builder)
        activate(game, only_oid(game, WALKER, 0), "+1")
        assert tally(game, "each_opponent") == 0

    def test_a_walker_that_minused_itself_away_still_counts(self, builder):
        """The reason this is a ledger: by the end step the walker is gone."""
        game = position(builder)
        walker = only_oid(game, WALKER, 0)
        game.state.objects[walker].counters["loyalty"] = 3
        activate(game, walker, "-3")
        assert game.state.objects[walker].zone is Zone.GRAVEYARD
        assert tally(game) == 1


class TestOnlyLoyaltyAbilitiesCount:
    def test_a_planeswalkers_tap_ability_is_not_a_loyalty_ability(self, builder):
        game = position(builder, mine=[TAPPER])
        activate(game, only_oid(game, TAPPER, 0), "{T}")
        assert tally(game) == 0


class TestItIsAnOrdinaryCondition:
    def test_the_comparison_turns_off(self, builder):
        game = position(builder)
        assert evaluate_condition(game.state, DIDNT, controller=0)
        activate(game, only_oid(game, WALKER, 0), "+1")
        assert not evaluate_condition(game.state, DIDNT, controller=0)

    def test_an_unknown_spelling_is_refused(self):
        with pytest.raises(DslError):
            validate_value({"loyalty_activations_last_turn": "you"}, "test")


class TestTheEndStepTrigger:
    def test_it_fires_without_an_activation(self, builder):
        game = position(builder, mine=[WALKER, VEIL])
        run_through_end_step(game)
        assert game.state.players[0].life == 38

    def test_it_does_not_fire_after_one(self, builder):
        game = position(builder, mine=[WALKER, VEIL])
        activate(game, only_oid(game, WALKER, 0), "-3")
        run_through_end_step(game)
        assert game.state.players[0].life == 40

    def test_it_is_only_your_own_end_step(self, builder):
        game = position(builder, theirs=[VEIL])
        run_through_end_step(game)
        assert game.state.players[1].life == 40


class TestItWearsOff:
    def test_the_tally_is_gone_next_turn(self, builder):
        game = position(builder)
        activate(game, only_oid(game, WALKER, 0), "+1")
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert tally(game) == 0
