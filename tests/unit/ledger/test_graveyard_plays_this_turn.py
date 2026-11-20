"""The turn's graveyard-play tally: "if you've cast a spell from a graveyard or
activated an ability of a card in a graveyard this turn".

Laboratory Drudge -- "At the beginning of each end step, draw a card if you've
cast a spell from a graveyard or activated an ability of a card in a graveyard
this turn" -- is the witness. It asks about two *events*, and by the end step
the board cannot answer either: a spell's `cast_from_zone` keeps only that
card's latest cast, whatever turn it was, and an unearth or scavenge exiled its
card as the cost was paid (602.2b) and left nothing behind. Rule 601.2a puts the spell on the stack
from the zone it was cast from, and 602.2 makes an activation happen as it is
announced, so those are the moments to count.

So it is a per-player tally on the turn ledger, `TurnLedger.graveyard_plays`:
a cast is counted in the SPELL_CAST fold off the zone `stack.push_spell`
stamped, and an activation in `Game._activate` before the cost is paid, while
the card is still in the graveyard. Keyed by the caster or activator, from any
graveyard.

The near misses the gap record names: `spells_cast_this_turn` counts every cast
from every zone; `cards_from_graveyard_this_turn` counts every card leaving a
graveyard (a reanimation, an exile) and no activation that leaves the card
there; and an unprinted `spell_cast` trigger setting a turn flag would miss
every play made before the Drudge entered. The ledger clears at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import activations, only_oid, pass_until, settle

DRUDGE = "t_drudge_watcher"  # each end step: draw if you played from a graveyard
CANTRIP = "t_flashback_cantrip"  # instant, {1}: gain 1 life; flashback {1}
GRAVE = "t_grave_lifegain"  # "{1}, Exile this card from your graveyard: gain 2 life"
BOARD = "t_board_lifegain"  # "{1}: gain 2 life", on the battlefield

PLAYED = {"cmp": ">", "left": {"graveyard_plays_this_turn": "you"}, "right": {"const": 0}}


def position(builder, mine=(), hand=(), graveyard=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 4 + list(mine))
        .battlefield(1, ["plains"] * 2 + list(theirs))
        # A land in hand anchors the main phase: with no play left, the engine
        # would auto-pass the rest of the turn away once the stack empties.
        .hand(0, ["plains", *hand])
        .graveyard(0, list(graveyard))
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def tally(game, who="you", controller=0) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return evaluate_value(ctx, {"graveyard_plays_this_turn": who})


def cast(game, card_id: str, zone: Zone) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
        and game.state.objects[a.source].zone is zone
    )
    game.apply(action)
    settle(game)


def activate(game, oid: int) -> None:
    game.apply(activations(game, oid)[0])
    settle(game)


def card(game, card_id: str) -> int:
    """The one object of a card, in whatever zone it is now."""
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == card_id]
    return oid


def end_step_draws(game, turn: int, pid: int = 0) -> int:
    """Cards ``pid`` drew in the end step of ``turn``."""
    return sum(
        1
        for e in game.state.events
        if e.type == EventType.DRAW and e.player == pid and e.turn == turn and e.step == Step.END_STEP
    )


def run_through_end_step(game) -> int:
    """Play out this turn's end step; return the turn it was."""
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn != turn
        or (g.state.step is Step.CLEANUP and not g.state.stack and not g.state.pending_triggers),
    )
    return turn


class TestACastFromAGraveyardCounts:
    def test_a_flashback_cast_is_counted_for_its_caster(self, builder):
        game = position(builder, graveyard=[CANTRIP])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        assert game.state.turn_ledger.graveyard_plays == {0: 1}
        assert tally(game) == 1

    def test_the_same_spell_cast_from_hand_is_not(self, builder):
        game = position(builder, hand=[CANTRIP])
        cast(game, CANTRIP, Zone.HAND)
        assert game.state.turn_ledger.spells_cast == {0: 1}
        assert tally(game) == 0

    def test_it_still_counts_after_the_spell_has_left_for_exile(self, builder):
        """Flashback exiles the card on resolution (702.34a); the cast still counted."""
        game = position(builder, graveyard=[CANTRIP])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        assert game.state.objects[card(game, CANTRIP)].zone is Zone.EXILE
        assert tally(game) == 1


class TestAGraveyardActivationCounts:
    def test_an_ability_whose_cost_exiles_its_card_still_counts(self, builder):
        game = position(builder, graveyard=[GRAVE])
        grave = card(game, GRAVE)
        activate(game, grave)
        assert game.state.objects[grave].zone is Zone.EXILE
        assert game.state.players[0].life == 42
        assert tally(game) == 1

    def test_the_same_ability_on_the_battlefield_does_not(self, builder):
        game = position(builder, mine=[BOARD])
        activate(game, only_oid(game, BOARD, 0))
        assert game.state.players[0].life == 42
        assert tally(game) == 0

    def test_a_cast_and_an_activation_are_one_tally(self, builder):
        game = position(builder, graveyard=[CANTRIP, GRAVE])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        activate(game, card(game, GRAVE))
        assert tally(game) == 2


class TestItIsPerPlayer:
    def test_your_plays_are_not_your_opponents(self, builder):
        game = position(builder, graveyard=[CANTRIP])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        assert tally(game, "each_opponent") == 0
        assert tally(game, "you", controller=1) == 0


class TestItIsAnOrdinaryCondition:
    def test_the_comparison_turns_on(self, builder):
        game = position(builder, graveyard=[CANTRIP])
        assert not evaluate_condition(game.state, PLAYED, controller=0)
        cast(game, CANTRIP, Zone.GRAVEYARD)
        assert evaluate_condition(game.state, PLAYED, controller=0)

    def test_an_unknown_spelling_is_refused(self):
        with pytest.raises(DslError):
            validate_value({"graveyard_plays_last_turn": "you"}, "test")


class TestTheEndStepTrigger:
    def test_it_draws_after_a_graveyard_cast(self, builder):
        game = position(builder, mine=[DRUDGE], graveyard=[CANTRIP])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        turn = run_through_end_step(game)
        assert end_step_draws(game, turn) == 1

    def test_it_draws_nothing_without_one(self, builder):
        game = position(builder, mine=[DRUDGE], hand=[CANTRIP])
        cast(game, CANTRIP, Zone.HAND)
        turn = run_through_end_step(game)
        assert end_step_draws(game, turn) == 0

    def test_a_play_made_before_it_entered_counts(self, builder):
        """No trigger was watching the cast; the ledger was."""
        game = position(builder, hand=[DRUDGE], graveyard=[CANTRIP])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        cast(game, DRUDGE, Zone.HAND)
        assert game.state.objects[only_oid(game, DRUDGE, 0)].zone is Zone.BATTLEFIELD
        turn = run_through_end_step(game)
        assert end_step_draws(game, turn) == 1

    def test_on_another_players_end_step_it_reads_its_controller(self, builder):
        """It triggers on each end step, and "you" is still its controller."""
        game = position(builder, theirs=[DRUDGE], graveyard=[CANTRIP])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        turn = run_through_end_step(game)
        assert end_step_draws(game, turn, 1) == 0


class TestItWearsOff:
    def test_the_tally_is_gone_next_turn(self, builder):
        game = position(builder, graveyard=[CANTRIP])
        cast(game, CANTRIP, Zone.GRAVEYARD)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert tally(game) == 0
