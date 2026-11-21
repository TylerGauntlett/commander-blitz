"""The as-enters copy that has a quoted ability as part of the copy.

    "You may have this artifact enter as a copy of any creature on the
    battlefield, except it's an artifact **and it has "{T}: Add {U}."**
    (It's not a creature.)"                          -- Machine God's Effigy

707.9b: an exception is a copiable value. The quoted ability is written once
under the card's ``grantable_abilities`` and named by position in
``except_.add_abilities``; `_enter_battlefield` puts the positions on
`copying_add_abilities` and `GameState.card_of` appends the abilities to the
copied face, after the copied card's own, so every index the copied card
prints keeps meaning what it printed.

Without the key, the copy of a creature has only the creature's abilities: the
Effigy, which is no creature and so has no combat to offer, would be a mana rock
that makes no mana. A `grant_ability` after the copy is the near miss: a layer-6
grant rather than part of what the copy is.

The exception ends with the copy: a timed copy is its printed self after
cleanup, and a copy that leaves the battlefield is a new object (400.7).
"""

from __future__ import annotations

import dataclasses

import pytest

from commanderblitz.cards.authoring.verify import _covered
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until
from tests.unit.copies.test_enters_as_copy import cast, name_of
from tests.unit.copies.test_enters_as_copy_set_types import position, types_of

EFFIGY = "t_eaxa_effigy"  # copy of any creature, except an artifact with "{T}: Add {U}."
MIRROR = "t_eaxa_mirror"  # the same until end of turn, printing no ability itself
BEAR = "t_bear"  # 2/2 Creature - Bear, no abilities
ELVES = "llanowar_elves"  # {T}: Add {G}.


def ability_texts(game, oid: int) -> list[str]:
    return [a.text for a in game.state.card_of(game.state.objects[oid]).abilities]


def blue(game, pid: int = 0) -> int:
    return game.state.players[pid].mana_pool.amounts[SYMBOL_INDEX["U"]]


class TestTheCopyHasTheQuotedAbility:
    def test_a_copy_of_a_vanilla_creature_has_only_the_quoted_ability(self, builder):
        game = position(builder, EFFIGY)
        cast(game, EFFIGY)
        oid = only_oid(game, EFFIGY, 0)
        assert name_of(game, oid) == "Test Bear"
        assert types_of(game, oid) == {"Artifact"}
        assert ability_texts(game, oid) == ["{T}: Add {U}."]

    def test_it_comes_after_the_copied_cards_own_abilities(self, builder):
        game = position(builder, EFFIGY, board=(ELVES,))
        cast(game, EFFIGY)
        oid = only_oid(game, EFFIGY, 0)
        abilities = game.state.card_of(game.state.objects[oid]).abilities
        assert [a.text for a in abilities][1] == "{T}: Add {U}."
        assert [a.index for a in abilities] == [0, 1]

    def test_the_quoted_ability_makes_mana(self, builder):
        """No creature, so no summoning sickness: it taps the turn it arrives."""
        game = position(builder, EFFIGY)
        cast(game, EFFIGY)
        oid = only_oid(game, EFFIGY, 0)
        before = blue(game)
        activate_mana_ability(game.state, oid, 0, 0)
        assert blue(game) == before + 1
        assert game.state.objects[oid].tapped

    def test_the_copied_card_itself_does_not_have_it(self, builder):
        game = position(builder, EFFIGY)
        cast(game, EFFIGY)
        assert ability_texts(game, only_oid(game, BEAR, 1)) == []

    def test_declining_the_copy_leaves_the_printed_ability_alone(self, builder):
        game = position(builder, EFFIGY)
        cast(game, EFFIGY, say_yes=False)
        oid = only_oid(game, EFFIGY, 0)
        assert name_of(game, oid) == "Test Mana Effigy"
        assert ability_texts(game, oid) == ["{T}: Add {U}."]
        assert game.state.objects[oid].copying_add_abilities is None


class TestTheExceptionEndsWithTheCopy:
    def test_a_timed_copy_loses_the_quoted_ability_at_cleanup(self, builder):
        game = position(builder, MIRROR, mine=(BEAR,))
        cast(game, MIRROR)
        oid = only_oid(game, MIRROR, 0)
        assert ability_texts(game, oid) == ["{T}: Add {U}."]
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        obj = game.state.objects[oid]
        assert obj.copying is None and obj.copying_add_abilities is None
        assert ability_texts(game, oid) == []

    def test_the_ability_does_not_outlive_the_object(self, builder):
        game = position(builder, MIRROR)
        cast(game, MIRROR)
        oid = only_oid(game, MIRROR, 0)
        move_object(game.state, oid, Zone.HAND)
        obj = game.state.objects[oid]
        assert obj.copying_add_abilities is None
        assert ability_texts(game, oid) == []


def _model(except_: dict, grantable: int = 1) -> CardModel:
    ability = {
        "kind": "activated",
        "text": "{T}: Add {U}.",
        "is_mana_ability": True,
        "cost": {"tap": True},
        "effects": [{"op": "add_mana", "mana": "{U}"}],
    }
    return CardModel.model_validate(
        {
            "id": "t_eaxa_probe",
            "name": "Probe",
            "mana_cost": "{4}",
            "types": ["Artifact"],
            "grantable_abilities": [ability] * grantable,
            "replacements": [
                {
                    "event": "self_enters_as_copy",
                    "copying": {"zone": "battlefield", "types": ["Creature"]},
                    "except_": except_,
                }
            ],
        }
    )


class TestTheLoaderChecksThePositions:
    def test_a_position_the_card_has_loads(self):
        compile_card(_model({"add_abilities": [0]}))

    def test_a_position_out_of_range_is_refused(self):
        with pytest.raises(DslError, match="add_abilities"):
            compile_card(_model({"add_abilities": [1]}))

    def test_a_card_with_no_grantable_abilities_is_refused(self):
        with pytest.raises(DslError, match="add_abilities"):
            compile_card(_model({"add_abilities": [0]}, grantable=0))

    def test_an_empty_list_is_refused(self):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_model({"add_abilities": []}))

    def test_a_position_that_is_not_a_number_is_refused(self):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_model({"add_abilities": ["0"]}))

    def test_one_ability_named_twice_is_refused(self):
        with pytest.raises(DslError, match="twice"):
            compile_card(_model({"add_abilities": [0, 0]}, grantable=2))


class TestTheVerifierWantsTheQuotedAbility:
    """The printed "{T}: Add {U}." is a substring of the quote, so without the
    replacement owning its sentence a copy with no such ability would claim it."""

    LINE = (
        "You may have this artifact enter as a copy of any creature on the "
        "battlefield, except it's an artifact and it has \"{T}: Add {U}.\""
    )

    def _with(self, registry, except_: dict):
        card = registry.get(EFFIGY)
        replacement = {**card.replacements[0], "except_": except_}
        return dataclasses.replace(card, replacements=(replacement,))

    def test_the_sentence_is_claimed_with_the_ability(self, registry):
        assert _covered(registry.get(EFFIGY), self.LINE)

    def test_a_copy_without_it_cannot_claim_the_sentence(self, registry):
        card = self._with(registry, {"set_types": ["Artifact"]})
        assert not _covered(card, self.LINE)

    def test_an_ability_nobody_quoted_cannot_claim_it_either(self, registry):
        line = "You may have this artifact enter as a copy of any creature on the battlefield, except it's an artifact"
        assert not _covered(registry.get(EFFIGY), line)
