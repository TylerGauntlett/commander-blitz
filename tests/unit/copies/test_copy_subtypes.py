"""The Scarab God — "…a copy of it, **except it's a 4/4 black Zombie**."

`copy_permanent`'s `except_` could add a subtype (`add_subtypes`, embalm's
"white Zombie **Angel**") and could not replace one. The printed clause has no
"in addition to its other types", so the token is a Zombie *instead of* its
creature types (205.1b; the Gatherer ruling on The Scarab God says so in as
many words). Benthic Anomaly's "it's a colorless Eldrazi creature", God-Pharaoh's
Gift, Hashaton and Lazotep Quarry print the same shape.

**A replacement, not an addition.** A union would leave a Zombie Bear, and a
Bear lord would pump a token the printed card never lets it touch.

`t_magicite_token` is the counterfactual for the rest of the clause: its copy
keeps the copied card's subtypes, because its printing does not mention them.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.errors import DslError

from .test_copy_type_change import BEAR, RETYPED, _copy, board, cast, token

SCARAB = "t_scarab_token"


class TestTheCopyIsOnlyAZombie:
    def test_it_is_a_zombie(self, builder):
        state, oid = token(cast(board(builder, SCARAB), SCARAB))
        assert set(chars(state, oid).subtypes) == {"Zombie"}

    def test_it_loses_the_copied_creature_types(self, builder):
        """The half a union would drop."""
        state, oid = token(cast(board(builder, SCARAB), SCARAB))
        assert "Bear" not in chars(state, oid).subtypes

    def test_the_rest_of_the_clause_still_applies(self, builder):
        state, oid = token(cast(board(builder, SCARAB), SCARAB))
        c = chars(state, oid)
        assert (c.power, c.toughness) == (4, 4)
        assert set(c.colors) == {"B"}
        assert "Creature" in c.types

    def test_it_is_still_a_copy_of_that_card(self, builder):
        state, oid = token(cast(board(builder, SCARAB), SCARAB))
        assert state.card_of(state.objects[oid]).id == BEAR

    def test_without_the_key_the_copy_keeps_its_subtypes(self, builder):
        state, oid = token(cast(board(builder, RETYPED), RETYPED))
        assert "Bear" in chars(state, oid).subtypes


class TestTheLoaderChecksIt:
    def test_a_subtype_list_loads(self):
        compile_card(_copy(subtypes=["Zombie"]), source="test")

    def test_an_empty_list_is_refused(self):
        """It replaces, so an empty list strips every subtype -- no printing says that."""
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_copy(subtypes=[]), source="test")

    def test_replacing_and_adding_at_once_is_refused(self):
        with pytest.raises(DslError, match="write the one the printed clause says"):
            compile_card(_copy(subtypes=["Zombie"], add_subtypes=["Angel"]), source="test")
