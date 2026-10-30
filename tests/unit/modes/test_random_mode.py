"""Choosing a mode at random, and "if you discarded a card this turn".

Typhoid Mary, Fractured -- "Whenever Typhoid Mary attacks, choose one at
random. If you discarded a card this turn, you choose one instead. • Mary --
Create a Treasure token. • Typhoid Mary -- Draw a card. • Bloody Mary -- Each
opponent loses 2 life and you gain 2 life."

`choose_mode` always asked somebody. ``random: true`` answers it off the game's
seeded `state.rng` instead, so a game replays from its seed; the near miss is
`roll_dice` with an `if` per face, which is a different card -- it rolls, and a
roll is an event "whenever you roll" cards see. ``choose_instead_if`` hands the
question back to the controller while its condition holds. Like every modal
trigger's, the choice is made as the trigger is put on the stack (603.3c), so
that is when the condition is read.

The condition is `cards_discarded_this_turn`, a per-seat count folded off
DISCARD. Mayhem's `TurnLedger.discarded` is the near miss: it records one
*object* and drops it at the next zone change (400.7), but a player who
discarded a card that has since left the graveyard still discarded a card this
turn.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import discard_cards
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, action_for_card, only_oid, pass_until, settle

MARY = "t_rm_mary"  # the attack trigger, random unless you discarded this turn
CHARM = "t_rm_charm"  # {0} sorcery: choose one at random -- gain 3 / draw
MODES = ["Mary", "Typhoid Mary", "Bloody Mary"]


def position(builder, *, seed: int = 0, battlefield=()):
    """We are seat 0 with Mary and two cards in hand, in our main phase.

    The Dark Ritual is a priority stop, so the engine does not auto-pass on
    past the turn this file is about.
    """
    return (
        builder(players=2, seed=seed)
        .battlefield(0, ["swamp", MARY, *battlefield])
        .hand(0, ["dark_ritual", "swamp", "swamp"])
        .library(0, ["swamp"] * 30)
        .library(1, ["swamp"] * 30)
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .max_turns(40)
        .build()
    )


def hand(game, pid: int) -> list[int]:
    return [o.oid for o in game.state.objects.values() if o.zone is Zone.HAND and o.owner == pid]


def discarded(game, who: str = "you", controller: int = 0) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return evaluate_value(ctx, {"cards_discarded_this_turn": who})


def attack(game, pick: str | None = None) -> list[list[str]]:
    """Attack with Mary and run past combat; return every mode question asked."""
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    mary = only_oid(game, MARY, 0)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.source == mary
        )
    )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    asked: list[list[str]] = []
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    for _ in range(400):
        if (game.state.turn, game.state.step) >= mark or game.over:
            return asked
        decision = game.pending()
        if decision is None:
            return asked
        if decision.kind is DecisionKind.CHOOSE_MODE:
            labels = [o.label for o in decision.options]
            asked.append(labels)
            index = labels.index(pick) if pick in labels else 0
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("combat did not finish")


def outcome(game, hand_before: int) -> str:
    """Which mode resolved, read off the board."""
    state = game.state
    treasures = [o for o in state.battlefield_objects(0) if o.def_id == "treasure_token"]
    if treasures:
        return "Mary"
    if state.players[0].life == 42 and state.players[1].life < 40:
        return "Bloody Mary"
    if len(hand(game, 0)) == hand_before + 1:
        return "Typhoid Mary"
    raise AssertionError("no mode resolved")


def random_outcome(builder, seed: int) -> str:
    game = position(builder, seed=seed)
    before = len(hand(game, 0))
    assert attack(game) == [], "a random pick asks nobody"
    return outcome(game, before)


class TestChosenAtRandom:
    def test_nobody_is_asked_and_one_mode_resolves(self, builder):
        assert random_outcome(builder, 0) in MODES

    def test_the_pick_is_deterministic_per_seed(self, builder):
        for seed in range(6):
            assert random_outcome(builder, seed) == random_outcome(builder, seed)

    def test_every_mode_comes_up_across_seeds(self, builder):
        seen = {random_outcome(builder, seed) for seed in range(24)}
        assert seen == set(MODES)

    def test_a_random_spell_is_answered_at_cast_too(self, builder):
        """`Game._ask_modes`' path: a spell's modes are chosen as it is cast."""
        seen = set()
        for seed in range(16):
            game = (
                builder(players=2, seed=seed)
                .hand(0, [CHARM])
                .library(0, ["swamp"] * 10)
                .life(0, 40)
                .active(0)
                .build()
            )
            game.apply(action_for_card(game, ActionKind.CAST, CHARM))
            assert game.pending() is None or game.pending().kind is not DecisionKind.CHOOSE_MODE
            settle(game)
            seen.add("gain" if game.state.players[0].life == 43 else "draw")
        assert seen == {"gain", "draw"}


class TestYouChooseInsteadAfterADiscard:
    def test_a_discard_this_turn_hands_the_choice_to_the_controller(self, builder):
        game = position(builder)
        discard_cards(game.state, 0, hand(game, 0)[-1:])
        asked = attack(game, pick="Bloody Mary")
        assert asked == [MODES]
        assert game.state.players[0].life == 42
        assert game.state.players[1].life < 40

    def test_a_discarded_card_that_left_the_graveyard_still_counts(self, builder):
        """Mayhem's per-object record is dropped here; the player's count is not."""
        game = position(builder)
        (card,) = hand(game, 0)[-1:]
        discard_cards(game.state, 0, [card])
        move_object(game.state, card, Zone.EXILE)
        assert card not in game.state.turn_ledger.discarded
        assert discarded(game) == 1
        assert attack(game, pick="Mary") == [MODES]

    def test_a_discard_replaced_into_exile_still_counts(self, builder):
        """Rest in Peace moves the card, but the player still discarded it."""
        game = position(builder, battlefield=["rest_in_peace"])
        (card,) = hand(game, 0)[-1:]
        discard_cards(game.state, 0, [card])
        assert game.state.objects[card].zone is Zone.EXILE
        assert discarded(game) == 1

    def test_an_opponents_discard_does_not_count(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["swamp", MARY])
            .hand(0, ["dark_ritual"])
            .hand(1, ["swamp"])
            .library(0, ["swamp"] * 30)
            .library(1, ["swamp"] * 30)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        discard_cards(game.state, 1, hand(game, 1))
        assert discarded(game, "you") == 0
        assert discarded(game, "each_opponent") == 1
        assert attack(game) == [], "still random"


class TestTheCountIsPerTurn:
    def test_it_counts_each_discard(self, builder):
        game = position(builder)
        discard_cards(game.state, 0, hand(game, 0)[-2:])
        assert discarded(game) == 2

    def test_it_resets_next_turn(self, builder):
        game = position(builder)
        discard_cards(game.state, 0, hand(game, 0)[-1:])
        assert discarded(game) == 1
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert game.state.turn != turn
        assert discarded(game) == 0
        assert discarded(game, "all") == 0


def _card(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "…",
            "mana_cost": "{1}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "…",
                    "trigger": {"event": "attacks", "source": "self", "controller": "you"},
                    "effects": [effect],
                }
            ],
        }
    )


def _modes(**extra) -> dict:
    return {
        "op": "choose_mode",
        "count": 1,
        "modes": [
            {"label": "A", "effects": [{"op": "draw", "player": "you"}]},
            {"label": "B", "effects": [{"op": "draw", "player": "you"}]},
        ],
        **extra,
    }


DISCARDED = {"cmp": ">", "left": {"cards_discarded_this_turn": "you"}, "right": {"const": 0}}


class TestTheLoader:
    def test_mary_loads(self, registry):
        spec = registry.get(MARY).abilities[0].effects[0]
        assert spec["random"] is True
        assert spec["choose_instead_if"] == DISCARDED

    def test_random_must_be_a_boolean(self):
        with pytest.raises(DslError, match="boolean"):
            compile_card(_card(_modes(random="yes")))

    @pytest.mark.parametrize(
        "extra",
        [
            {"up_to": True},
            {"or_more": True},
            {"chooser": "each_opponent"},
            {"up_to_if": {"condition": DISCARDED, "count": 2}},
        ],
    )
    def test_a_players_widening_is_refused_on_a_random_pick(self, extra):
        with pytest.raises(DslError, match="random"):
            compile_card(_card(_modes(random=True, **extra)))

    def test_choose_instead_if_needs_random(self):
        with pytest.raises(DslError, match="choose_instead_if"):
            compile_card(_card(_modes(choose_instead_if=DISCARDED)))

    def test_choose_instead_if_needs_a_valid_condition(self):
        with pytest.raises(DslError):
            compile_card(_card(_modes(random=True, choose_instead_if={"nonsense": 1})))

    def test_the_value_needs_a_player_spec(self):
        bad = {"cmp": ">", "left": {"cards_discarded_this_turn": 3}, "right": {"const": 0}}
        with pytest.raises(DslError, match="cards_discarded_this_turn"):
            compile_card(_card(_modes(random=True, choose_instead_if=bad)))
