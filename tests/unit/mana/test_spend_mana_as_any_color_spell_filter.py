"""Oath of Nissa: any-colour mana, but only to cast planeswalker spells.

    You may spend mana as though it were mana of any color to cast
    planeswalker spells.

Chromatic Orrery's `spend_mana_as_any_color` static, narrowed by an
`affects_spells` filter. The rules argument is the narrowing itself: written
unfiltered, the Oath is an Orrery -- every spell and every activated ability
loosened -- which is a strictly stronger card. So the claims are that a
matching spell's coloured pips are payable off any land, that a non-matching
spell's are not, that no activated ability is loosened (activating is not
casting, even a planeswalker's own), that the unfiltered Orrery is untouched,
and that the loader keeps the filter to the keys a spell being cast has.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError

OATH = "t_oath_static"
WALKER = "t_azure_walker"  # {1}{U} planeswalker
BOLT = "t_azure_bolt"  # {1}{U} sorcery
FONT = "t_chroma_font"  # {W}{W}: gain 1 life
ORRERY = "t_orrery_static"


def board(builder, *, hand=(), lands=(), permanents=(), oath=True, oath_seat=0):
    b = (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, list(lands) + list(permanents))
        .library(0, ["forest"] * 10)
    )
    if oath:
        b = b.battlefield(oath_seat, [OATH])
    return b.build()


def casts(game, card_id):
    oids = {o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id}
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source in oids]


def activations(game, card_id):
    oids = {o.oid for o in game.state.battlefield_objects(0) if o.def_id == card_id}
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source in oids]


class TestAPlaneswalkerSpell:
    def test_is_castable_off_colour(self, builder):
        game = board(builder, hand=[WALKER], lands=["mountain"] * 2)
        assert casts(game, WALKER)

    def test_and_resolves_paid_with_off_colour_lands(self, builder):
        game = board(builder, hand=[WALKER], lands=["mountain"] * 2)
        game.apply(casts(game, WALKER)[0])
        assert sum(1 for o in game.state.battlefield_objects(0) if o.tapped) == 2

    def test_is_not_without_the_oath(self, builder):
        game = board(builder, hand=[WALKER], lands=["mountain"] * 2, oath=False)
        assert casts(game, WALKER) == []

    def test_an_opponents_oath_does_nothing_for_you(self, builder):
        game = board(builder, hand=[WALKER], lands=["mountain"] * 2, oath_seat=1)
        assert casts(game, WALKER) == []

    def test_the_amount_owed_does_not_move(self, builder):
        game = board(builder, hand=[WALKER], lands=["mountain"])
        assert casts(game, WALKER) == []


class TestWhatItDoesNotReach:
    def test_a_non_planeswalker_spell(self, builder):
        """The whole of the filter: an unfiltered static would cast this."""
        game = board(builder, hand=[BOLT], lands=["mountain"] * 2)
        assert casts(game, BOLT) == []

    def test_an_activated_ability(self, builder):
        game = board(builder, lands=["mountain"] * 2, permanents=[FONT])
        assert activations(game, FONT) == []

    def test_the_orrery_still_reaches_both(self, builder):
        game = board(
            builder, hand=[BOLT], lands=["mountain"] * 2, permanents=[FONT, ORRERY], oath=False
        )
        assert casts(game, BOLT)
        assert activations(game, FONT)


class TestTheLoader:
    def card(self, **static):
        return {
            "id": "t_bad_oath",
            "name": "Test Bad Oath",
            "oracle_text": "You may spend mana as though it were mana of any color.",
            "mana_cost": "{0}",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "You may spend mana as though it were mana of any color.",
                    "effect": "spend_mana_as_any_color",
                    "affects_player": "you",
                    **static,
                }
            ],
        }

    def test_the_filter_loads(self):
        compile_card(CardModel.model_validate(self.card(affects_spells={"types": ["Planeswalker"]})))

    def test_a_controller_key_is_refused(self):
        card = self.card(affects_spells={"controller": "you"})
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(CardModel.model_validate(card))

    def test_an_empty_filter_is_refused(self):
        with pytest.raises(DslError, match="empty filter"):
            compile_card(CardModel.model_validate(self.card(affects_spells={})))

    def test_affects_is_still_refused(self):
        with pytest.raises(DslError, match="no 'affects'"):
            compile_card(CardModel.model_validate(self.card(affects={"types": ["Creature"]})))
