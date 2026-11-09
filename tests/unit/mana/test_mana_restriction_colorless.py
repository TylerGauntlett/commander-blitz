""""Spend this mana only to cast **colorless** Eldrazi spells or activate
abilities of **colorless** Eldrazi."  -- Eldrazi Temple; Shrine of the Forsaken
Gods says "colorless spells".

Colour is not a type, so `SpendPurpose.names` never held it. Both spellings
available before this were wrong, in opposite directions:

- `["colorless"]` as a name would match nothing ever -- mana that can never be
  spent. `mana._restriction_name` now refuses the word, because it is a
  predicate.
- `["eldrazi"]` alone funds a coloured Eldrazi too: a strictly better card.

So a group carries a `colorless` predicate, answered by `costs.spell_purpose`
off the printed colours and by `costs.ability_purpose` off the source's
current ones, the same split it already makes for names.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.costs import spell_purpose
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import (
    ACTIVATE,
    CAST,
    OTHER_PAYMENT,
    ManaSource,
    SpendPurpose,
    compile_restriction,
)

TEMPLE = [["eldrazi", {"colorless": True}]]


def source(spec):
    restriction = compile_restriction({"cast": spec, "activate": spec}, "test")
    return ManaSource(oid=1, ability_index=0, options=((0, 0, 0, 0, 0, 2),), restriction=restriction)


def purpose(kind, names, *, colorless):
    return SpendPurpose(kind, frozenset(names), colorless=colorless)


class TestTheTemple:
    def test_a_colorless_eldrazi_spell_is_permitted(self):
        assert source(TEMPLE).permits(purpose(CAST, {"creature", "eldrazi"}, colorless=True))

    def test_a_coloured_eldrazi_spell_is_not(self):
        """The half `["eldrazi"]` alone would drop."""
        assert not source(TEMPLE).permits(purpose(CAST, {"creature", "eldrazi"}, colorless=False))

    def test_a_colorless_non_eldrazi_is_not(self):
        assert not source(TEMPLE).permits(purpose(CAST, {"artifact"}, colorless=True))

    def test_an_ability_of_a_colorless_eldrazi_is_permitted(self):
        assert source(TEMPLE).permits(purpose(ACTIVATE, {"creature", "eldrazi"}, colorless=True))

    def test_an_unanswered_question_fails(self):
        """A purpose that does not say whether it is colorless is refused, the
        under-permitting direction every restriction takes."""
        assert not source(TEMPLE).permits(SpendPurpose(CAST, frozenset({"creature", "eldrazi"})))
        assert not source(TEMPLE).permits(OTHER_PAYMENT)


class TestTheShrine:
    def test_any_colorless_spell_is_permitted(self):
        shrine = source([[{"colorless": True}]])
        assert shrine.permits(purpose(CAST, {"artifact"}, colorless=True))
        assert not shrine.permits(purpose(CAST, {"artifact"}, colorless=False))


class TestThePurposeAnswersIt:
    def test_a_colorless_card_is_colorless(self, registry):
        assert spell_purpose(registry.get("eldrazi_10_10_c")).colorless is True

    def test_a_coloured_card_is_not(self, registry):
        assert spell_purpose(registry.get("t_bear")).colorless is False


class TestTheLoaderChecksIt:
    def test_the_word_as_a_name_is_refused(self):
        """The permanently unspendable spelling."""
        with pytest.raises(DslError, match="predicate"):
            compile_restriction([["colorless"]], "test")

    def test_a_non_boolean_is_refused(self):
        with pytest.raises(DslError, match="true or false"):
            compile_restriction([[{"colorless": {"op": ">=", "value": 1}}]], "test")
