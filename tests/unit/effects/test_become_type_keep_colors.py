"""Becoming exactly a type, and keeping the colours -- 205.1a, 613.1d.

Vraska, Betrayal's Sting is the witness: "-2: Target creature becomes a
Treasure artifact with \"{T}, Sacrifice this artifact: Add one mana of any
color\" and loses all other card types and abilities." No duration, so it is
indefinite (611.2a); no colour named, so the colour is unchanged (the card's
rulings); no size named, and none is needed on a non-creature.

What would be wrong without `keep_colors`: an exact `animate` replaces the
colours with ``colors``, so the Treasure went colourless and stopped answering
"target green permanent". And without the size-less form an author had to
invent a power and toughness the card never prints, which a later effect that
made it a creature again would expose.

The supertypes stay too (205.4): a legendary creature becomes a legendary
Treasure, and the legend rule still reads it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import animate
from tests.conftest import activations, only_oid, pass_until, settle

VRASKA = "t_treasure_vraska"
DRAKE = "t_legend_drake"  # legendary green Artifact Creature -- Drake, flying, an activated pump


def position(builder):
    """Vraska for player 0, the Drake for player 1; returns ``(game, vraska, drake)``."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 2 + [VRASKA])
        .battlefield(1, ["forest"] * 2 + [DRAKE])
        .hand(0, ["t_bear"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, VRASKA, 0), only_oid(game, DRAKE, 1)


def treasure(builder):
    game, vraska, drake = position(builder)
    action = next(
        a for a in activations(game, vraska) if any(t.id == drake for t in a.targets)
    )
    game.apply(action)
    settle(game)
    return game, drake


class TestWhatItBecomes:
    def test_exactly_a_treasure_artifact(self, builder):
        game, drake = treasure(builder)
        c = chars(game.state, drake)
        assert c.types == frozenset({"Artifact"})
        assert c.subtypes == frozenset({"Treasure"}), "the creature type goes with Creature"

    def test_it_keeps_its_colour(self, builder):
        game, drake = treasure(builder)
        assert chars(game.state, drake).colors == frozenset({"G"})

    def test_it_keeps_its_supertypes(self, builder):
        game, drake = treasure(builder)
        assert chars(game.state, drake).supertypes == frozenset({"Legendary"})

    def test_it_loses_its_abilities_but_not_the_treasures(self, builder):
        game, drake = treasure(builder)
        assert "flying" not in chars(game.state, drake).keywords
        texts = [
            a.label for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == drake
        ]
        assert not any("+1/+0" in (t or "") for t in texts)

    def test_its_controller_is_unchanged(self, builder):
        game, drake = treasure(builder)
        assert game.state.objects[drake].controller == 1


class TestTheTreasure:
    def test_its_controller_can_sacrifice_it_for_mana_of_any_colour(self, builder):
        game, drake = treasure(builder)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step is Step.PRECOMBAT_MAIN)
        offers = activations(game, drake)
        assert {a.option_label for a in offers} >= {"{W}", "{U}", "{B}", "{R}", "{G}"}
        game.apply(offers[0])
        assert drake not in game.state.battlefield
        assert sum(game.state.players[1].mana_pool.amounts) == 1


class TestItLasts:
    def test_it_is_still_a_treasure_next_turn(self, builder):
        game, drake = treasure(builder)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        c = chars(game.state, drake)
        assert c.types == frozenset({"Artifact"})
        assert c.colors == frozenset({"G"})


class TestTheSizeIsLeftAlone:
    def test_a_sizeless_animation_keeps_the_base_size(self, builder):
        """A later creature-making effect that names no size reads the printed one."""
        game, drake = treasure(builder)
        animate(game.state, drake, 0, 0, types=["Creature"], keep_pt=True)
        c = chars(game.state, drake)
        assert "Creature" in c.types
        assert (c.power, c.toughness) == (2, 2)

    def test_an_exact_animation_without_keep_colors_still_replaces(self, builder):
        """Oko's form is untouched: no ``colors`` there means colourless."""
        game, _, drake = position(builder)
        animate(game.state, drake, 3, 3, types=["Creature"], subtypes=["Elk"], exact=True)
        assert chars(game.state, drake).colors == frozenset()


def _probe(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "Target creature becomes something.",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "targets": [{"id": "t1", "kind": "permanent", "count": 1,
                         "selector": {"types": ["Creature"], "zone": "battlefield"}}],
            "spell_effects": [{"op": "animate", "objects": {"target": "t1"}, **effect}],
        }
    )


class TestTheLoaderRefuses:
    def test_a_creature_animation_without_a_size(self):
        with pytest.raises(DslError, match="needs 'power' and 'toughness'"):
            compile_card(_probe({"types": ["Creature"]}))

    def test_half_a_size(self):
        with pytest.raises(DslError, match="needs 'power' and 'toughness'"):
            compile_card(_probe({"types": ["Artifact"], "power": {"const": 1}}))

    def test_keep_colors_on_an_additive_animation(self):
        with pytest.raises(DslError, match="only on an exact animation"):
            compile_card(_probe({"types": ["Artifact"], "keep_colors": True}))

    def test_keep_colors_beside_colors(self):
        with pytest.raises(DslError, match="contradict"):
            compile_card(
                _probe({"types": ["Artifact"], "exact": True, "keep_colors": True, "colors": ["G"]})
            )

    def test_the_witness_shape_compiles(self):
        compile_card(
            _probe({"types": ["Artifact"], "subtypes": ["Treasure"], "exact": True,
                    "keep_colors": True, "duration": "permanent"})
        )
