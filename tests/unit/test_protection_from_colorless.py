""""…gains protection from colorless or from the color of your choice" -- 702.16, 105.2c

    Giver of Runes -- "{T}: Another target creature you control gains
    protection from colorless or from the color of your choice until end of
    turn."

Colorless is not a colour (105.2c), but "protection from colorless" is a
quality of its own (702.16a: protection is "from [quality]"). Nothing could
spell it. `grant_protection`'s `from_colors` holds colour letters, and
`_matches_protection` intersects the qualities with the source's types,
subtypes and colours -- a colourless artifact creature has an empty colour set,
so no quality built from what a source *has* can ever match it. It is the one
quality matched on what the source lacks.

So it went the way `from_everything` went: a boolean on the op (and on the
printed `protection` static), stored as the sentinel `PROTECTION_COLORLESS` in
the same flat set of qualities the four rules -- damage, enchant/equip, block,
target -- already read. Without it, Giver of Runes would be Mother of Runes
with a missing sixth mode, and that missing mode is the card's whole reason to
exist in a deck facing artifact creatures.

The boundary that matters: **"colorless" must not match a source with any
colour.** A white creature walks straight through it.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.registry import CardRegistry
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import protected_from, protection_from
from automtg.engine.combat import can_block
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.primitives import attach, damage_permanent
from automtg.engine.sandbox import GameBuilder
from automtg.engine.structs import PROTECTION_COLORLESS, CombatState, TargetRef
from automtg.engine.targeting import can_be_targeted
from automtg.engine.turn import clear_until_eot
from tests.conftest import only_oid

BEAR = "t_bear"  # green 2/2 -- the creature that gains protection
ROBOT = "t_artifact_blocker"  # colourless {3} artifact creature
SOLDIER = "t_human_soldier"  # white 2/2


def board(builder, *, hand: list[str] | None = None):
    """Our Bear, granted protection from colorless; their Robot and Soldier."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR, "plains", "plains"])
        .battlefield(1, [ROBOT, SOLDIER])
        .hand(1, hand or [])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .active(0)
        .build()
    )
    bear = only_oid(game, BEAR, 0)
    grant(game, bear, {"from_colorless": True})
    return game, bear, only_oid(game, ROBOT, 1), only_oid(game, SOLDIER, 1)


def grant(game, oid: int, quality: dict) -> None:
    """Resolve the op itself, the way Giver of Runes' colorless mode does."""
    ctx = EffectContext(
        state=game.state, controller=0, source_oid=None, targets={"t1": (TargetRef.obj(oid),)}
    )
    list(
        execute(
            ctx,
            [{"op": "grant_protection", "objects": {"target": "t1"}, **quality}],
        )
    )


class TestTheQualityIsGranted:
    def test_the_op_installs_the_sentinel(self, builder):
        game, bear, _, _ = board(builder)
        assert protection_from(game.state, bear) == frozenset({PROTECTION_COLORLESS})

    def test_it_wears_off_at_cleanup(self, builder):
        """"Until end of turn" -- a `TempEffect` on `until_eot`, which is swept."""
        game, bear, robot, _ = board(builder)
        clear_until_eot(game.state)
        assert protection_from(game.state, bear) == frozenset()
        assert not protected_from(game.state, bear, robot)


class TestTheFourRulesAgainstAColorlessSource:
    """Damage, Enchant/equip, Block, Target -- each paired with a white source."""

    def test_damage_from_it_is_prevented(self, builder):
        game, bear, robot, soldier = board(builder)
        assert damage_permanent(game.state, bear, 2, robot) == 0
        assert game.state.objects[bear].damage == 0

        assert damage_permanent(game.state, bear, 1, soldier) == 1, "white is a colour"

    def test_it_cannot_be_targeted_by_it(self, builder):
        game, bear, robot, soldier = board(builder)
        assert not can_be_targeted(game.state, 1, bear, source_oid=robot)
        assert can_be_targeted(game.state, 1, bear, source_oid=soldier)

    def test_protection_stops_its_own_controller_too(self, builder):
        """The half a hexproof-shaped implementation would get wrong."""
        game, bear, robot, _ = board(builder)
        assert not can_be_targeted(game.state, 0, bear, source_oid=robot)

    def test_it_cannot_be_blocked_by_it(self, builder):
        game, bear, robot, soldier = board(builder)
        game.state.combat = CombatState()
        game.state.combat.attackers[bear] = 1
        game.state.bump_chars()

        assert not can_block(game.state, robot, bear, 1)
        assert can_block(game.state, soldier, bear, 1)

    def test_it_cannot_be_enchanted_or_equipped_by_it(self, builder):
        game, bear, robot, soldier = board(builder)
        assert not attach(game.state, robot, bear)
        assert game.state.objects[robot].attached_to is None

        assert attach(game.state, soldier, bear)

    def test_a_colorless_card_off_the_battlefield_is_read_by_its_printed_colours(
        self, builder
    ):
        """A spell's source is not on the battlefield; its printed colours count."""
        game, bear, _, _ = board(builder, hand=[ROBOT, SOLDIER])
        in_hand = {game.state.objects[o].def_id: o for o in game.state.players[1].hand}
        assert protected_from(game.state, bear, in_hand[ROBOT])
        assert not protected_from(game.state, bear, in_hand[SOLDIER])


