""""Commanders you control have protection from everything." -- 702.16i

    Vexilus Praetor -- "Aegis of the Emperor — Commanders you control have
    protection from everything."

Protection from everything (702.16i) existed only on the one-shot
`grant_protection` op, which lasts until end of turn for an object (Teferi's
Protection's player half aside). A lasting static could not say it: the
`protection` static's qualities are types, subtypes, colours and colorless, and
listing every one of them still misses what has none of them -- a colourless
artifact with no subtypes.

So the static takes the op's own flag, ``from_everything: true``, stored as the
same `PROTECTION_EVERYTHING` sentinel the op installs, and every rule that reads
protection -- damage, enchant/equip, block, target -- sees it unchanged.

The boundaries: it reaches only what `affects` names (a commander, not every
creature), it stops its own controller too, and it lasts exactly as long as its
source is on the battlefield.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import protected_from, protection_from
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, damage_permanent
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.structs import PROTECTION_EVERYTHING, CombatState
from commanderblitz.engine.targeting import can_be_targeted
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid

COMMANDER = "t_mv3"  # our commander, a green 3/3
BEAR = "t_bear"  # ours, not a commander
ROBOT = "t_artifact_blocker"  # theirs: colourless artifact creature, no colour to match
FOUR = "t_mv4"  # theirs: green 4/4

AEGIS = {
    "kind": "static",
    "effect": "protection",
    "affects": {"controller": "you", "is_commander": True},
    "from_everything": True,
}


def praetor() -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_aegis_praetor",
            "name": "Aegis Praetor",
            "oracle_text": "Flash\nVigilance\nCommanders you control have protection "
            "from everything.",
            "mana_cost": "{4}{W}",
            "types": ["Creature"],
            "colors": ["W"],
            "color_identity": ["W"],
            "keywords": ["flash", "vigilance"],
            "power": 4,
            "toughness": 4,
            "abilities": [AEGIS],
        }
    )


def board(registry):
    """The Praetor, our commander on the battlefield and a Bear; their Robot and 4/4."""
    model = praetor()
    cards = {card.id: card for card in registry}
    cards[model.id] = compile_card(model)
    game = (
        GameBuilder(CardRegistry(cards), players=2)
        .battlefield(0, [model.id, BEAR])
        .commander(0, [COMMANDER])
        .battlefield(1, [ROBOT, FOUR])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .active(0)
        .build()
    )
    (commander,) = game.state.players[0].commanders
    move_object(game.state, commander, Zone.BATTLEFIELD, to_player=0)
    game.state.bump_chars()
    return (
        game,
        only_oid(game, model.id, 0),
        commander,
        only_oid(game, BEAR, 0),
        only_oid(game, ROBOT, 1),
        only_oid(game, FOUR, 1),
    )


class TestWhoHasIt:
    def test_the_commander_has_the_sentinel(self, registry):
        game, _, commander, _, _, _ = board(registry)
        assert protection_from(game.state, commander) == frozenset({PROTECTION_EVERYTHING})

    def test_a_creature_that_is_not_a_commander_does_not(self, registry):
        game, _, _, bear, robot, _ = board(registry)
        assert protection_from(game.state, bear) == frozenset()
        assert not protected_from(game.state, bear, robot)

    def test_it_ends_when_the_praetor_leaves(self, registry):
        """A static, not a grant: no until-end-of-turn record outlives it."""
        game, praetor_oid, commander, _, robot, _ = board(registry)
        move_object(game.state, praetor_oid, Zone.GRAVEYARD)
        game.state.bump_chars()
        assert protection_from(game.state, commander) == frozenset()
        assert not protected_from(game.state, commander, robot)


class TestTheFourRulesAgainstEverything:
    """A colourless artifact is the source no list of qualities could match."""

    def test_damage_from_anything_is_prevented(self, registry):
        game, _, commander, _, robot, four = board(registry)
        assert damage_permanent(game.state, commander, 2, robot) == 0
        assert damage_permanent(game.state, commander, 2, four) == 0
        assert game.state.objects[commander].damage == 0

    def test_it_cannot_be_targeted_by_anything(self, registry):
        game, _, commander, _, robot, four = board(registry)
        assert not can_be_targeted(game.state, 1, commander, source_oid=robot)
        assert not can_be_targeted(game.state, 1, commander, source_oid=four)

    def test_protection_stops_its_own_controller_too(self, registry):
        game, praetor_oid, commander, _, _, _ = board(registry)
        assert not can_be_targeted(game.state, 0, commander, source_oid=praetor_oid)

    def test_it_cannot_be_blocked(self, registry):
        game, _, commander, _, robot, four = board(registry)
        game.state.combat = CombatState()
        game.state.combat.attackers[commander] = 1
        game.state.bump_chars()
        assert not can_block(game.state, robot, commander, 1)
        assert not can_block(game.state, four, commander, 1)

    def test_it_cannot_be_enchanted_or_equipped(self, registry):
        game, _, commander, bear, robot, _ = board(registry)
        assert not attach(game.state, robot, commander)
        assert game.state.objects[robot].attached_to is None

        assert attach(game.state, robot, bear), "the Bear is not a commander"


class TestTheLoaderRefusesNonsense:
    def _static(self, static: dict):
        return CardModel.model_validate(
            {
                "id": "t_bad_static",
                "name": "Bad Static",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [{"kind": "static", "affects": {"self_only": True}, **static}],
            }
        )

    def test_the_flag_alone_is_a_quality(self):
        compile_card(self._static({"effect": "protection", "from_everything": True}))

    def test_false_alone_is_protection_from_nothing(self):
        with pytest.raises(DslError, match="protection needs"):
            compile_card(self._static({"effect": "protection", "from_everything": False}))

    @pytest.mark.parametrize(
        "other",
        [
            {"from_colorless": True},
            {"from_colors": ["W"]},
            {"from_types": ["Artifact"]},
            {"from_subtypes": ["Wizard"]},
            {"from_mana_value": {"op": "<=", "value": 3}},
            {"from_colors_outside_commander_identity": True},
        ],
    )
    def test_beside_another_quality_it_is_dead_weight(self, other):
        with pytest.raises(DslError, match="'from_everything' already covers"):
            compile_card(
                self._static({"effect": "protection", "from_everything": True, **other})
            )

    def test_the_sentinel_is_not_a_subtype(self):
        with pytest.raises(DslError, match="is not a subtype"):
            compile_card(self._static({"effect": "protection", "from_subtypes": ["everything"]}))

    def test_it_needs_the_protection_effect(self):
        with pytest.raises(DslError, match="need effect 'protection'"):
            compile_card(
                self._static(
                    {"effect": "grant_keyword", "keywords": ["flying"], "from_everything": True}
                )
            )
