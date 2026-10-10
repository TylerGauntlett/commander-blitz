"""An Angel tribal list, every card engine-native -- the pasted-link guarantee.

**Giada, Font of Hope** leads "Choir Practice", a mono-white Angels deck whose engine
is the creature type itself: Giada's extra +1/+1 counters for each Angel already in
play and her Angel-only mana, Starnheim Aspirant's and Urza's Incubator's discounts,
the life-gain package that turns into 4/4 Angels at end of turn (Resplendent Angel,
Valkyrie Harbinger, Ob Nixilis, the Ascended, Lyra, Righteous Valkyrie, Angel of
Destiny), and the anthems and locks that protect it.

It started at **30 of 74 distinct cards** native. The other 44 took four token
definitions and a dozen capabilities -- Giada's counted enters-with replacement, a
life-gain addend, a block tax, a player's starting life total and the players a
creature attacked, a library-search trigger, a static zone cast lock, the putter of
a counter, a creature-type comparison with the trigger's own source, protection
from colorless, a Worship-style life floor, an alternative cost on a permanent,
"your commander" in a trigger filter, and the first shipped meld pair (Gisela and
Bruna into Brisela) -- plus three engine fixes the cards exposed: an intervening
"if" on a trigger that was silently dropped, life totals that did not refresh the
statics reading them, and counters a permanent enters with that never counted as
"put on" it (122.6).

So this file pins the same claim as its siblings: **every one of its 74 distinct
cards resolving `native`**, through the same `importer.import_deck` a pasted link
goes through. A card dropping out of `data/cards/auto/`, or an engine change
invalidating one, turns a `native` into a `partial` here rather than in somebody's
game.

Deliberately a *list* and not a `data/decks/*.deck.json`, for the reason the Lucy pin
gives: the deliverable is card-level support reached through the importer, so the test
asserts what the importer says.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry

COMMANDER = "Giada, Font of Hope"

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
DECK: tuple[tuple[str, int], ...] = (
    ("Akroma's Will", 1),
    ("Angel of Destiny", 1),
    ("Angel of Invention", 1),
    ("Angel of the Ruins", 1),
    ("Angel of Vitality", 1),
    ("Angelic Field Marshal", 1),
    ("Arcane Signet", 1),
    ("Archangel of Thune", 1),
    ("Archangel of Tithes", 1),
    ("Archivist of Oghma", 1),
    ("Austere Command", 1),
    ("Avacyn, Angel of Hope", 1),
    ("Bishop of Wings", 1),
    ("Bonders' Enclave", 1),
    ("Castle Ardenvale", 1),
    ("Cathars' Crusade", 1),
    ("Clever Concealment", 1),
    ("Court of Grace", 1),
    ("Dawn of Hope", 1),
    ("Dazzling Angel", 1),
    ("Drannith Magistrate", 1),
    ("Eiganjo, Seat of the Empire", 1),
    ("Elesh Norn, Grand Cenobite", 1),
    ("Emeria's Call // Emeria, Shattered Skyclave", 1),
    ("Emeria, the Sky Ruin", 1),
    ("Exemplar of Light", 1),
    ("Farewell", 1),
    ("Fateful Absence", 1),
    ("Flawless Maneuver", 1),
    ("Folk Hero", 1),
    ("Generous Gift", 1),
    ("Get Lost", 1),
    ("Ghostly Prison", 1),
    ("Gisela, the Broken Blade", 1),
    ("Giver of Runes", 1),
    ("Grasp of Fate", 1),
    ("Herald's Horn", 1),
    ("Heraldic Banner", 1),
    ("Inspiring Overseer", 1),
    ("Lyra Dawnbringer", 1),
    ("Lyra, Archangel of Dawn", 1),
    ("Magus of the Moat", 1),
    ("Metastatic Evangel", 1),
    ("Minas Tirith", 1),
    ("Mind Stone", 1),
    ("Norn's Choirmaster", 1),
    ("Ob Nixilis, the Ascended", 1),
    ("Patchwork Banner", 1),
    ("Path to Exile", 1),
    ("Pearl Medallion", 1),
    ("Plains", 27),
    ("Radiant Fountain", 1),
    ("Resplendent Angel", 1),
    ("Righteous Valkyrie", 1),
    ("Secluded Steppe", 1),
    ("Sephara, Sky's Blade", 1),
    ("Seraph Sanctuary", 1),
    ("Serra the Benevolent", 1),
    ("Sol Ring", 1),
    ("Starnheim Aspirant", 1),
    ("Swiftfoot Boots", 1),
    ("Swords to Plowshares", 1),
    ("The Wandering Emperor", 1),
    ("Thraben Watcher", 1),
    ("Three Tree City", 1),
    ("Tome of Legends", 1),
    ("Urza's Incubator", 1),
    ("Valkyrie Harbinger", 1),
    ("Valorous Stance", 1),
    ("Vanquisher's Banner", 1),
    ("War Room", 1),
    ("Wojek Investigator", 1),
    ("Youthful Valkyrie", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="choirpractice",
        name="Choir Practice",
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
        assert len(report.cards) == 74

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


class TestTheCommanderIsLegal:
    def test_giada_leads_the_deck(self, report):
        """A legendary creature, so 903.3 needs no sentence."""
        card = default_registry().registry.by_name(COMMANDER)
        assert card is not None and card.is_creature and card.is_legendary

    def test_her_mana_pays_only_for_angels(self):
        """The rider the proxy tier could not generate, and the line most likely to
        be dropped by a careless re-author: "Spend this mana only to cast an Angel
        spell." Without it Giada is an unrestricted mana dork."""
        card = default_registry().registry.by_name(COMMANDER)
        mana = [a for a in card.abilities if a.is_mana_ability]
        assert len(mana) == 1 and mana[0].mana_restriction is not None


class TestTheMeldPairShips:
    def test_gisela_names_her_partner_and_result(self):
        """Gisela is the deck's one meld card, and the first in the pool. A Gisela
        whose `melds_with` / `melds_into` dangled would load as a 4/3 whose end-step
        trigger raises the first time it fires."""
        registry = default_registry().registry
        gisela = registry.by_name("Gisela, the Broken Blade")
        assert gisela is not None
        assert registry.get(gisela.melds_with).name == "Bruna, the Fading Light"
        assert registry.get(gisela.melds_into).name == "Brisela, Voice of Nightmares"


class TestTheManaBaseIsReal:
    def test_every_land_makes_mana_or_does_something(self, report):
        """Emeria, the Sky Ruin reanimates, Bonders' Enclave draws, Three Tree City
        counts a creature type, Seraph Sanctuary gains life; any of them generated
        as an inert permanent leaves a deck that looks like 37 lands and plays like
        fewer."""
        assert report.lands == 37
        assert report.lands_inert == 0
