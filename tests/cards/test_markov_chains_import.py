"""Markov Chains, imported from its live Moxfield list, every card engine-native.

The deck was pinned by #22, #24 and #28 and then kept moving: the list gained
Ghostly Prison, and a pasted link came back 90 of 91 distinct cards native,
with the one pillowfort in it reading as inert text. It moved again -- Canyon
Slough and Zulaport Cutthroat out, Clever Concealment and Edgar, Ancient
Bloodlord in -- and came back 90 of 91 with Edgar partial. Then once more --
Vampire Nocturnus out, Carmen, Cruel Skymarcher in -- and 90 of 91 with Carmen
partial, until #53 wrote her. Then Florian, Malakir Bloodwitch and Sundown
Pass out, Authority of the Consuls, Bloodline Recollector and an eighth Swamp
in -- 89 of 90 with Bloodline Recollector's prepare trigger inert, until it
was written. This file holds the list
as it now stands, imported through the same `importer.import_deck` a pasted
link goes through, so a card dropping out of `data/cards/auto/` or an engine
change invalidating one fails here rather than in a game.

Deliberately a *list* and not `data/decks/edgar_markov.deck.json`: that file is
the curated preset deck, a different 100 cards, and the claim here is about
what the importer says for somebody's real decklist.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry

COMMANDER = "Edgar Markov"
#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
DECK: tuple[tuple[str, int], ...] = (
    ("Akroma's Will", 1),
    ("Anguished Unmaking", 1),
    ("Anowon, the Ruin Sage", 1),
    ("Arcane Signet", 1),
    ("Authority of the Consuls", 1),
    ("Baron Bertram Graywater", 1),
    ("Bartolomé del Presidio", 1),
    ("Bastion of Remembrance", 1),
    ("Battlefield Forge", 1),
    ("Black Market Connections", 1),
    ("Blade of the Bloodchief", 1),
    ("Blood Artist", 1),
    ("Blood Crypt", 1),
    ("Bloodghast", 1),
    ("Bloodletter of Aclazotz", 1),
    ("Bloodline Keeper // Lord of Lineage", 1),
    ("Bloodline Recollector // Ancestral Craving", 1),
    ("Bloodthirsty Conqueror", 1),
    ("Bojuka Bog", 1),
    ("Captivating Vampire", 1),
    ("Carmen, Cruel Skymarcher", 1),
    ("Carrion Feeder", 1),
    ("Caves of Koilos", 1),
    ("Charismatic Conqueror", 1),
    ("Clavile\u00f1o, First of the Blessed", 1),
    ("Clever Concealment", 1),
    ("Command Tower", 1),
    ("Cordial Vampire", 1),
    ("Cruel Celebrant", 1),
    ("Dark Ritual", 1),
    ("Dragonskull Summit", 1),
    ("Edgar, Ancient Bloodlord", 1),
    ("Edgar, Charmed Groom // Edgar Markov's Coffin", 1),
    ("Elenda, the Dusk Rose", 1),
    ("Exotic Orchard", 1),
    ("Fetid Heath", 1),
    ("Forerunner of the Legion", 1),
    ("Ghostly Prison", 1),
    ("Godless Shrine", 1),
    ("Grave Pact", 1),
    ("Haunted Ridge", 1),
    ("Henrika Domnathi // Henrika, Infernal Seer", 1),
    ("Herald's Horn", 1),
    ("High-Society Hunter", 1),
    ("Impact Tremors", 1),
    ("Indulgent Aristocrat", 1),
    ("Isolated Chapel", 1),
    ("Legion Lieutenant", 1),
    ("Malakir Rebirth // Malakir Mire", 1),
    ("Marauding Blight-Priest", 1),
    ("Master of Dark Rites", 1),
    ("Mirkwood Bats", 1),
    ("Necropotence", 1),
    ("New Blood", 1),
    ("Nomad Outpost", 1),
    ("Olivia's Wrath", 1),
    ("Oubliette", 1),
    ("Path of Ancestry", 1),
    ("Patron of the Vein", 1),
    ("Phyrexian Tower", 1),
    ("Plains", 4),
    ("Qarsi Revenant", 1),
    ("Ruthless Lawbringer", 1),
    ("Sacred Foundry", 1),
    ("Sanctum Seeker", 1),
    ("Shared Animosity", 1),
    ("Shattered Sanctum", 1),
    ("Skullclamp", 1),
    ("Smoldering Marsh", 1),
    ("Sol Ring", 1),
    ("Sorin, Imperious Bloodlord", 1),
    ("Soul Shatter", 1),
    ("Stromkirk Captain", 1),
    ("Sulfurous Springs", 1),
    ("Swamp", 8),
    ("Swords to Plowshares", 1),
    ("Takenuma, Abandoned Mire", 1),
    ("Talisman of Conviction", 1),
    ("Talisman of Hierarchy", 1),
    ("Talisman of Indulgence", 1),
    ("Teferi's Protection", 1),
    ("Vault of the Archangel", 1),
    ("Vein Ripper", 1),
    ("Village Rites", 1),
    ("Viscera Seer", 1),
    ("Vito, Thorn of the Dusk Rose", 1),
    ("Voldaren Estate", 1),
    ("War Room", 1),
    ("Welcoming Vampire", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="Sr3op2p6G0m0Msv1n_jLZw",
        name="Markov Chains",
        format="commander",
        commanders=(COMMANDER,),
        cards=DECK,
    )
    return import_deck(deck, default_registry().registry, load_index(), dry_run=True)


class TestEveryCardIsNative:
    def test_the_list_is_a_hundred_cards(self, report):
        """A 99-card deck is not a deck, so the arithmetic is asserted first.

        If a name were dropped the count would fall and every other assertion
        here would still pass, which is the one way this file could lie.
        """
        assert report.total == 100
        assert len(report.cards) == 90

    def test_nothing_is_a_proxy(self, report):
        """The claim. `partial` means the printed text is inert."""
        not_native = sorted(c.name for c in report.cards if c.origin != "native")
        assert not_native == []

    def test_nothing_was_simplified(self, report):
        assert report.simplified == 0
        assert report.playable == 100

    def test_no_card_carries_a_note(self, report):
        """A note is the importer saying what it had to give up."""
        noted = {c.name: c.notes for c in report.cards if c.notes}
        assert noted == {}


class TestTheManaBaseIsReal:
    def test_every_land_makes_mana_or_does_something(self, report):
        """A land generated as an inert permanent leaves a deck that looks like
        34 lands and plays like fewer. `lands_inert` counts the ones doing
        nothing at all."""
        assert report.lands == 34
        assert report.lands_inert == 0
