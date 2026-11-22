"""The as-enters copy whose type line is replaced, not added to.

    "You may have this artifact enter as a copy of any creature on the
    battlefield, **except it's an artifact** and it has "{T}: Add {U}."
    (It's not a creature.)"                          -- Machine God's Effigy

707.9b: the exception is a copiable value, so ``except_.set_types`` is written
onto the copy (`copying_set_types`, read by `GameState.card_of` beside
`copying_add_types`). It is the replacement beside Phyrexian Metamorph's
addition, and the printed words decide which: with no "in addition to its other
types" the copy of a Bear is an Artifact and nothing else. Written as
``add_types`` it would be an artifact creature that attacks, blocks and dies to
a wrath -- a strictly different card.

205.1b: the subtypes of a card type the copy no longer has go with it, as they
do under a `set_types` static. The copy of a Bear is no Bear; the copy of an
Equipment Golem artifact creature keeps Equipment, an artifact type, and loses
Golem.

The exception ends with the copy: a timed copy is its printed self after
cleanup, and a copy that leaves the battlefield is a new object (400.7).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until
from tests.unit.copies.test_enters_as_copy import cast, name_of

EFFIGY = "t_eaxt_effigy"  # artifact, copy of any creature except it's an artifact
MIRROR = "t_eaxt_mirror"  # the same, until end of turn
GOLEM = "t_eaxt_golem"  # 3/3 Artifact Creature - Equipment Golem
BEAR = "t_bear"  # 2/2 Creature - Bear


def position(builder, spell: str, board=(BEAR,), mine=()):
    """The model is the opponent's: "any creature on the battlefield"."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + list(mine))
        .battlefield(1, list(board))
        .hand(0, [spell])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def types_of(game, oid: int) -> set[str]:
    return {str(t) for t in chars(game.state, oid).types}


def subtypes_of(game, oid: int) -> set[str]:
    return {str(t) for t in chars(game.state, oid).subtypes}


class TestTheCopyIsOnlyAnArtifact:
    def test_a_copy_of_a_creature_is_no_creature(self, builder):
        game = position(builder, EFFIGY)
        cast(game, EFFIGY)
        oid = only_oid(game, EFFIGY, 0)
        assert name_of(game, oid) == "Test Bear"
        assert types_of(game, oid) == {"Artifact"}

    def test_its_creature_types_go_with_the_creature_type(self, builder):
        """205.1b: no Bear lord and no Bear count sees it."""
        game = position(builder, EFFIGY)
        cast(game, EFFIGY)
        assert subtypes_of(game, only_oid(game, EFFIGY, 0)) == set()

    def test_a_subtype_of_the_type_it_keeps_stays(self, builder):
        game = position(builder, EFFIGY, board=(GOLEM,))
        cast(game, EFFIGY)
        oid = only_oid(game, EFFIGY, 0)
        assert name_of(game, oid) == "Test Glass Golem"
        assert types_of(game, oid) == {"Artifact"}
        assert subtypes_of(game, oid) == {"Equipment"}

    def test_the_copied_card_itself_is_untouched(self, builder):
        game = position(builder, EFFIGY)
        cast(game, EFFIGY)
        bear = only_oid(game, BEAR, 1)
        assert types_of(game, bear) == {"Creature"}
        assert subtypes_of(game, bear) == {"Bear"}

    def test_declining_the_copy_leaves_the_printed_artifact(self, builder):
        game = position(builder, EFFIGY)
        cast(game, EFFIGY, say_yes=False)
        oid = only_oid(game, EFFIGY, 0)
        assert name_of(game, oid) == "Test Effigy"
        assert game.state.objects[oid].copying_set_types is None


class TestTheExceptionEndsWithTheCopy:
    def test_a_timed_copy_is_its_printed_self_after_cleanup(self, builder):
        """A Bear of our own keeps the game in this turn's combat to look."""
        game = position(builder, MIRROR, mine=(BEAR,))
        cast(game, MIRROR)
        oid = only_oid(game, MIRROR, 0)
        assert (name_of(game, oid), types_of(game, oid)) == ("Test Bear", {"Artifact"})
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        obj = game.state.objects[oid]
        assert obj.copying is None and obj.copying_set_types is None
        assert name_of(game, oid) == "Test Effigy Mirror"
        assert types_of(game, oid) == {"Artifact"}

    def test_the_type_line_does_not_outlive_the_object(self, builder):
        game = position(builder, EFFIGY)
        cast(game, EFFIGY)
        oid = only_oid(game, EFFIGY, 0)
        move_object(game.state, oid, Zone.HAND)
        obj = game.state.objects[oid]
        assert obj.copying is None and obj.copying_set_types is None
        assert game.state.card_of(obj).name == "Test Effigy"


def _model(except_: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_eaxt_probe",
            "name": "Probe",
            "mana_cost": "{3}",
            "types": ["Artifact"],
            "replacements": [
                {
                    "event": "self_enters_as_copy",
                    "copying": {"zone": "battlefield", "types": ["Creature"]},
                    "except_": except_,
                }
            ],
        }
    )


class TestTheLoaderChecksTheTypes:
    def test_a_known_type_loads(self):
        compile_card(_model({"set_types": ["Artifact"]}))

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            compile_card(_model({"set_types": ["Artefact"]}))

    def test_an_empty_list_is_refused(self):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_model({"set_types": []}))

    def test_replacing_and_adding_at_once_is_refused(self):
        with pytest.raises(DslError, match="set_types"):
            compile_card(_model({"set_types": ["Artifact"], "add_types": ["Enchantment"]}))
