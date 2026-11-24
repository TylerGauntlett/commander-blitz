""""{T}: Add one mana of any color. Spend this mana only to cast a
**multicolored** spell."  -- Obsidian Obelisk; Pillar of the Paruns prints the
same restriction.

Multicolored is two or more colours (202.2b), and colour is not a type, so
`SpendPurpose.names` never held it. Both spellings available before this were
wrong, in opposite directions:

- `["multicolored"]` as a name would match nothing ever -- mana that can never
  be spent. `mana._restriction_name` now refuses the word.
- `{"colorless": false}` funds a one-colour spell too: a strictly better card.

So a group carries a `min_colors` predicate, spelled as the filter languages
spell it, and `costs.spell_purpose` answers it off the printed colours, as it
answers `colorless`.
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

OBELISK = [[{"min_colors": 2}]]


def source(spec):
    restriction = compile_restriction({"cast": spec}, "test")
    return ManaSource(oid=1, ability_index=0, options=((1, 1, 1, 1, 1, 0),), restriction=restriction)


def spell(colors: int) -> SpendPurpose:
    return SpendPurpose(CAST, frozenset({"creature"}), colors_count=colors)


class TestTheObelisk:
    def test_a_two_colour_spell_is_permitted(self):
        assert source(OBELISK).permits(spell(2))

    def test_a_five_colour_spell_is_permitted(self):
        assert source(OBELISK).permits(spell(5))

    def test_a_one_colour_spell_is_not(self):
        """The spell `{"colorless": false}` would have funded."""
        assert not source(OBELISK).permits(spell(1))

    def test_a_colorless_spell_is_not(self):
        assert not source(OBELISK).permits(spell(0))

    def test_an_ability_is_not(self):
        """"Only to cast": the activate half is never granted."""
        purpose = SpendPurpose(ACTIVATE, frozenset({"creature"}), colors_count=5)
        assert not source(OBELISK).permits(purpose)

    def test_an_unanswered_question_fails(self):
        """A purpose that cannot count its colours is refused, the
        under-permitting direction every restriction takes."""
        assert not source(OBELISK).permits(SpendPurpose(CAST, frozenset({"creature"})))
        assert not source(OBELISK).permits(OTHER_PAYMENT)

    def test_it_combines_with_a_name(self):
        """"…a multicolored creature spell" is the name and the count at once."""
        gold_creatures = source([["creature", {"min_colors": 2}]])
        assert gold_creatures.permits(spell(2))
        assert not gold_creatures.permits(SpendPurpose(CAST, frozenset({"instant"}), colors_count=2))


class TestThePurposeAnswersIt:
    def test_a_five_colour_card_counts_five(self, registry):
        assert spell_purpose(registry.get("chromanticore")).colors_count == 5

    def test_a_two_colour_card_counts_two(self, registry):
        assert spell_purpose(registry.get("t_mc_gold")).colors_count == 2

    def test_a_one_colour_card_counts_one(self, registry):
        assert spell_purpose(registry.get("t_bear")).colors_count == 1


class TestTheLoaderChecksIt:
    def test_the_word_as_a_name_is_refused(self):
        """The permanently unspendable spelling."""
        with pytest.raises(DslError, match="min_colors"):
            compile_restriction([["multicolored"]], "test")

    @pytest.mark.parametrize("value", [0, 6, True, "2", {"op": ">=", "value": 2}])
    def test_anything_but_one_to_five_is_refused(self, value):
        with pytest.raises(DslError, match="min_colors"):
            compile_restriction([[{"min_colors": value}]], "test")
