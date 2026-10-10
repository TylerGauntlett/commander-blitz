"""Milling twice as many cards instead.

    Bruvac the Grandiloquent — "If an opponent would mill one or more cards,
    they mill twice that many cards instead."
    Fraying Sanity — the same sentence said of one player.

`static_effects` carried the whole `replace_*` family — `replace_draw`,
`replace_life_gain`, `replace_life_loss`, `replace_token_creation` — and no mill
member. `mill` existed only as an effect op and as a cost, which is to say only
as something *this card's controller does*, never as an event that could be
replaced.

Two things decide the design, and both come from the rules rather than from
convenience:

- **701.13a makes milling N cards one event**, where 121.2 makes drawing N cards
  N separate draws. So this multiplies a count once, in place, and needs none of
  the per-card recursion (and none of the 614.5 "applies once" bookkeeping) that
  `replacements._draw_one` is built out of.
- **It belongs in `primitives.mill_cards`**, the single choke point every mill
  goes through: the `mill` op, the `mill` cost, and dredge (702.52a). That is
  what makes Bruvac double the mills an *opponent's own* cards cause, which is
  the entire card — a doubling written into the op would only ever see mills its
  own controller caused, and Bruvac's controller is not the one being milled.

A `mill` trigger cannot substitute: there is no such trigger event, and one
would fire after the cards were already in the graveyard and mill again
*alongside* rather than *instead* — which is a different card the moment
anything cares how many cards were milled at once, or the library runs short.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import mill_multiplier
from commanderblitz.engine.primitives import mill_cards

DOUBLER = "t_bruvac_doubler"  # opponents mill twice as many
SELF_DOUBLER = "t_self_mill_doubler"  # you mill twice as many
BEAR = "t_bear"


def _model(**over):
    ability = {
        "kind": "static",
        "text": "If an opponent would mill one or more cards, they mill twice that many cards instead.",
        "effect": "replace_mill",
        "affects_player": "opponent",
        "mill_multiplier": 2,
    }
    ability.update(over.pop("ability", {}))
    base = {
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": ability["text"],
        "mana_cost": "{1}{U}",
        "types": ["Enchantment"],
        "abilities": [ability],
    }
    base.update(over)
    return CardModel.model_validate(base)


class TestTheMillIsDoubled:
    def test_an_opponent_mills_twice_as_many(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island", DOUBLER])
            .library(1, ["forest"] * 20)
            .build()
        )
        before = len(game.state.players[1].library)
        milled = mill_cards(game.state, 1, 3)
        assert len(milled) == 6, "the doubler did not replace the mill"
        assert len(game.state.players[1].library) == before - 6

    def test_without_the_doubler_it_is_the_printed_number(self, builder):
        """The pair, and the one that makes the test above mean anything."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"])
            .library(1, ["forest"] * 20)
            .build()
        )
        assert len(mill_cards(game.state, 1, 3)) == 3

    def test_the_controller_is_not_doubled(self, builder):
        """"If an **opponent** would mill" -- Bruvac's own mills are untouched.

        The near miss, and the one a player-agnostic implementation passes
        silently: a doubler that ignored `affects_player` would read identically
        on the opponent and be wrong here.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["island", DOUBLER])
            .library(0, ["forest"] * 20)
            .build()
        )
        assert len(mill_cards(game.state, 0, 3)) == 3

    def test_affects_player_you_doubles_its_own_controller(self, builder):
        """Fraying Sanity's half of the same static."""
        game = (
            builder(players=2)
            .battlefield(0, ["island", SELF_DOUBLER])
            .library(0, ["forest"] * 20)
            .build()
        )
        assert len(mill_cards(game.state, 0, 3)) == 6


class TestCompounding:
    def test_two_doublers_quadruple(self, builder):
        """616.1: two different replacements each apply, and they compound.

        Each source is visited once, so none applies twice (614.5) -- the
        guarantee `draw_replacements` needs an `applied` set to get, this shape
        gets from multiplying a count rather than recursing.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 2 + [DOUBLER, DOUBLER])
            .library(1, ["forest"] * 40)
            .build()
        )
        assert mill_multiplier(game.state, 1) == 4
        assert len(mill_cards(game.state, 1, 2)) == 8


class TestTheBoundaries:
    def test_milling_nothing_is_not_an_event(self, builder):
        """"If an opponent would mill **one or more** cards."

        A mill of zero is no event, so there is nothing to replace -- and the
        assertion matters because `0 * 2` is also 0: what is being pinned is
        that the printed condition is read, not that the arithmetic happens to
        agree.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["island", DOUBLER])
            .library(1, ["forest"] * 20)
            .build()
        )
        before = len(game.state.players[1].library)
        assert mill_cards(game.state, 1, 0) == []
        assert len(game.state.players[1].library) == before

    def test_a_short_library_mills_what_is_there(self, builder):
        """701.13b: milling fewer than asked is not an error.

        The doubled count is still only a request -- this is the case the whole
        deck is trying to reach, so it must not raise or over-count.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["island", DOUBLER])
            .library(1, ["forest"] * 5)
            .build()
        )
        milled = mill_cards(game.state, 1, 4)
        assert len(milled) == 5, "should have emptied the 5-card library, not milled 8"
        assert game.state.players[1].library == []

    def test_the_hold_ends_when_the_source_leaves(self, builder):
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.zones import move_object
        from tests.conftest import only_oid

        game = (
            builder(players=2)
            .battlefield(0, ["island", DOUBLER])
            .library(1, ["forest"] * 20)
            .build()
        )
        assert mill_multiplier(game.state, 1) == 2
        move_object(game.state, only_oid(game, DOUBLER), Zone.GRAVEYARD)
        assert mill_multiplier(game.state, 1) == 1


class TestLoadTimeGuards:
    def test_a_multiplier_is_required(self):
        with pytest.raises(DslError, match="needs 'mill_multiplier'"):
            compile_card(_model(ability={"mill_multiplier": None}))

    @pytest.mark.parametrize("value", [0, 1])
    def test_below_two_is_refused(self, value):
        """1 replaces a mill with itself; 0 is a prevention no doubler prints."""
        with pytest.raises(DslError, match="must be 2 or more"):
            compile_card(_model(ability={"mill_multiplier": value}))

    def test_the_key_is_refused_on_another_static(self):
        """A key nothing reads would load clean and print a line that lies."""
        with pytest.raises(DslError, match="only means anything on a replace_mill"):
            compile_card(
                _model(
                    ability={
                        "effect": "no_hand_limit",
                        "text": "Players have no maximum hand size.",
                        "affects_player": "any",
                        "mill_multiplier": 2,
                    }
                )
            )

    def test_affects_player_is_required(self):
        with pytest.raises(DslError, match="needs 'affects_player'"):
            compile_card(_model(ability={"affects_player": None}))

    def test_the_ordinary_card_loads(self):
        card = compile_card(_model())
        assert card.abilities[0].static["mill_multiplier"] == 2
