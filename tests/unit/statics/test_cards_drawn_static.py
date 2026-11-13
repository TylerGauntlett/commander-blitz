"""A static sized by how many cards a player has drawn this turn.

    "Creatures you control get +X/+X, where X is the number of cards you've
    drawn this turn."                              -- Knowledge Is Power

A static's magnitude is read continuously (611.3a), so the anthem is bigger
the instant a card is drawn, and back to nothing when the turn that counted
the draws ends. `{"cards_drawn_this_turn": spec}` is the leaf, the effect
side's draw tally in its bare player-spec form.

The near miss is a pump trigger on `draw`: it misses a creature that enters
after the draws (the anthem covers it the moment it lands) and lingers on one
that changes controller. Only a static sized by the tally is the printed card.

What the tests pin, each invisible on screen:

- **It follows the tally.** `chars` is cached per `char_version`. The draw's
  zone change bumps it *before* `primitives.draw_cards` writes the tally, so a
  cache warmed in between would keep the old size; the draw and the untap
  step's reset both bump after writing.
- **It stays acyclic** (ADR 0001). The tally is player state written only by
  `draw_cards` and the untap step, never by a layer of `characteristics`.

Knowledge Is Power is the shipped witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import draw_cards
from tests.conftest import only_oid, pass_until, pt

ANTHEM = "t_draw_anthem"  # creatures you control get +X/+X, X = cards you drew this turn
BEAR = "t_bear"  # {1}{G} 2/2


def position(builder, step=Step.PRECOMBAT_MAIN):
    """Player 0 on turn 3 with the anthem and a Bear; player 1 with a Bear.

    Turn 3 rather than 1, where a two-player game's starting player skips the
    draw (103.8a).
    """
    game = (
        builder(players=2)
        .turn(3)
        .battlefield(0, [ANTHEM, BEAR])
        .battlefield(1, [BEAR])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(step)
        .build()
    )
    return game, only_oid(game, BEAR, 0)


class TestItFollowsTheTally:
    def test_no_draws_is_the_printed_size(self, builder):
        game, bear = position(builder)
        assert pt(game, bear) == (2, 2)

    def test_each_draw_grows_it(self, builder):
        game, bear = position(builder)
        pt(game, bear)  # warm the cache
        draw_cards(game.state, 0, 1)
        assert pt(game, bear) == (3, 3)
        draw_cards(game.state, 0, 2)
        assert pt(game, bear) == (5, 5)

    def test_a_cache_warmed_mid_draw_does_not_miss_it(self, builder):
        """The move bumps before the tally is written; the write bumps again."""
        game, bear = position(builder)
        state = game.state
        version = state.char_version
        draw_cards(state, 0, 1)
        assert state.char_version > version + 1
        assert pt(game, bear) == (3, 3)

    def test_the_draw_step_counts(self, builder):
        """Building at upkeep runs the turn-based draw (504.1) on the way in."""
        game, bear = position(builder, step=Step.UPKEEP)
        assert game.state.cards_drawn_this_turn == {0: 1}
        assert pt(game, bear) == (3, 3)

    def test_the_next_turn_resets_it(self, builder):
        game, bear = position(builder)
        draw_cards(game.state, 0, 2)
        assert pt(game, bear) == (4, 4)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert pt(game, bear) == (2, 2)


class TestWhoseDraws:
    def test_an_opponents_draws_do_not_count(self, builder):
        game, bear = position(builder)
        pt(game, bear)
        draw_cards(game.state, 1, 3)
        assert pt(game, bear) == (2, 2)

    def test_it_buffs_only_your_creatures(self, builder):
        game, _ = position(builder)
        theirs = only_oid(game, BEAR, 1)
        draw_cards(game.state, 0, 2)
        assert pt(game, theirs) == (2, 2)

    def test_the_effect_side_reads_the_same_tally(self, builder):
        game, _ = position(builder)
        draw_cards(game.state, 0, 2)
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"cards_drawn_this_turn": "you"}) == 2
        assert evaluate_value(ctx, {"cards_drawn_this_turn": "each_opponent"}) == 0


class TestTheLoader:
    def _card(self, amount):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Creatures you control get +X/+X.",
                "mana_cost": "{1}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Creatures you control get +X/+X.",
                        "effect": "buff",
                        "affects": {"controller": "you", "types": ["Creature"]},
                        "power": amount,
                        "toughness": amount,
                    }
                ],
            }
        )

    def test_a_well_formed_static_loads(self):
        compile_card(self._card({"cards_drawn_this_turn": "you"}))

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError, match="cards_drawn_this_turn"):
            compile_card(self._card({"cards_drawn_this_turn": "active_player"}))

    def test_a_non_spec_is_refused(self):
        with pytest.raises(DslError, match="cards_drawn_this_turn"):
            compile_card(self._card({"cards_drawn_this_turn": {"player": "you"}}))
