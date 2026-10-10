""""Repeat this process." A mandatory loop whose length nobody knows up front.

Sphinx's Tutelage: "Whenever you draw a card, target opponent mills two cards. If
two nonland cards that share a color were milled this way, repeat this process."

A **do-while**: the body always runs once — that first mill is what the trigger is
about — and the condition is re-read after each pass, because the printed sentence
is a decision about repeating rather than a guard on starting.

Neither existing loop can say it:

- **`repeat`** evaluates `amount` once, above the loop, so the count must be
  knowable before the body runs. Here there is no number to write at all: how
  many times depends on what each mill turns up.
- **`may` with `repeat: true`** is the only other unbounded loop and is a
  *player-choice* loop — it asks the controller yes/no before every pass and stops
  at the first no, and its `condition` only gates whether the question is asked.
  Sphinx's Tutelage never asks anybody, so that spelling is a different and
  strictly weaker card: its controller could decline, and the opponent's mill
  would be optional.

**`reset` is the subtle half and is not a convenience.** `mill`'s `as` binding
deliberately *accumulates* (`earlier + milled`), because the ops it was built for
ask about everything a spell milled. Inside a loop that is the wrong question: the
second pass would test the colour clause over all four cards milled so far, where
"milled this way" is per repetition. `t_tutelage_unscoped` is that card, kept live,
and `TestTheAccumulatingBindingIsTheTrap` measures the difference on a board where
the two disagree.

The hundred-iteration guard is `repeat`'s and `may`'s, for the same reason: one
pathological board must not hang a game.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError

TUTELAGE = "t_tutelage_spell"  # with `reset`
UNSCOPED = "t_tutelage_unscoped"  # without it -- the trap
FOREVER = "t_forever_loop"  # a condition that never goes false

GREEN_BEAR = "t_bear"  # G creature
GREEN_DORK = "t_dork"  # G creature
RED_BOLT = "t_bolt"  # R instant
BLUE_FLYER = "t_flyer"  # U creature
PLAINS = "plains"  # a land: excluded by the filter, so it stops the loop


def position(builder, library: list[str], spell: str = TUTELAGE, pad: int = 40):
    """Player 1's library is stacked exactly, so every mill is deterministic.

    Padded with lands, which the `not_types` filter drops — so once the stacked
    cards run out the loop always stops, and a test can never hang on a board it
    did not mean to build.
    """
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 3)
        .hand(0, [spell])
        .library(0, ["plains"] * 10)
        .library(1, [*library, *[PLAINS] * pad])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )


def cast_and_settle(game, card_id: str, limit: int = 400) -> None:
    from tests.conftest import _default_answer

    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            game._advance()
            decision = game.pending()
            if decision is None:
                return
        if decision.kind is DecisionKind.PRIORITY and decision.player == 0:
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == card_id
                ),
                None,
            )
            if action is not None:
                game.apply(action)
                for _ in range(limit):
                    if not game.state.stack:
                        return
                    d = game.pending()
                    if d is None:
                        return
                    game.apply(_default_answer(game, d))
                return
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never cast {card_id}")


def milled(game) -> int:
    return len(game.state.players[1].graveyard)


class TestTheBodyAlwaysRunsOnce:
    """A do-while, not a while: the first mill is the trigger's own."""

    def test_it_mills_even_when_the_condition_is_false_at_once(self, builder):
        game = position(builder, [GREEN_BEAR, RED_BOLT])
        cast_and_settle(game, TUTELAGE)
        assert milled(game) == 2, "one pass, and the colours did not match"

    def test_two_lands_still_mill_two(self, builder):
        """The filter empties the pool, so the condition is false — but the body
        has already run."""
        game = position(builder, [PLAINS, PLAINS])
        cast_and_settle(game, TUTELAGE)
        assert milled(game) == 2


