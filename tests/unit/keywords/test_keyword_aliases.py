"""One ability, two printed names.

Rule 702.88 is *totem armor*, and it has been implemented since regeneration
was: ``zones.destroy`` reads ``Keyword.TOTEM_ARMOR`` and replaces the
destruction. But the Rise of the Eldrazi Umbra cycle -- Bear Umbra, Eel Umbra,
Snake Umbra, and nine more -- prints that identical ability as **"Umbra armor"**,
and Scryfall's ``keywords`` array repeats the printed spelling rather than the
rule's.

So every Umbra was unshippable for a reason that had nothing to do with the
rules: ``lift_keywords`` folds a printed line to ``umbra_armor``, that word is in
no vocabulary, the line is never claimed, and the residual gate rejects the card
as half-implemented. The mechanic was finished and the *name* was missing.

The fix is an alias, not a second ``Keyword`` member. Two enum values for one
ability would oblige every reader of a keyword set to check both, and the first
one that forgot would be a creature quietly losing its totem armor -- exactly the
silent wrongness the authoring gates exist to catch.

The witness is Bear Umbra, and the near miss asserted below is the one that
matters: a card must not be able to *claim* the line without having the
keyword, which is how Simic Sky Swallower once shipped shroud as hexproof.
"""

from __future__ import annotations

from commanderblitz.cards.loader.vocabulary import (
    KEYWORD_ALIASES,
    KNOWN_KEYWORDS,
    normalize_keyword,
)
from commanderblitz.cards.proxy import lift_keywords
from commanderblitz.engine.enums import Keyword

BEAR_UMBRA = (
    "Enchant creature\n"
    'Enchanted creature gets +2/+2 and has "Whenever this creature attacks, '
    'untap all lands you control."\n'
    "Umbra armor (If enchanted creature would be destroyed, instead remove all "
    "damage from it and destroy this Aura.)"
)

#: Exactly what the catalog carries for Bear Umbra, printed spelling and all.
SCRYFALL_KEYWORDS = ("Umbra armor", "Enchant")


class TestTheAliasNamesSomethingReal:
    def test_every_alias_resolves_to_an_implemented_keyword(self):
        """An alias pointing at a word no ``Keyword`` has is worse than none.

        It would make the residual gate consume a printed line and hand the card
        a keyword the engine never reads -- an inert ability that looks claimed.
        """
        for printed, engine in KEYWORD_ALIASES.items():
            assert engine in KNOWN_KEYWORDS, f"{printed} -> {engine} is not a keyword"
            assert printed not in KNOWN_KEYWORDS, f"{printed} is a keyword in its own right"

    def test_umbra_armor_is_totem_armor(self):
        assert normalize_keyword("umbra_armor") == Keyword.TOTEM_ARMOR.value

    def test_a_word_that_is_not_an_alias_is_unchanged(self):
        assert normalize_keyword("flying") == "flying"
        assert normalize_keyword("not_a_keyword") == "not_a_keyword"


class TestBearUmbraCanBeRead:
    def test_the_printed_line_yields_totem_armor(self):
        """The whole point: the printed word reaches the engine's keyword."""
        keywords, _ = lift_keywords(BEAR_UMBRA, SCRYFALL_KEYWORDS)
        assert Keyword.TOTEM_ARMOR.value in keywords

    def test_the_printed_line_is_consumed(self):
        """Gate 3 rejects a card with any printed line left over.

        The reminder text is stripped before the fold, so the whole parenthetical
        goes with the line it explains.
        """
        _, consumed = lift_keywords(BEAR_UMBRA, SCRYFALL_KEYWORDS)
        assert any(line.startswith("Umbra armor") for line in consumed)

    def test_the_other_lines_are_left_alone(self):
        """Only the keyword line is consumed; the Aura's real text survives.

        If the enchant clause or the +2/+2 line were swallowed here they would be
        unimplemented *and* unreported, which is the failure mode the residual
        gate exists for.
        """
        _, consumed = lift_keywords(BEAR_UMBRA, SCRYFALL_KEYWORDS)
        assert not any("Enchant creature" in line for line in consumed)
        assert not any("+2/+2" in line for line in consumed)


class TestStrictStillRefusesAnUnearnedClaim:
    """``strict=True`` is the audit: ``printed`` is what the card actually has.

    The alias must not become a way to claim a line the card does not implement.
    """

    def test_a_card_without_the_keyword_cannot_claim_the_line(self):
        _, consumed = lift_keywords(BEAR_UMBRA, ("enchant",), strict=True)
        assert not any(line.startswith("Umbra armor") for line in consumed)

    def test_a_card_carrying_totem_armor_claims_it(self):
        """The card file says ``totem_armor``; the card says "Umbra armor"."""
        _, consumed = lift_keywords(
            BEAR_UMBRA, (Keyword.TOTEM_ARMOR.value, "enchant"), strict=True
        )
        assert any(line.startswith("Umbra armor") for line in consumed)
