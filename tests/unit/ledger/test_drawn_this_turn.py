"""Which cards in a hand were drawn this turn.

    "…If you do, choose two cards in your hand **drawn this turn** and put them
    back on top of your library."                        -- Sylvan Library

`GameState.cards_drawn_this_turn` has existed as long as the draw tally has, and
it is a per-player **integer**: it says how many, and no selector can ask which.
Nothing else distinguishes a card in hand drawn a moment ago from one that has
sat there since the opening hand -- both are simply cards in a hand -- so the
fact has to be recorded as the card is drawn or it is gone.

`draw_cards` is where it is recorded, for the tally's own reason: every draw
passes through that function, so a card cannot be drawn without being marked.

**The turn, not a flag.** A boolean would need clearing at a turn boundary, and
that is one more thing for the boundary to forget; a stale `true` reads as a
card drawn this turn that was not. Comparing a recorded turn against the current
one is self-clearing.
"""

from __future__ import annotations

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import matches
from automtg.engine.enums import Step
from automtg.engine.primitives import draw_cards
from tests.conftest import pass_until

DRAWN = {"zone": "hand", "controller": "you", "drawn_this_turn": True}
ANY_CARD = {"zone": "hand", "controller": "you"}


def board(builder, hand=(), library=()):
    return (
        builder(players=2)
        .hand(0, list(hand))
        .library(0, list(library) or ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def count(game, selector, controller: int = 0) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return sum(
        1
        for oid in game.state.players[controller].hand
        if matches(ctx, oid, selector, default_zone=None)
    )


class TestOnlyDrawnCardsMatch:
    def test_a_starting_hand_is_not_drawn_this_turn(self, builder):
        """The whole distinction. These cards are in hand and were not drawn
        now, and nothing about them says so except the mark."""
        game = board(builder, hand=["forest", "forest"])
        assert count(game, ANY_CARD) == 2
        assert count(game, DRAWN) == 0

    def test_a_card_drawn_now_matches(self, builder):
        game = board(builder, hand=["forest"])
        draw_cards(game.state, 0, 1)
        assert count(game, ANY_CARD) == 2
        assert count(game, DRAWN) == 1

    def test_several_draws_all_match(self, builder):
        game = board(builder, hand=["forest"])
        draw_cards(game.state, 0, 3)
        assert count(game, DRAWN) == 3


class TestItIsPerPlayer:
    def test_an_opponents_draw_does_not_mark_your_hand(self, builder):
        game = board(builder, hand=["forest"])
        draw_cards(game.state, 1, 2)
        assert count(game, DRAWN) == 0


class TestTheMarkIsSelfClearing:
    def test_a_card_drawn_last_turn_no_longer_matches(self, builder):
        """The wearing-off, and the reason the mark is a turn and not a flag.

        Nothing clears it: the comparison simply stops holding once the turn
        moves on, so no turn boundary has to remember to do anything.
        """
        game = (
            builder(players=2)
            .hand(0, ["forest"])
            .library(0, ["forest"] * 40)
            .library(1, ["forest"] * 40)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        draw_cards(game.state, 0, 1)
        assert count(game, DRAWN) == 1

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        assert count(game, DRAWN) == 0, "the card is still in hand, but not drawn now"
        assert count(game, ANY_CARD) >= 1, "...and it really is still in hand"
