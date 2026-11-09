"""A `play_lands_from_graveyard` permission narrowed to a land type.

    Hazezon, Shaper of Sand — "You may play Desert lands from your graveyard."
    Titania, Nature's Force — "You may play Forests from your graveyard."

Rule 305.1 lets a player play a land whenever they have priority in a main
phase of their own turn with an empty stack, and 305.2 holds that to one land a
turn; a permission like Crucible of Worlds' widens only *where* that land may
come from. Hazezon's widens it for Deserts and nothing else. Without a filter
the static could only open the whole graveyard -- a Hazezon that replays every
fetched-away Forest and Mountain, a strictly bigger card than the printed one.

So the filter is read per card (`player_statics.graveyard_land_play_allows`):
a Desert is offered, a land that is not one stays put, and the unfiltered
Crucible is unchanged. Two permissions are two separate grants -- a land either
covers is playable -- and the land drop is still one a turn. The loader refuses
an empty filter, `affects` in its place, and a `controller` key the
`affects_player` already answers.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import static_probe

HAZEZON_LINE = "t_desert_crucible"
CRUCIBLE = "ramunap_excavator"
DESERT = "painted_bluffs"


def position(builder, permissions=(HAZEZON_LINE,), buried=(DESERT, "forest"), *, played=0):
    """``(game, buried_oids)``: seat 0 in its main phase, lands in the graveyard."""
    game = (
        builder(players=2)
        .battlefield(0, list(permissions))
        .graveyard(0, list(buried))
        .library(0, ["plains"] * 10)
        .lands_played(0, played)
        .build()
    )
    return game, list(game.state.players[0].graveyard)


def playable_from_graveyard(game) -> list[str]:
    state = game.state
    return sorted(
        state.card(a.source).id
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND and state.objects[a.source].zone is Zone.GRAVEYARD
    )


class TestTheLandType:
    def test_only_the_desert_is_offered(self, builder):
        game, _ = position(builder)
        assert playable_from_graveyard(game) == [DESERT]

    def test_a_graveyard_with_no_desert_offers_nothing(self, builder):
        game, _ = position(builder, buried=("forest", "mountain"))
        assert playable_from_graveyard(game) == []

    def test_playing_the_desert_moves_it_to_the_battlefield(self, builder):
        game, _ = position(builder)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND and game.state.card(a.source).id == DESERT
        )
        game.apply(action)
        assert game.state.objects[action.source].zone is Zone.BATTLEFIELD


class TestTheUnfilteredFormIsUnchanged:
    def test_crucible_still_frees_every_land(self, builder):
        game, _ = position(builder, permissions=(CRUCIBLE,))
        assert playable_from_graveyard(game) == sorted([DESERT, "forest"])

    def test_beside_crucible_the_filter_narrows_nothing(self, builder):
        """Two permissions, two grants: a land either one covers is playable."""
        game, _ = position(builder, permissions=(HAZEZON_LINE, CRUCIBLE))
        assert playable_from_graveyard(game) == sorted([DESERT, "forest"])


class TestStillOneLandDrop:
    def test_no_desert_once_the_land_drop_is_spent(self, builder):
        game, _ = position(builder, played=1)
        assert playable_from_graveyard(game) == []

    def test_without_the_permission_nothing_leaves_the_graveyard(self, builder):
        game, _ = position(builder, permissions=())
        assert playable_from_graveyard(game) == []


class TestTheLoaderRefuses:
    def _static(self, **extra):
        return CardModel.model_validate(
            static_probe({"effect": "play_lands_from_graveyard", "affects_player": "you", **extra})
        )

    def test_the_bare_permission_loads(self):
        compile_card(self._static(), source="test")

    def test_an_empty_filter(self):
        with pytest.raises(DslError, match="empty filter"):
            compile_card(self._static(affects_spells={}), source="test")

    def test_affects_in_place_of_affects_spells(self):
        with pytest.raises(DslError, match="not 'affects'"):
            compile_card(self._static(affects={"subtypes": ["Desert"]}), source="test")

    def test_a_controller_key(self):
        with pytest.raises(DslError, match="controller"):
            compile_card(
                self._static(affects_spells={"controller": "you", "types": ["Land"]}),
                source="test",
            )