class TestColorlessIsNotEveryColour:
    def test_a_coloured_source_is_never_matched(self, builder):
        """The boundary: "colorless" is what the source lacks, not a wildcard."""
        game, bear, _, soldier = board(builder)
        assert not protected_from(game.state, bear, soldier)

    def test_a_colour_mode_does_not_stop_a_colorless_source(self, builder):
        """The other five modes of Giver of Runes, from the other side."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, "plains"])
            .battlefield(1, [ROBOT, SOLDIER])
            .active(0)
            .build()
        )
        bear = only_oid(game, BEAR, 0)
        grant(game, bear, {"from_colors": ["W"]})
        assert protected_from(game.state, bear, only_oid(game, SOLDIER, 1))
        assert not protected_from(game.state, bear, only_oid(game, ROBOT, 1))


class TestThePrintedStatic:
    """`from_colorless` on the `protection` static reads the same quality."""

    def test_a_printed_static_protects_from_a_colorless_source(self, registry):
        model = CardModel.model_validate(
            {
                "id": "t_colorless_warded",
                "name": "Colorless Warded",
                "oracle_text": "Protection from colorless",
                "mana_cost": "{1}{W}",
                "types": ["Creature"],
                "colors": ["W"],
                "color_identity": ["W"],
                "power": 2,
                "toughness": 2,
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "protection",
                        "affects": {"self_only": True},
                        "from_colorless": True,
                    }
                ],
            }
        )
        cards = {card.id: card for card in registry}
        cards[model.id] = compile_card(model)
        game = (
            GameBuilder(CardRegistry(cards), players=2)
            .battlefield(0, [model.id])
            .battlefield(1, [ROBOT, SOLDIER])
            .active(0)
            .build()
        )
        warded = only_oid(game, model.id, 0)
        assert protection_from(game.state, warded) == frozenset({PROTECTION_COLORLESS})
        assert protected_from(game.state, warded, only_oid(game, ROBOT, 1))
        assert not protected_from(game.state, warded, only_oid(game, SOLDIER, 1))


class TestTheLoaderRefusesNonsense:
    def _spell(self, effect: dict):
        return CardModel.model_validate(
            {
                "id": "t_bad_protection",
                "name": "Bad Protection",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Instant"],
                "colors": ["W"],
                "color_identity": ["W"],
                "spell_effects": [
                    {
                        "op": "grant_protection",
                        "objects": {"zone": "battlefield", "controller": "you"},
                        **effect,
                    }
                ],
            }
        )

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
        compile_card(self._spell({"from_colorless": True}))

    def test_the_flag_is_a_boolean(self):
        with pytest.raises(DslError, match="'from_colorless' is a boolean"):
            compile_card(self._spell({"from_colorless": "yes"}))

    def test_false_alone_is_protection_from_nothing(self):
        with pytest.raises(DslError, match="needs a quality"):
            compile_card(self._spell({"from_colorless": False}))

    def test_beside_everything_it_is_dead_weight(self):
        with pytest.raises(DslError, match="already covers colorless"):
            compile_card(self._spell({"from_colorless": True, "from_everything": True}))

    @pytest.mark.parametrize("letter", ["C", "colorless"])
    def test_colorless_is_not_a_colour_letter(self, letter):
        """105.2c, and the spelling a hurried author reaches for first."""
        with pytest.raises(DslError, match="colorless is not a colour"):
            compile_card(self._spell({"from_colors": [letter]}))

    @pytest.mark.parametrize("word", ["colorless", "everything"])
    def test_a_sentinel_is_not_a_subtype(self, word):
        """`from_subtypes` is not checked against a subtype list, so the
        sentinel string would otherwise load as the quality without its flag."""
        with pytest.raises(DslError, match="is not a subtype"):
            compile_card(self._spell({"from_subtypes": [word]}))

    def test_the_static_refuses_the_letter_too(self):
        with pytest.raises(DslError, match="colorless is not a colour"):
            compile_card(self._static({"effect": "protection", "from_colors": ["C"]}))

    def test_the_static_refuses_a_sentinel_subtype(self):
        with pytest.raises(DslError, match="is not a subtype"):
            compile_card(self._static({"effect": "protection", "from_subtypes": ["colorless"]}))

    def test_the_static_flag_needs_the_protection_effect(self):
        with pytest.raises(DslError, match="need effect 'protection'"):
            compile_card(
                self._static(
                    {"effect": "grant_keyword", "keywords": ["flying"], "from_colorless": True}
                )
            )
