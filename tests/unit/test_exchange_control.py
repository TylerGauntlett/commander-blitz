"""Exchanging control of two permanents -- one act, or nothing.

"Exchange control of target artifact or creature you control and target
creature an opponent controls with power 3 or less." Oko, Thief of Crowns' -5.

Rule 701.12a: each controller gains control of the permanent the other one
controlled, indefinitely. 701.12b is the rule that makes it one op rather than
two `gain_control`s: "if the entire exchange can't be completed, no part of the
exchange occurs." Written as two steals, the Oko player whose Food was destroyed
in response still takes the opponent's creature and pays nothing for it, which
is a strictly better card. And two permanents under one controller are not
exchanged either, because there is nothing to swap.

Each half is an ordinary control change, so a creature arriving this way is
summoning sick for its new controller (302.6) and still goes to its owner's
graveyard when it dies (400.3). That is `change_control`'s contract, and it is
asserted here once to show the exchange goes through it.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.structs import TargetRef
from automtg.engine.zones import destroy, move_object
from tests.conftest import only_oid, pass_until

SWAP = {"op": "exchange_control", "first": {"target": "t1"}, "second": {"target": "t2"}}


def a_board(builder, *, sick: bool = False):
    """Player 0's Sol Ring facing player 1's Test Bear; both oids."""
    game = (
        builder(players=2)
        .battlefield(0, ["sol_ring"])
        .battlefield(1, ["t_bear"], sick=sick)
        .build()
    )
    return game, only_oid(game, "sol_ring"), only_oid(game, "t_bear")


def swap(game, first: int | None, second: int | None) -> None:
    """Resolve the exchange as player 0's ability, with whichever targets survive."""
    targets = {}
    if first is not None:
        targets["t1"] = (TargetRef.obj(first),)
    if second is not None:
        targets["t2"] = (TargetRef.obj(second),)
    ctx = EffectContext(state=game.state, controller=0, targets=targets)
    gen = OPS["exchange_control"](ctx, SWAP)
    try:
        decision = next(gen)
    except StopIteration:
        return
    raise AssertionError(f"the exchange asked an unexpected question: {decision}")


class TestTheExchange:
    def test_each_side_takes_the_other(self, builder):
        game, ring, bear = a_board(builder)
        swap(game, ring, bear)
        assert game.state.objects[ring].controller == 1
        assert game.state.objects[bear].controller == 0

    def test_ownership_does_not_move(self, builder):
        game, ring, bear = a_board(builder)
        swap(game, ring, bear)
        assert game.state.objects[ring].owner == 0
        assert game.state.objects[bear].owner == 1

    def test_it_lasts_past_the_turn(self, builder):
        game, ring, bear = a_board(builder)
        swap(game, ring, bear)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn + 1)
        assert game.state.objects[bear].controller == 0

    def test_it_is_an_ordinary_control_change(self, builder):
        """Sick for its new controller, and it dies to its owner."""
        game, ring, bear = a_board(builder)
        swap(game, ring, bear)
        assert game.state.objects[bear].summoning_sick(game.state.turn)
        destroy(game.state, bear)
        assert bear in game.state.players[1].graveyard


class TestNoPartOfItHappens:
    def test_when_the_first_target_is_gone(self, builder):
        """608.2b dropped the illegal target; 701.12b then stops the rest."""
        game, ring, bear = a_board(builder)
        move_object(game.state, ring, Zone.GRAVEYARD)
        swap(game, None, bear)
        assert game.state.objects[bear].controller == 1

    def test_when_the_second_target_is_gone(self, builder):
        game, ring, bear = a_board(builder)
        move_object(game.state, bear, Zone.GRAVEYARD)
        swap(game, ring, None)
        assert game.state.objects[ring].controller == 0

    def test_when_a_target_left_after_being_checked(self, builder):
        """A target that is still in the list but no longer on the battlefield."""
        game, ring, bear = a_board(builder)
        move_object(game.state, ring, Zone.HAND)
        swap(game, ring, bear)
        assert game.state.objects[bear].controller == 1

    def test_when_one_player_controls_both(self, builder):
        game, ring, bear = a_board(builder)
        game.state.objects[bear].controller = 0
        swap(game, ring, bear)
        assert game.state.objects[ring].controller == 0
        assert game.state.objects[bear].controller == 0


class TestTheLoaderGuards:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_swapper",
                "name": "Test Swapper",
                "mana_cost": "{2}{U}",
                "types": ["Sorcery"],
                "oracle_text": "Exchange control of target creature you control and "
                "target creature an opponent controls.",
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "selector": {"types": ["Creature"], "controller": "you"},
                    },
                    {
                        "id": "t2",
                        "kind": "permanent",
                        "selector": {"types": ["Creature"], "controller": "opponent"},
                    },
                ],
                "spell_effects": [effect],
            }
        )

    def test_the_two_target_form_loads(self):
        compile_card(self._card(SWAP))

    def test_a_missing_half_is_refused(self):
        with pytest.raises(DslError, match="needs 'second'"):
            compile_card(self._card({"op": "exchange_control", "first": {"target": "t1"}}))

    def test_an_undeclared_target_is_refused(self):
        with pytest.raises(DslError, match="does not declare"):
            compile_card(self._card({**SWAP, "second": {"target": "t9"}}))

    def test_a_duration_is_refused(self):
        with pytest.raises(DslError, match="duration"):
            compile_card(self._card({**SWAP, "duration": "until_end_of_turn"}))
