""""You can't cast this during your first, second, or third turns of the game."

    Serra Avenger -- "You can't cast Serra Avenger during your first, second,
    or third turns of the game. Flying, vigilance"

Nothing counted a player's turns. `GameState.turn` is the table's count and
`round` the log's, and neither is "your third turn": in a pod the third turn of
the game is somebody else's first. So `PlayerState.turns_begun` counts the turns
each seat has begun, extra turns included (500.7), bumped as the untap step
opens, and the card says how many of them it waits out in
`cant_cast_first_turns`.

It is a "can't", not a timing window, so it is asked in
`player_statics.player_cant_cast_spells` with the card in hand -- the question
every cast path, the resolution-time ones included, already asks (101.2).
"During **your** turns" is the other half: on an opponent's turn, with flash,
the card can be cast.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import pass_until

AVENGER = "t_ccft_avenger"
FLASH_AVENGER = "t_ccft_flash_avenger"


def board(builder, card_id: str = AVENGER, *, turns_begun: int, active: int = 0):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 2)
        .hand(0, [card_id])
        .turns_begun(0, turns_begun)
        .active(active)
        .build()
    )


def castable(game, card_id: str = AVENGER) -> bool:
    return any(
        a.kind is ActionKind.CAST
        and a.source is not None
        and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


class TestYourFirstThreeTurns:
    @pytest.mark.parametrize("turn", [1, 2, 3])
    def test_it_cannot_be_cast(self, builder, turn):
        assert not castable(board(builder, turns_begun=turn))

    def test_on_your_fourth_turn_it_can(self, builder):
        assert castable(board(builder, turns_begun=4))


class TestOnlyYourOwnTurns:
    def test_with_flash_it_can_be_cast_on_an_opponents_turn(self, builder):
        game = board(builder, FLASH_AVENGER, turns_begun=1, active=1)
        pass_until(game, lambda g: g.pending() is not None and g.pending().player == 0)
        assert castable(game, FLASH_AVENGER)


class TestTheCount:
    def test_each_turn_a_player_begins_counts_once(self, builder):
        game = builder(players=2).turns_begun(0, 0).turns_begun(1, 0).build()
        pass_until(game, lambda g: g.state.active_player == 1)
        pass_until(game, lambda g: g.state.active_player == 0)
        assert game.state.players[0].turns_begun == 1
        assert game.state.players[1].turns_begun == 1


class TestTheLoader:
    def test_zero_turns_is_refused(self):
        model = CardModel.model_validate(
            {"id": "t_probe", "name": "Probe", "types": ["Creature"], "power": 1,
             "toughness": 1, "cant_cast_first_turns": 0}
        )
        with pytest.raises(DslError, match="cant_cast_first_turns"):
            compile_card(model)
