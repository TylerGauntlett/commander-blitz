"""Descend -- "if you descended this turn".

Enterprising Scallywag: "At the beginning of your end step, if you descended
this turn, create a Treasure token. (You descended if a permanent card was put
into your graveyard from anywhere.)" And "the number of times you descended this
turn" is the same record counted rather than tested: each permanent card that
arrives is one descent, so two creature cards milled together are two.

Three facts in the reminder text, and each near miss gets one wrong:

- **a permanent card** -- `cards_to_graveyard_this_turn` counts an instant too;
- **put into your graveyard from anywhere** -- `permanents_to_graveyard_this_turn`
  sees only the battlefield, so a milled or discarded creature card is missed;
- **your** graveyard -- both of those are table-wide, so an opponent's dead
  creature would make you descend.

And a **card**: a token reaching a graveyard is no descent (111.1). The value
reads `TurnLedger.graveyard_arrivals`, which already keeps every card arrival
with its graveyard's owner and leaves tokens out, so a card that has since left
the graveyard still counted as the descent it was.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token, discard_cards, mill_cards
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of

BEAR = "t_bear"
INSTANT = "t_plain_instant"
SOLDIER = "human_soldier_1_1_w"


def descended(game, who="you", controller: int = 0) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return evaluate_value(ctx, {"descended_this_turn": who})


def board(builder, *, library=(), hand=(), battlefield=()):
    return (
        builder(players=2)
        .library(0, list(library))
        .hand(0, list(hand))
        .battlefield(0, list(battlefield))
        .build(advance=False)
    )


class TestAPermanentCardFromAnywhere:
    def test_nothing_yet(self, builder):
        assert descended(board(builder)) == 0

    def test_a_creature_card_milled(self, builder):
        game = board(builder, library=[BEAR, "forest"])
        mill_cards(game.state, 0, 1)
        assert descended(game) == 1

    def test_a_land_card_discarded(self, builder):
        game = board(builder, hand=["forest"])
        discard_cards(game.state, 0, list(game.state.players[0].hand))
        assert descended(game) == 1

    def test_a_creature_dying(self, builder):
        game = board(builder, battlefield=[BEAR])
        (oid,) = oids_of(game, BEAR, 0)
        move_object(game.state, oid, Zone.GRAVEYARD, cause="test")
        assert descended(game) == 1

    def test_each_card_is_a_descent(self, builder):
        """"The number of times you descended": two together are two."""
        game = board(builder, library=[BEAR, "forest", "forest"])
        mill_cards(game.state, 0, 3)
        assert descended(game) == 3

    def test_a_card_that_left_again_still_descended(self, builder):
        game = board(builder, library=[BEAR])
        (oid,) = mill_cards(game.state, 0, 1)
        move_object(game.state, oid, Zone.HAND, to_player=0, cause="test")
        assert descended(game) == 1


class TestWhatIsNoDescent:
    def test_an_instant_card(self, builder):
        game = board(builder, library=[INSTANT])
        mill_cards(game.state, 0, 1)
        assert descended(game) == 0

    def test_a_token(self, builder):
        game = board(builder)
        (token,) = create_token(game.state, SOLDIER, 0)
        move_object(game.state, token, Zone.GRAVEYARD, cause="test")
        assert descended(game) == 0

    def test_an_opponents_graveyard(self, builder):
        game = builder(players=2).library(1, [BEAR]).build(advance=False)
        mill_cards(game.state, 1, 1)
        assert descended(game, "you") == 0
        assert descended(game, "opponent") == 1


class TestItIsThisTurns:
    def test_the_ledger_clears(self, builder):
        game = board(builder, library=[BEAR])
        mill_cards(game.state, 0, 1)
        game.state.turn_ledger.clear()
        assert descended(game) == 0


class TestTheLoaderRefuses:
    @pytest.mark.parametrize("bad", [True, 1, None])
    def test_a_value_that_is_not_a_player_spec(self, bad):
        with pytest.raises(DslError, match="descended_this_turn"):
            validate_value({"descended_this_turn": bad}, "amount")
