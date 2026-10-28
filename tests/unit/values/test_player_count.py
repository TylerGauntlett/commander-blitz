""""Where X is **the number of opponents you have**" -- a headcount of seats.

Dack Fayden, Helping Hand reveals "until you reveal X creature cards, where X is
the number of opponents you have". Every player value the language had measured
something *about* the players -- `life_of`, `max_poison_of`, `cards_in_hand`,
`unspent_mana_count` -- and summed or extremed it; `count` counts objects and
cannot reach a player at all. Nothing said how many players a spec names, so the
card's X was unsayable, and a `const` 3 would be the four-player card in a
four-player game only: one opponent down, it reveals one creature too many and
there is nobody left to hand it to.

Rule 800.4a: a player who has left the game is out of it, so they are nobody's
opponent and the count drops with them. `select_players` already resolves the
plural specs to living seats; the leaf filters again so that a binding or a
target naming a seat that has since left is not counted either.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError

OPPONENTS = {"player_count": "each_opponent"}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def table(builder, players: int):
    return builder(players=players).build(advance=False)


class TestItCountsSeats:
    @pytest.mark.parametrize("players", [2, 3, 4])
    def test_the_number_of_opponents_you_have(self, builder, players):
        assert value(table(builder, players), OPPONENTS) == players - 1

    def test_you_is_one(self, builder):
        assert value(table(builder, 4), {"player_count": "you"}) == 1

    def test_each_player_includes_you(self, builder):
        assert value(table(builder, 4), {"player_count": "each_player"}) == 4

    def test_it_reads_from_the_controllers_seat(self, builder):
        game = table(builder, 3)
        assert value(game, OPPONENTS, controller=2) == 2


class TestAPlayerWhoLeftIsNobodysOpponent:
    def test_an_eliminated_opponent_drops_out(self, builder):
        game = table(builder, 4)
        game.state.players[3].has_lost = True
        assert value(game, OPPONENTS) == 2

    def test_a_seat_named_directly_that_has_left_is_not_counted(self, builder):
        game = table(builder, 3)
        game.state.players[1].has_lost = True
        assert value(game, {"player_count": 1}) == 0

    def test_the_last_one_standing_has_no_opponents(self, builder):
        game = table(builder, 2)
        game.state.players[1].has_lost = True
        assert value(game, OPPONENTS) == 0


class TestTheLoaderGuardsIt:
    def test_the_witness_shape_validates(self):
        validate_value(OPPONENTS, "probe")

    def test_a_non_player_spec_is_refused(self):
        with pytest.raises(DslError, match="player_count: needs a player spec"):
            validate_value({"player_count": "opponents"}, "probe")

    def test_a_number_is_refused(self):
        """A bare seat number is not a spec a card can print; `const` is the
        spelling for a number."""
        with pytest.raises(DslError, match="player_count: needs a player spec"):
            validate_value({"player_count": 3}, "probe")
