""""If two nonland cards that **share a color** were milled this way."

Sphinx's Tutelage. A relation **between two members of a pool**, and the only
condition in the language that is not a property of one object — which is exactly
why none of the existing colour readers could say it:

- `colors` and `not_colors` test a pool member against a colour fixed when the
  card is written. Sphinx's Tutelage names no colour; it asks whether two cards
  agree on one, whichever it is.
- `min_colors` counts the colours on a *single* card, so it answers "was a
  multicolored card milled".
- `shares_a_color_with` is the near-namesake and resolves its argument through
  `_bound_oid`, which reads one oid and returns ``None`` for a list. A `mill`'s
  `as` binding is always a list, so the clause pointed here matches nothing at
  all — a card that loads, prints the sentence and never fires.
- `distinct` is restricted to power and basic land type, so it cannot count
  colours either.

`exists` with a count is the tempting substitute and drops the colour clause
entirely: "two nonland cards were milled" is true on almost every mill.
`TestTheCountingSpellingLeaks` keeps that card alive and measures the difference
on the one board where the two disagree.

**Colourless cards share no colour with anything.** That falls out of the
intersection being empty rather than being special-cased, and it is the printed
ruling: two artifacts do not continue the process.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError

MILLER = "t_color_miller"  # the colour clause
COUNTER = "t_any_two_miller"  # the near miss: two nonland cards, any colours

GREEN_BEAR = "t_bear"  # G creature
GREEN_DORK = "t_dork"  # G creature
RED_BOLT = "t_bolt"  # R instant
BLUE_FLYER = "t_flyer"  # U creature
ROCK = "t_colorless_rock"  # colourless artifact
FOREST = "forest"  # a land, which the filter excludes


def position(builder, top_two: list[str], spell: str = MILLER):
    """Player 1's library is stacked so the mill is deterministic.

    The two cards named are what the mill will take, in that order, and nothing
    else about the board can reach the life total the assertions read.
    """
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 3)
        .hand(0, [spell])
        .library(0, ["plains"] * 10)
        .library(1, [*top_two, *["plains"] * 10])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )


def cast_and_settle(game, card_id: str, limit: int = 60) -> None:
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


def cast_and_report(game, card_id: str) -> bool:
    """Cast the miller and say whether the conditional half ran.

    Life against its own starting value rather than a literal: this format deals
    40, and a test written against 20 passes every assertion it makes and proves
    none of them.
    """
    before = game.state.players[0].life
    cast_and_settle(game, card_id)
    return game.state.players[0].life > before


class TestTwoCardsThatShareAColour:
    def test_two_green_creatures_share(self, builder):
        game = position(builder, [GREEN_BEAR, GREEN_DORK])
        assert cast_and_report(game, MILLER)

    def test_a_green_and_a_red_do_not(self, builder):
        game = position(builder, [GREEN_BEAR, RED_BOLT])
        assert not cast_and_report(game, MILLER), "different colours are not a shared colour"

    def test_a_green_and_a_blue_do_not(self, builder):
        game = position(builder, [GREEN_BEAR, BLUE_FLYER])
        assert not cast_and_report(game, MILLER)


class TestColourlessSharesNothing:
    """The empty intersection, which is the printed ruling and not a special case."""

    def test_two_colourless_cards_do_not_share(self, builder):
        game = position(builder, [ROCK, ROCK])
        assert not cast_and_report(game, MILLER), "two artifacts do not continue the process"

    def test_a_colourless_card_and_a_green_one_do_not(self, builder):
        game = position(builder, [ROCK, GREEN_BEAR])
        assert not cast_and_report(game, MILLER)


class TestTheFilterIsApplied:
    """"two **nonland** cards" -- the lands are excluded before the pairing."""

    def test_two_lands_are_not_a_pair(self, builder):
        game = position(builder, [FOREST, FOREST])
        assert not cast_and_report(game, MILLER)

    def test_a_land_and_a_creature_are_not_a_pair(self, builder):
        """One nonland card cannot share a colour with anything: there is no
        second member of the pool once the filter has run."""
        game = position(builder, [FOREST, GREEN_BEAR])
        assert not cast_and_report(game, MILLER)


class TestTheCountingSpellingLeaks:
    """Kept as a live card: `exists`/`count` drops the colour clause.

    The board where the two spellings disagree is the one that matters most,
    because it is the ordinary case — two nonland cards of different colours.
    """

    def test_it_fires_on_two_cards_of_different_colours(self, builder):
        game = position(builder, [GREEN_BEAR, RED_BOLT], spell=COUNTER)
        assert cast_and_report(game, COUNTER), "the control: counting sees two cards and no colours"

    def test_where_the_colour_clause_does_not(self, builder):
        game = position(builder, [GREEN_BEAR, RED_BOLT], spell=MILLER)
        assert not cast_and_report(game, MILLER)


class TestTheLoader:
    def spell(self, condition):
        return {
            "id": "t_probe_share",
            "name": "Probe Share",
            "mana_cost": "{U}",
            "types": ["Sorcery"],
            "spell_effects": [
                {
                    "op": "if",
                    "condition": condition,
                    "then": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_a_pool_is_accepted(self):
        card = compile_card(
            CardModel.model_validate(
                self.spell({"two_share_a_color": {"binding": "milled", "not_types": ["Land"]}})
            )
        )
        assert card.spell_effects[0]["condition"]["two_share_a_color"]["binding"] == "milled"

    def test_a_bare_true_is_refused(self):
        """A card that loads, prints the sentence and asks about nothing."""
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(self.spell({"two_share_a_color": True})))

    def test_an_unknown_selector_key_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.spell({"two_share_a_color": {"binding": "milled", "nonsense": 1}})
                )
            )
