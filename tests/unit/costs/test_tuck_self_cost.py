"""Timestream Navigator -- "{2}{U}{U}, {T}, **Put this creature on the bottom of
its owner's library**: Take an extra turn after this one."

Rule 601.2h (602.2b for an activation) pays every cost as the ability goes on
the stack. Written as the `put_on_top` op with ``bottom`` in the effects, the
creature would still be on the battlefield while the ability waited to resolve:
a second activation could be stacked on the first, and a countered ability would
leave the creature where it was. `sacrifice` is the other near miss, and it
sends the creature to the graveyard, where it was never meant to go.

So `tuck_self` is a boolean on the cost, the library twin of `exile_self`: no
choice, *this* permanent, the bottom of its **owner's** library.

`t_tuck_navigator` is the witness; `t_tuck_on_resolution` is the counterfactual
that tucks itself with the op, where the two visibly part company while the
ability is still on the stack.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, only_oid, settle

TUCKER = "t_tuck_navigator"
LATE = "t_tuck_on_resolution"


def position(builder, card_id: str = TUCKER, *, stolen: bool = False):
    """``card_id`` under player 0's control; owned by player 1 when ``stolen``.

    The Opt in hand keeps player 0 holding priority after the activation, so the
    ability waits on the stack instead of being auto-passed into resolution.
    """
    owner = 1 if stolen else 0
    game = (
        builder(players=2)
        .battlefield(owner, [card_id])
        .battlefield(0, ["island"] * 3)
        .hand(0, ["opt"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build()
    )
    oid = only_oid(game, card_id)
    if stolen:
        game.state.objects[oid].controller = 0
        game.state.bump_chars()
    return game, oid


def activate(game, oid: int) -> None:
    game.apply(activations(game, oid)[0])


class TestTheCostIsPaidOnActivation:
    def test_the_creature_is_in_the_library_before_the_ability_resolves(self, builder):
        game, oid = position(builder)
        activate(game, oid)
        assert game.state.stack, "the ability should still be waiting"
        assert game.state.objects[oid].zone is Zone.LIBRARY

    def test_it_goes_to_the_bottom(self, builder):
        game, oid = position(builder)
        activate(game, oid)
        assert game.state.players[0].library[-1] == oid

    def test_the_ability_still_happens(self, builder):
        game, oid = position(builder)
        before = len(game.state.players[0].hand)
        activate(game, oid)
        settle(game)
        assert len(game.state.players[0].hand) == before + 1
        assert oid not in game.state.players[0].hand

    def test_it_cannot_be_activated_a_second_time_in_response(self, builder):
        game, oid = position(builder)
        activate(game, oid)
        assert not activations(game, oid)


class TestTheResolutionCounterfactual:
    def test_the_op_leaves_it_on_the_battlefield_while_the_ability_waits(self, builder):
        game, oid = position(builder, LATE)
        activate(game, oid)
        assert game.state.stack
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_both_end_in_the_library(self, builder):
        """The difference is *when*, not *where*."""
        game, oid = position(builder, LATE)
        activate(game, oid)
        settle(game)
        assert game.state.objects[oid].zone is Zone.LIBRARY


class TestItGoesToItsOwnersLibrary:
    def test_a_stolen_creature_goes_home(self, builder):
        game, oid = position(builder, stolen=True)
        activate(game, oid)
        assert game.state.players[1].library[-1] == oid
        assert oid not in game.state.players[0].library


class TestThePaymentSolverKeepsItsHandsOff:
    def test_it_is_not_tap_only(self, builder):
        game, oid = position(builder)
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert not cost.is_tap_only()

    def test_it_describes_itself(self, builder):
        game, oid = position(builder)
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert "bottom of its owner's library" in cost.describe()


def _card(cost: dict, **extra) -> CardModel:
    text = "{1}: Draw a card."
    return CardModel.model_validate(
        {
            "id": "t_tuck_probe",
            "name": "Test Tuck Probe",
            "oracle_text": text,
            "mana_cost": "{1}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "activated",
                    "text": text,
                    "cost": cost,
                    "effects": [{"op": "draw", "player": "you"}],
                    **extra,
                }
            ],
        }
    )


class TestTheLoaderRefusals:
    def test_it_cannot_also_exile_the_source(self):
        with pytest.raises(DslError, match="tuck_self"):
            compile_card(_card({"mana": "{1}", "tuck_self": True, "exile_self": True}), source="test")

    def test_it_is_not_a_cast_time_cost(self):
        from commanderblitz.cards.loader.vocabulary import NOT_A_CAST_TIME_COST

        assert "tuck_self" in NOT_A_CAST_TIME_COST

    def test_it_does_not_pass_the_outside_the_battlefield_guard(self):
        """It requires the battlefield, so from a graveyard it would be inert."""
        with pytest.raises(DslError, match="removes its source"):
            compile_card(
                _card({"mana": "{1}", "tuck_self": True}, active_zones=["graveyard"]),
                source="test",
            )
