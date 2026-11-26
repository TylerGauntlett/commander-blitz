"""Echo: pay for the permanent a second time, once, the upkeep after it arrives.

    Echo {1}{G} (At the beginning of your upkeep, if this came under your
    control since the beginning of your last upkeep, sacrifice it unless you
    pay its echo cost.)

702.30a is one triggered ability, and the whole of it that the DSL lacked was
its intervening-if. "Sacrifice it unless you pay" is `may` with a `pay` and a
sacrificing `else`, cumulative upkeep's shape. The clause is the
`came_under_control_since_last_upkeep` condition.

What would be wrong without it:

- `entered_this_turn` is already false at the next upkeep, so the card would
  never be asked to pay, a strictly cheaper card than the printed one;
- a `set_flag` written by the trigger asks once, but a change of control does
  not clear a flag. A stolen echo permanent must be paid for again by its new
  controller (800.4a makes the steal a change of control), and with a flag it
  never is.

So the condition compares two timestamps: when the permanent came under its
controller's control (its arrival or its last `change_control`) and when that
controller's last upkeep began. During that controller's upkeep "last" is the
one before, so the trigger holds both as it triggers and as it resolves (603.4).

Witness: Karmic Guide and Bone Shredder (`data/cards/auto/`), whose test twin
without the enters trigger is `t_echoer` (`tests/data/testing.cards.json`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.conditions import validate_condition
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import change_control
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, find_action, only_oid

OX = "t_echoer"  # {1}{G} 4/4 Ox, Echo {2}{G}


def position(builder):
    """Player 0's Ox on the battlefield in turn 1's main phase; both seats on Forests.

    It came under player 0's control on turn 1, before any upkeep of theirs, so
    their turn-3 upkeep is the one that asks. Each seat has three Forests, which
    is the echo cost and no more.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + [OX])
        .battlefield(1, ["forest"] * 3)
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )
    return game, only_oid(game, OX)


def is_echo_question(game) -> bool:
    decision = game.pending()
    return (
        decision is not None
        and decision.kind is DecisionKind.MAY
        and "echo" in decision.prompt.lower()
    )


def to_echo_question(game, *, until_turn: int):
    """Run until the echo payment is asked; ``None`` once ``until_turn`` passes."""
    for _ in range(800):
        decision = game.pending()
        if decision is None or game.over or game.state.turn > until_turn:
            return None
        if is_echo_question(game):
            return decision
        game.apply(_default_answer(game, decision))
    return None


def zone(game, oid):
    return game.state.objects[oid].zone


class TestTheFirstUpkeepAsks:
    def test_the_controllers_next_upkeep_asks(self, builder):
        game, _ = position(builder)
        decision = to_echo_question(game, until_turn=3)
        assert decision is not None
        assert decision.player == 0
        assert game.state.turn == 3 and game.state.step is Step.UPKEEP

    def test_an_opponents_upkeep_does_not(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        # Turn 2 was player 1's, and it went by unasked and unsacrificed.
        assert game.state.turn == 3
        assert zone(game, oid) is Zone.BATTLEFIELD

    def test_paying_keeps_it(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.YES))
        assert zone(game, oid) is Zone.BATTLEFIELD
        forests = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "forest"
        ]
        assert all(f.tapped for f in forests), "{2}{G} was paid with all three Forests"

    def test_declining_sacrifices_it(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.NO))
        assert zone(game, oid) is Zone.GRAVEYARD


class TestItAsksOnce:
    def test_the_second_upkeep_does_not_ask(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.YES))
        assert to_echo_question(game, until_turn=7) is None
        assert game.state.turn == 8
        assert zone(game, oid) is Zone.BATTLEFIELD


class TestANewObjectIsAskedAgain:
    def test_leaving_and_returning_asks_again(self, builder):
        """400.7: the returning permanent is a new object, newly under your control."""
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.YES))
        returned = move_object(game.state, oid, Zone.EXILE)
        returned = move_object(game.state, returned.oid, Zone.BATTLEFIELD)
        decision = to_echo_question(game, until_turn=5)
        assert decision is not None and decision.player == 0
        assert game.state.turn == 5


class TestAChangeOfControlReArmsIt:
    def test_the_new_controller_is_asked_at_their_upkeep(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.YES))
        # Stolen after player 0 paid; player 1's next upkeep is turn 4's.
        assert change_control(game.state, oid, 1)
        decision = to_echo_question(game, until_turn=4)
        assert decision is not None
        assert decision.player == 1 and game.state.turn == 4

    def test_the_new_controller_declining_sacrifices_it(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.YES))
        change_control(game.state, oid, 1)
        to_echo_question(game, until_turn=4)
        game.apply(find_action(game, ActionKind.NO))
        assert zone(game, oid) is Zone.GRAVEYARD
        assert game.state.objects[oid].owner == 0

    def test_a_handback_asks_the_old_controller_again(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.YES))
        change_control(game.state, oid, 1)
        to_echo_question(game, until_turn=4)
        game.apply(find_action(game, ActionKind.YES))
        change_control(game.state, oid, 0)
        decision = to_echo_question(game, until_turn=5)
        assert decision is not None and decision.player == 0

    def test_without_a_change_the_stolen_permanent_asks_once(self, builder):
        game, oid = position(builder)
        to_echo_question(game, until_turn=3)
        game.apply(find_action(game, ActionKind.YES))
        change_control(game.state, oid, 1)
        to_echo_question(game, until_turn=4)
        game.apply(find_action(game, ActionKind.YES))
        assert to_echo_question(game, until_turn=8) is None
        assert zone(game, oid) is Zone.BATTLEFIELD
        assert game.state.objects[oid].controller == 1


class TestTheGuard:
    def test_true_and_false_load(self):
        validate_condition({"came_under_control_since_last_upkeep": True}, "test")
        validate_condition({"came_under_control_since_last_upkeep": False}, "test")

    def test_a_string_is_refused(self):
        with pytest.raises(DslError, match="must be true or false"):
            validate_condition({"came_under_control_since_last_upkeep": "true"}, "test")

    def test_the_test_card_loads(self, registry):
        card = registry.get(OX)
        assert card.abilities[0].trigger is not None

    def test_a_card_spelling_it_wrong_is_refused(self):
        model = CardModel.model_validate(
            {
                "id": "t_echo_typo",
                "name": "Echo Typo",
                "mana_cost": "{G}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "trigger": {
                            "event": "upkeep",
                            "controller": "you",
                            "condition": {"came_under_control_since_last_upkeep": 1},
                        },
                        "effects": [{"op": "sacrifice", "objects": {"self_only": True}}],
                    }
                ],
            }
        )
        with pytest.raises(DslError):
            compile_card(model)
