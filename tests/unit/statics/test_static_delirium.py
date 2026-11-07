"""Delirium as a static's condition: the card types among cards in a graveyard.

    "Delirium -- Grim Flayer gets +2/+2 as long as there are four or more card
    types among cards in your graveyard."           -- Grim Flayer

An "as long as" clause is a static's condition (611.3a), re-read whenever the
board changes, so a trigger that checks once cannot say it. The effect side's
`distinct` already counted card types; the static value language now admits it,
held to ``of: "card_type"`` over a counting filter off the battlefield. A card in
a graveyard has its printed face and no continuous effects (it is not a
permanent), so its types are a pipeline input and the static cannot come to
depend on another static's output -- which is why the other ``of`` words, and a
battlefield pool, stay refused. Types, not cards: two creature cards are one
type, and one artifact creature card is two.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.statics import _validate_static_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pt

GROWER = "t_sdl_grower"  # 2/2, +2/+2 with four or more card types in your graveyard
CREATURE = "t_sdl_creature"
LAND = "t_sdl_land"
SORCERY = "t_sdl_sorcery"
INSTANT = "t_sdl_instant"
CONSTRUCT = "t_sdl_artifact_creature"  # Artifact and Creature on one card
ENCHANTMENT = "t_sdl_enchantment"


def board(builder, yard=(), their_yard=(), hand=()):
    return (
        builder(players=2)
        .battlefield(0, [GROWER])
        .graveyard(0, list(yard))
        .hand(0, list(hand))
        .graveyard(1, list(their_yard))
        .build(advance=False)
    )


def in_zone(game, card_id: str, zone: Zone) -> int:
    (oid,) = [
        oid
        for oid in game.state.players[0].zone_list(zone)
        if game.state.objects[oid].def_id == card_id
    ]
    return oid


def grower(game) -> tuple[int, int]:
    return pt(game, only_oid(game, GROWER))


class TestTheCount:
    def test_an_empty_graveyard_is_off(self, builder):
        assert grower(board(builder)) == (2, 2)

    def test_three_types_is_off(self, builder):
        game = board(builder, yard=[CREATURE, LAND, SORCERY])
        assert grower(game) == (2, 2)

    def test_four_types_is_on(self, builder):
        game = board(builder, yard=[CREATURE, LAND, SORCERY, INSTANT])
        assert grower(game) == (4, 4)

    def test_cards_sharing_a_type_count_it_once(self, builder):
        game = board(builder, yard=[CREATURE, CREATURE, CREATURE, LAND, SORCERY])
        assert grower(game) == (2, 2)

    def test_one_card_with_two_types_counts_both(self, builder):
        """Artifact Creature, Land and Sorcery: four types from three cards."""
        game = board(builder, yard=[CONSTRUCT, LAND, SORCERY])
        assert grower(game) == (4, 4)

    def test_an_opponents_graveyard_is_not_yours(self, builder):
        game = board(builder, yard=[CREATURE, LAND], their_yard=[SORCERY, INSTANT, ENCHANTMENT])
        assert grower(game) == (2, 2)


class TestItTracksTheGraveyard:
    def test_a_card_arriving_turns_it_on(self, builder):
        game = board(builder, yard=[CREATURE, LAND, SORCERY], hand=[INSTANT])
        assert grower(game) == (2, 2)
        move_object(game.state, in_zone(game, INSTANT, Zone.HAND), Zone.GRAVEYARD)
        assert grower(game) == (4, 4)

    def test_a_card_leaving_turns_it_off(self, builder):
        game = board(builder, yard=[CREATURE, LAND, SORCERY, INSTANT])
        move_object(game.state, in_zone(game, INSTANT, Zone.GRAVEYARD), Zone.EXILE)
        assert grower(game) == (2, 2)


class TestTheLoader:
    GOOD = {"of": "card_type", "objects": {"zone": "graveyard", "controller": "you"}}

    def test_the_printed_shape_loads(self):
        _validate_static_value({"distinct": self.GOOD}, "test")

    @pytest.mark.parametrize("of", ["power", "color", "basic_land_type", "name", "counter_kind"])
    def test_a_layer_output_is_refused(self, of):
        with pytest.raises(DslError, match="can only read 'card_type'"):
            _validate_static_value({"distinct": {**self.GOOD, "of": of}}, "test")

    def test_the_battlefield_is_refused(self):
        """A permanent's types are a layer's output ("it's an artifact in addition")."""
        spec = {"of": "card_type", "objects": {"controller": "you"}}
        with pytest.raises(DslError, match="layer's output"):
            _validate_static_value({"distinct": spec}, "test")

    def test_objects_are_required(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            _validate_static_value({"distinct": {"of": "card_type"}}, "test")

    def test_an_unknown_key_is_refused(self):
        spec = {**self.GOOD, "spells_cast_this_turn": "you"}
        with pytest.raises(DslError, match="unsupported keys"):
            _validate_static_value({"distinct": spec}, "test")

    def test_the_filter_is_held_to_the_static_zone_filter(self):
        spec = {"of": "card_type", "objects": {"zone": "graveyard", "controller": "you", "tapped": True}}
        with pytest.raises(DslError):
            _validate_static_value({"distinct": spec}, "test")
