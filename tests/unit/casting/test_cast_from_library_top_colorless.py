"""Mystic Forge — artifact spells *and* colorless spells off the top of the library.

    You may cast artifact spells and colorless spells from the top of your
    library.

Thundermane Dragon's permission with a different filter, and the filter is the
whole card. "Artifact spells and colorless spells" is a **union** of two printed
shapes: a red artifact creature is an artifact spell, a colorless Eldrazi is a
colorless spell, and both come off the top. Every other filter key is ANDed, so
the two shapes written as one filter would be "colorless artifact" and drop both
halves' edges; written as an artifact filter alone the card would miss every
colorless nonartifact spell (Kozilek's Return), which is the reason the second
half is printed. `any_of` says the union, and `colorless` says the second half:
zero colours, 105.2c, which `colors` (a membership test) and `min_colors` (a
floor) cannot.

A branch is matched against the printed face, so it takes no `power` or
`toughness` -- the reader measures those on the object at the top level only,
and a size in a branch would load and be ignored, a wider permission than the
printed one. The loader refuses it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import settle

FORGE = "t_forge"
RED_ARTIFACT = "t_mf_red_construct"  # {1}{R} red artifact creature
ELDRAZI = "t_mf_eldrazi"  # {3} colorless creature
TRINKET = "t_mf_trinket"  # {2} colorless artifact
GREEN_BEAR = "t_mf_green_bear"  # {1}{G} green creature


def board(builder, *, top: str, permanents=(FORGE,)):
    return (
        builder(players=2)
        .battlefield(0, ["mountain", "forest", "forest", "forest", *permanents])
        .hand(0, ["plains"])
        .life(0, 40)
        .library(0, [top] + ["forest"] * 10)
        .build()
    )


def top_lines(game):
    top = game.state.players[0].library[0]
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == top]


class TestTheUnion:
    def test_a_colored_artifact_is_an_artifact_spell(self, builder):
        assert top_lines(board(builder, top=RED_ARTIFACT))

    def test_a_colorless_nonartifact_is_a_colorless_spell(self, builder):
        assert top_lines(board(builder, top=ELDRAZI))

    def test_a_colorless_artifact_is_both(self, builder):
        assert top_lines(board(builder, top=TRINKET))

    def test_a_colored_nonartifact_is_neither(self, builder):
        assert top_lines(board(builder, top=GREEN_BEAR)) == []

    def test_without_the_permanent_nothing_is(self, builder):
        assert top_lines(board(builder, top=ELDRAZI, permanents=())) == []


class TestThePrintedPrice:
    def test_the_eldrazi_costs_its_mana_and_no_life(self, builder):
        game = board(builder, top=ELDRAZI)
        oid = game.state.players[0].library[0]
        game.apply(top_lines(game)[0])
        settle(game)
        assert game.state.objects[oid].on_battlefield
        assert game.state.players[0].life == 40
        assert all(not a.from_library_top for a in game.legal_actions())

    def test_the_next_card_down_is_judged_as_it_surfaces(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["mountain", "forest", "forest", "forest", "forest", FORGE])
            .library(0, [TRINKET, GREEN_BEAR] + ["forest"] * 10)
            .build()
        )
        game.apply(top_lines(game)[0])
        settle(game)
        assert top_lines(game) == []


def _permission(affects_spells):
    text = "You may cast artifact spells and colorless spells from the top of your library."
    return CardModel.model_validate(
        {
            "id": "t_probe_forge",
            "name": "Test Probe Forge",
            "oracle_text": text,
            "mana_cost": "{4}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "static",
                    "text": text,
                    "effect": "cast_from_library_top",
                    "affects_player": "you",
                    "affects_spells": affects_spells,
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_union_loads(self):
        filt = {"any_of": [{"types": ["Artifact"]}, {"colorless": True}]}
        card = compile_card(_permission(filt), source="test")
        assert card.abilities[0].static["affects_spells"] == filt

    def test_colorless_alone_loads(self):
        card = compile_card(_permission({"colorless": True}), source="test")
        assert card.abilities[0].static["affects_spells"] == {"colorless": True}

    def test_colorless_false_is_refused(self):
        with pytest.raises(DslError, match="colorless"):
            compile_card(_permission({"colorless": False}), source="test")

    def test_a_one_branch_union_is_refused(self):
        with pytest.raises(DslError, match="at least two"):
            compile_card(_permission({"any_of": [{"types": ["Artifact"]}]}), source="test")

    def test_a_size_inside_a_branch_is_refused(self):
        filt = {
            "any_of": [
                {"types": ["Artifact"]},
                {"types": ["Creature"], "power": {"op": ">=", "value": 4}},
            ]
        }
        with pytest.raises(DslError, match="power"):
            compile_card(_permission(filt), source="test")

    def test_a_chosen_color_inside_a_branch_is_refused(self):
        filt = {"any_of": [{"types": ["Artifact"]}, {"colors": [{"chosen_color_of": "self"}]}]}
        with pytest.raises(DslError, match="chosen"):
            compile_card(_permission(filt), source="test")

    def test_colorless_false_inside_a_branch_is_refused(self):
        filt = {"any_of": [{"types": ["Artifact"]}, {"colorless": False}]}
        with pytest.raises(DslError, match="colorless"):
            compile_card(_permission(filt), source="test")
