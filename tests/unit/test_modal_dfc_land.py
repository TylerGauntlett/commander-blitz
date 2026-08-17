"""A modal double-faced card whose other half is a land.

    Malakir Rebirth // Malakir Mire — an Instant on the front, a Land on the
    back, and you choose which as you play it.

`second_face` already gave one card two independently playable halves — that is
adventure, aftermath and split cards, all shipped. Every one of them is **cast**,
and that is the whole of what was missing here: a land is *played*. It uses no
stack, it spends the land drop, and it is offered beside the other land drops
rather than beside the cast lines.

So the land half is enumerated in `_land_actions` with `second_face=True`, and
`_play_land` sets `showing_second_face` before the move.

**Before, not after**, and that is the one ordering that matters:
`move_object` fires the enters-the-battlefield replacements, and they have to be
read off the *land*. Malakir Mire enters tapped; Malakir Rebirth does not enter
at all. Set afterwards, the land would arrive untapped and the printed line would
be silently missing.

Unlike `transformed`, the flag needs no second write: `reset_permanent_state`
deliberately leaves `showing_second_face` alone, so it survives the arrival —
which is also why disturb had to re-apply its face and this does not.

The loader's "a second castable face needs a mana cost of its own" guard is
relaxed for a land, and not as a loophole: a land has no mana cost to write, and
costing nothing is not a discount when it still spends the drop.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card, link_second_faces
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError

FRONT = "t_mdfc_front"  # {B} instant, gain 2 life
LAND = "t_mdfc_land"  # its other half: a tapland that adds {B}


def board(builder, lands_played: int = 0):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"])
        .hand(0, [FRONT])
        .library(0, ["swamp"] * 20)
        .active(0)
        .lands_played(0, lands_played)
        .build()
    )
    return game


def land_lines(game):
    return [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]


def the_card(game) -> int:
    return next(
        o.oid
        for o in game.state.objects.values()
        if o.zone in (Zone.HAND, Zone.BATTLEFIELD) and o.def_id == FRONT
    )


class TestBothHalvesAreOffered:
    def test_the_land_half_is_a_land_drop(self, builder):
        game = board(builder)
        assert any(a.second_face for a in land_lines(game))

    def test_the_front_is_still_castable(self, builder):
        game = board(builder)
        assert any(
            a.kind is ActionKind.CAST and a.source == the_card(game)
            for a in game.legal_actions()
        )

    def test_the_land_half_is_not_offered_after_the_drop(self, builder):
        """It is a land drop, so it competes with every other land."""
        game = board(builder, lands_played=1)
        assert not [a for a in land_lines(game) if a.second_face]

    def test_the_land_line_is_labelled_as_the_land(self, builder):
        game = board(builder)
        line = next(a for a in land_lines(game) if a.second_face)
        assert "MDFC Land" in (line.label or "")


class TestPlayingTheLandHalf:
    def play_the_land(self, game):
        game.apply(next(a for a in land_lines(game) if a.second_face))
        return the_card(game)

    def test_it_arrives_as_the_land(self, builder):
        game = board(builder)
        oid = self.play_the_land(game)
        assert game.state.card_of(game.state.objects[oid]).id == LAND

    def test_it_is_on_the_battlefield(self, builder):
        game = board(builder)
        oid = self.play_the_land(game)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_it_enters_tapped(self, builder):
        """The ordering test: the replacement is the *land's*.

        Set after the move, the flag would arrive too late and this land would
        enter untapped -- the printed line missing with nothing to show for it.
        """
        game = board(builder)
        oid = self.play_the_land(game)
        assert game.state.objects[oid].tapped

    def test_the_land_drop_is_spent(self, builder):
        game = board(builder)
        self.play_the_land(game)
        assert game.state.players[0].lands_played == 1

    def test_nothing_went_on_the_stack(self, builder):
        game = board(builder)
        self.play_the_land(game)
        assert not game.state.stack

    def test_it_stays_the_land_afterwards(self, builder):
        """`reset_permanent_state` must not have cleared the face."""
        game = board(builder)
        oid = self.play_the_land(game)
        game.state.bump_chars()
        assert game.state.card_of(game.state.objects[oid]).is_land


class TestTheLoaderGuard:
    def test_a_free_nonland_second_face_is_still_refused(self):
        cards = {
            c.id: c
            for c in (
                compile_card(
                    CardModel.model_validate(
                        {
                            "id": "t_free_front",
                            "name": "Free Front",
                            "mana_cost": "{B}",
                            "types": ["Instant"],
                            "second_face": "t_free_back",
                            "spell_effects": [{"op": "draw", "player": "you"}],
                        }
                    )
                ),
                compile_card(
                    CardModel.model_validate(
                        {
                            "id": "t_free_back",
                            "name": "Free Back",
                            "types": ["Instant"],
                            "spell_effects": [{"op": "draw", "player": "you"}],
                        }
                    )
                ),
            )
        }
        with pytest.raises(DslError, match="mana cost of its own"):
            link_second_faces(cards)