class TestItRepeatsWhileTheConditionHolds:
    def test_one_repetition(self, builder):
        """Two greens, then a mismatched pair: two passes, four cards."""
        game = position(builder, [GREEN_BEAR, GREEN_DORK, RED_BOLT, BLUE_FLYER])
        cast_and_settle(game, TUTELAGE)
        assert milled(game) == 4

    def test_two_repetitions(self, builder):
        game = position(
            builder, [GREEN_BEAR, GREEN_DORK, RED_BOLT, RED_BOLT, GREEN_BEAR, BLUE_FLYER]
        )
        cast_and_settle(game, TUTELAGE)
        assert milled(game) == 6

    def test_it_stops_on_the_first_pass_that_does_not_match(self, builder):
        """The boundary: a matching pass followed by a non-matching one."""
        game = position(builder, [GREEN_BEAR, GREEN_DORK, PLAINS, PLAINS, GREEN_BEAR, GREEN_DORK])
        cast_and_settle(game, TUTELAGE)
        assert milled(game) == 4, "the land pair ends it; the greens below are never reached"


class TestTheAccumulatingBindingIsTheTrap:
    """`mill`'s `as` binding accumulates, so a loop without `reset` is a
    different card.

    The board is chosen so the two spellings disagree: pass one mills two greens
    (both agree, repeat), pass two mills a red and a blue. Scoped, the second
    pass sees only those two and stops. Unscoped, it sees all four — including
    the two greens from pass one — and keeps going.
    """

    def test_scoped_stops_after_the_second_pass(self, builder):
        game = position(builder, [GREEN_BEAR, GREEN_DORK, RED_BOLT, BLUE_FLYER], spell=TUTELAGE)
        cast_and_settle(game, TUTELAGE)
        assert milled(game) == 4

    def test_unscoped_keeps_going(self, builder):
        game = position(builder, [GREEN_BEAR, GREEN_DORK, RED_BOLT, BLUE_FLYER], spell=UNSCOPED)
        cast_and_settle(game, UNSCOPED)
        assert milled(game) > 4, (
            "the control: an accumulated binding still holds pass one's two greens"
        )


class TestTheGuard:
    """One pathological board must not hang a game."""

    def test_a_condition_that_never_goes_false_stops_at_a_hundred(self, builder):
        """A library deep enough that the guard, not the deck, is what stops it."""
        game = position(builder, [], spell=FOREVER, pad=200)
        cast_and_settle(game, FOREVER)
        assert milled(game) == 100


class TestTheLoader:
    def spell(self, **extra):
        body = {
            "op": "repeat_while",
            "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
            "condition": {"cmp": ">=", "left": {"const": 0}, "right": {"const": 1}},
        }
        body.update(extra)
        return {
            "id": "t_probe_repeat_while",
            "name": "Probe Repeat While",
            "mana_cost": "{U}",
            "types": ["Sorcery"],
            "spell_effects": [body],
        }

    def test_the_ordinary_shape_compiles(self):
        card = compile_card(CardModel.model_validate(self.spell()))
        assert card.spell_effects[0]["op"] == "repeat_while"

    def test_it_needs_a_condition(self):
        """Without one the loop only ever stops at the guard."""
        spell = self.spell()
        del spell["spell_effects"][0]["condition"]
        with pytest.raises(DslError, match="needs a 'condition'"):
            compile_card(CardModel.model_validate(spell))

    def test_it_needs_a_body(self):
        spell = self.spell()
        spell["spell_effects"][0]["effects"] = []
        with pytest.raises(DslError, match="needs 'effects'"):
            compile_card(CardModel.model_validate(spell))

    def test_reset_must_be_a_list_of_names(self):
        with pytest.raises(DslError, match="binding names"):
            compile_card(CardModel.model_validate(self.spell(reset="milled")))

    def test_reset_is_optional(self):
        card = compile_card(CardModel.model_validate(self.spell(reset=["milled"])))
        assert card.spell_effects[0]["reset"] == ["milled"]
