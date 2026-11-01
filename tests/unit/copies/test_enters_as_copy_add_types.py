"""The as-enters copy that is an artifact in addition to what it copies.

    "You may have this creature enter as a copy of any artifact or creature on
    the battlefield, **except it's an artifact in addition to its other
    types**."                                           -- Phyrexian Metamorph

707.9b: an exception to a copy effect is part of the copiable values. So
``except_.add_types`` is written onto the copy itself (`copying_add_types`, read
by `GameState.card_of` beside `copying_keywords`), and the copy of a Bear is an
artifact creature from the moment it enters. Without it the Metamorph copying a
creature would be no artifact: every artifact count would miss it and every
"destroy target artifact" could not point at it, a different card.

The added type is the copy's, not the original's, and it ends with the copy:
a Metamorph that leaves the battlefield is a new object copying nothing (400.7).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid
from tests.unit.copies.test_enters_as_copy import cast, name_of
from tests.unit.copies.test_enters_as_copy_except import position

METAMORPH = "t_eacx_metamorph"  # 0/0, copy of an artifact or creature, plus Artifact
BEAR = "t_bear"  # 2/2 vanilla creature, the thing copied


def types_of(game, oid: int) -> set[str]:
    return {str(t) for t in chars(game.state, oid).types}


class TestTheCopyIsAlsoAnArtifact:
    def test_a_copy_of_a_creature_is_an_artifact_creature(self, builder):
        game = position(builder, METAMORPH)
        cast(game, METAMORPH)
        oid = only_oid(game, METAMORPH, 0)
        assert name_of(game, oid) == "Test Bear"
        assert types_of(game, oid) == {"Artifact", "Creature"}
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 2)

    def test_the_copied_card_itself_is_untouched(self, builder):
        game = position(builder, METAMORPH)
        cast(game, METAMORPH)
        assert types_of(game, only_oid(game, BEAR, 1)) == {"Creature"}

    def test_the_type_does_not_outlive_the_object(self, builder):
        game = position(builder, METAMORPH)
        cast(game, METAMORPH)
        oid = only_oid(game, METAMORPH, 0)
        move_object(game.state, oid, Zone.HAND)
        obj = game.state.objects[oid]
        assert obj.copying is None and obj.copying_add_types is None
        assert "Artifact" not in game.state.card_of(obj).types


def _model(except_: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_eacx_probe",
            "name": "Probe",
            "mana_cost": "{3}",
            "types": ["Creature"],
            "power": 0,
            "toughness": 0,
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
        compile_card(_model({"add_types": ["Artifact"]}))

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            compile_card(_model({"add_types": ["Artefact"]}))

    def test_an_empty_list_is_refused(self):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_model({"add_types": []}))
