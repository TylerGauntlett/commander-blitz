"""The continuous "you can't lose the game" -- 104.3b as a static.

    Gideon of the Trials — "0: You get an emblem with 'As long as you control a
    Gideon planeswalker, you can't lose the game and your opponents can't win
    the game.'"

`cant_lose_the_game` was a one-shot op with a turn-scoped `OutcomeLock` (Angel's
Grace), and the continuous Platinum Angel shape was recorded as deliberately
unbuilt -- so the emblem could not be written. It is two player-wide statics,
`cant_lose_the_game` and `cant_win_the_game`, each naming its players with
`affects_player`, both carrying the "as long as" as an ordinary `condition`.

What would be wrong without each claim:

- **The condition is live, not sampled.** The protection must stop the moment
  the last Gideon leaves (a player at 0 life then loses) and start again when
  one arrives. A static read once would keep protecting or never start.
- **The halves name different players.** "You can't lose" is the controller;
  "your opponents can't win" is everyone else. Swapping them would protect the
  opponent and forbid yourself from winning.
- **Every loss reason is held off**, as the op already does -- life, poison,
  the empty library.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.enums import Zone
from automtg.engine.errors import DslError
from automtg.engine.sba import player_cant_lose, player_cant_win
from automtg.engine.zones import move_object

HOLDER = "t_gideon_emblem_holder"
GIDEON = "t_test_gideon"


def board(builder, *, gideon: bool = True):
    mine = [HOLDER, "plains"] + ([GIDEON] if gideon else [])
    return builder(players=2).battlefield(0, mine).battlefield(1, ["forest"]).build(advance=False)


def oid_of(game, def_id):
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == def_id)


class TestTheConditionIsLive:
    def test_with_a_gideon_you_cannot_lose(self, builder):
        game = board(builder)
        assert player_cant_lose(game.state, 0)

    def test_without_one_the_emblem_does_nothing(self, builder):
        game = board(builder, gideon=False)
        assert not player_cant_lose(game.state, 0)
        assert not player_cant_win(game.state, 1)

    def test_the_last_gideon_leaving_ends_it(self, builder):
        game = board(builder)
        game.state.players[0].life = 0
        sba._player_losses(game.state)
        assert not game.state.players[0].has_lost, "held in the game at 0 life"
        move_object(game.state, oid_of(game, GIDEON), Zone.GRAVEYARD)
        game.state.bump_chars()
        sba._player_losses(game.state)
        assert game.state.players[0].has_lost


class TestTheHalvesNameDifferentPlayers:
    def test_your_opponents_cannot_win(self, builder):
        game = board(builder)
        assert player_cant_win(game.state, 1)

    def test_you_still_can_win_and_they_can_still_lose(self, builder):
        game = board(builder)
        assert not player_cant_win(game.state, 0)
        assert not player_cant_lose(game.state, 1)


class TestEveryLossReasonIsHeldOff:
    @pytest.mark.parametrize("reason", ["life", "poison", "library"])
    def test_held_in_the_game(self, builder, reason):
        game = board(builder)
        player = game.state.players[0]
        if reason == "life":
            player.life = -5
        elif reason == "poison":
            player.poison = 10
        else:
            player.attempted_draw_from_empty = True
        sba._player_losses(game.state)
        assert not player.has_lost


class TestTheLoaderGuard:
    def _card(self, static):
        return CardModel.model_validate(
            {
                "id": "t_bad_angel",
                "name": "Test Bad Angel",
                "oracle_text": "You can't lose the game.",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "abilities": [
                    {"kind": "static", "text": "You can't lose the game.", **static}
                ],
            }
        )

    def test_it_needs_affects_player(self):
        with pytest.raises(DslError, match="affects_player"):
            compile_card(self._card({"effect": "cant_lose_the_game"}))

    def test_a_permanent_filter_is_refused(self):
        with pytest.raises(DslError, match="affects"):
            compile_card(
                self._card(
                    {
                        "effect": "cant_lose_the_game",
                        "affects_player": "you",
                        "affects": {"types": ["Creature"]},
                    }
                )
            )
