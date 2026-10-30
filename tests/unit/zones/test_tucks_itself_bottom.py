""""Put <this card> on the bottom of its owner's library." -- `tucks_itself: "bottom"`

    Ultimate Nullification -- "As an additional cost to cast this spell,
    sacrifice a legendary creature. Exile all creatures and graveyards.
    **Put Ultimate Nullification on the bottom of its owner's library.**"

The bottom form of the `tucks_itself` rider on the destination
`stack._place_after_resolution` picks. Approach of the Second Sun's ordinal
counts from the top, and no number names the bottom of a library whose size
varies, so the rider also takes the word `"bottom"`. Like every rider on that
slot it replaces only the *graveyard* (608.2n puts a resolved instant or
sorcery there unless the card says otherwise).

**It could not be a `put_on_top` op with `bottom: true`.** A resolving spell has
already been popped off `state.stack` by the time its effects run, and
`_place_after_resolution` then moves it to the graveyard unconditionally, so the
printed line would load cleanly and leave the card recurrable from a graveyard.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card

BOTTOM = "t_tucks_itself_bottom"  # sorcery: gain 2 life. Put it on the bottom of its owner's library.
SEVENTH = "t_approach_tuck_only"  # the ordinal form, for the contrast
LIBRARY = ["forest"] * 20


def board(builder, card_id: str, library=LIBRARY):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 8)
        .hand(0, [card_id])
        .library(0, list(library))
        .library(1, ["forest"] * 20)
        .active(0)
        .build()
    )


def cast_and_settle(game, card_id: str) -> int:
    action = action_for_card(game, ActionKind.CAST, card_id)
    oid = action.source
    game.apply(action)
    for _ in range(100):
        decision = game.pending()
        if decision is None or not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    assert oid is not None
    return oid


class TestWhereItGoes:
    def test_it_ends_in_its_owners_library(self, builder):
        game = board(builder, BOTTOM)
        oid = cast_and_settle(game, BOTTOM)
        assert game.state.objects[oid].zone is Zone.LIBRARY
        assert oid not in game.state.players[0].graveyard

    def test_it_is_the_bottom_card(self, builder):
        game = board(builder, BOTTOM)
        oid = cast_and_settle(game, BOTTOM)
        library = game.state.players[0].library
        assert library[-1] == oid
        assert len(library) == len(LIBRARY) + 1

    def test_it_is_the_bottom_card_of_an_empty_library_too(self, builder):
        """The boundary: no depth to clamp, and still the bottom (and the top)."""
        game = board(builder, BOTTOM, library=[])
        oid = cast_and_settle(game, BOTTOM)
        assert game.state.players[0].library == [oid]

    def test_it_still_did_what_it_said(self, builder):
        game = board(builder, BOTTOM)
        life = game.state.players[0].life
        cast_and_settle(game, BOTTOM)
        assert game.state.players[0].life == life + 2

    def test_the_ordinal_form_still_counts_from_the_top(self, builder):
        """The near miss: seventh from the top is not the bottom of twenty."""
        game = board(builder, SEVENTH)
        oid = cast_and_settle(game, SEVENTH)
        library = game.state.players[0].library
        assert library.index(oid) == 6
        assert library[-1] != oid


class TestTheLoaderRefusesNonsense:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "t_bad_tucks_itself",
                "name": "Bad Tucks Itself",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "colors": ["W"],
                "color_identity": ["W"],
                "types": ["Sorcery"],
                "spell_effects": [{"op": "gain_life", "amount": {"const": 1}}],
                **extra,
            }
        )

    def test_bottom_loads(self):
        assert compile_card(self._card(tucks_itself="bottom")).tucks_itself == "bottom"

    def test_another_word_is_refused(self):
        with pytest.raises(Exception, match="tucks_itself"):
            compile_card(self._card(tucks_itself="top"))

    def test_a_depth_below_one_is_refused(self):
        """The ordinal counts from 1; zero would silently be the top."""
        with pytest.raises(DslError, match="tucks_itself"):
            compile_card(self._card(tucks_itself=0))

    def test_a_permanent_carrying_it_is_refused(self):
        """It replaces the graveyard, and a permanent never reaches the rider."""
        with pytest.raises(DslError, match="tucks_itself"):
            compile_card(
                self._card(
                    types=["Creature"], power=1, toughness=1, spell_effects=[],
                    tucks_itself="bottom",
                )
            )
