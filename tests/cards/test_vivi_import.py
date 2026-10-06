"""A spellslinger list, every card engine-native -- the pasted-link guarantee.

**Vivi Ornitier** leads "The Black Mage Arrives" (`moxfield.com/decks/0kx56Ml7Bkavzg-6awjieg`),
an Izzet storm deck: Vivi taps for mana and grows on every noncreature spell, and
the rest is magecraft, copies, rituals and the cards that cast spells for free.

It started at **30 of 83 distinct cards** native. The other 53 took twenty-six
engine capabilities -- magecraft, `double_triggers`, plot, granted rebound,
graveyard-cast permissions, "each of X targets" -- and the per-card behaviour is
pinned in `test_vivi_deck.py`. This file was the missing half: nothing asserted
that the *list* still imports native.

So it pins the same claim as its siblings: **every one of its 83 distinct cards
resolving `native`**, through the same `importer.import_deck` a pasted link goes
through. A card dropping out of `data/cards/auto/`, or an engine change
invalidating one, turns a `native` into a `partial` here rather than in somebody's
game.

Deliberately a *list* and not a `data/decks/*.deck.json`, for the reason the Lucy pin
gives: the deliverable is card-level support reached through the importer, so the test
asserts what the importer says.
"""

from __future__ import annotations

import pytest

from automtg.cards.images import load_index
from automtg.cards.importer import import_deck
from automtg.cards.moxfield import ParsedDeck
from automtg.cards.registry import default_registry

COMMANDER = "Vivi Ornitier"

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
DECK: tuple[tuple[str, int], ...] = (
    ("Abrade", 1),
    ("Aetherflux Reservoir", 1),
    ("Arcane Bombardment", 1),
    ("Arcane Denial", 1),
    ("Arcane Signet", 1),
    ("Archaeomancer", 1),
    ("Archmage Emeritus", 1),
    ("Archmage of Runes", 1),
    ("Balmor, Battlemage Captain", 1),
    ("Blasphemous Act", 1),
    ("Brainstorm", 1),
    ("Bria, Riptide Rogue", 1),
    ("Caldera Pyremaw", 1),
    ("Chandra's Ignition", 1),
    ("Chaos Warp", 1),
    ("Command Tower", 1),
    ("Crackle with Power", 1),
    ("Curiosity", 1),
    ("Electrodominance", 1),
    ("Electrostatic Infantry", 1),
    ("Epic Experiment", 1),
    ("Exalted Flamer of Tzeentch", 1),
    ("Exotic Orchard", 1),
    ("Expansion // Explosion", 1),
    ("Expressive Iteration", 1),
    ("Fire Magic", 1),
    ("Flame of Anor", 1),
    ("Flare of Denial", 1),
    ("Frantic Search", 1),
    ("Frostboil Snarl", 1),
    ("Gandalf's Sanction", 1),
    ("Gitaxian Probe", 1),
    ("Glamdring", 1),
    ("Harmonic Prodigy", 1),
    ("Haste Magic", 1),
    ("Ice Magic", 1),
    ("Island", 10),
    ("Izzet Boilerworks", 1),
    ("Jeska's Will", 1),
    ("Kitsa, Otterball Elite", 1),
    ("Lier, Disciple of the Drowned", 1),
    ("Lightning Bolt", 1),
    ("Lilah, Undefeated Slickshot", 1),
    ("Mana Geyser", 1),
    ("Mind Stone", 1),
    ("Mizzix's Mastery", 1),
    ("Mountain", 9),
    ("Myriad Landscape", 1),
    ("Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time", 1),
    ("Ophidian Eye", 1),
    ("Path of Ancestry", 1),
    ("Pinnacle Monk // Mystic Peak", 1),
    ("Ponder", 1),
    ("Pongify", 1),
    ("Reality Shift", 1),
    ("Reliquary Tower", 1),
    ("Restless Spire", 1),
    ("Rhystic Study", 1),
    ("Riptide Laboratory", 1),
    ("Riverglide Pathway // Lavaglide Pathway", 1),
    ("Season of Weaving", 1),
    ("Shivan Reef", 1),
    ("Sink into Stupor // Soporific Springs", 1),
    ("Sol Ring", 1),
    ("Solve the Equation", 1),
    ("Sprite Dragon", 1),
    ("Steam Vents", 1),
    ("Storm-Kiln Artist", 1),
    ("Stormcarved Coast", 1),
    ("Stormsplitter", 1),
    ("Swiftwater Cliffs", 1),
    ("Talisman of Creativity", 1),
    ("Temple of Epiphany", 1),
    ("The Emperor of Palamecia // The Lord Master of Hell", 1),
    ("The Ozolith", 1),
    ("Thought Vessel", 1),
    ("Urabrask // The Great Work", 1),
    ("Vandalblast", 1),
    ("Veyran, Voice of Duality", 1),
    ("Will of the Jeskai", 1),
    ("Windfall", 1),
    ("Winged Boots", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="0kx56Ml7Bkavzg-6awjieg",
        name="The Black Mage Arrives | Vivi Ornitier",
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
        assert len(report.cards) == 83

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
    def test_vivi_leads_the_deck(self, report):
        """A legendary creature, so 903.3 needs no sentence."""
        card = default_registry().registry.by_name(COMMANDER)
        assert card is not None and card.is_creature and card.is_legendary


class TestTheTwoFacedCardsHaveBothFaces:
    """Seven of the list's cards are two cards in one. A face whose link dangled
    would import as half a card -- a split card with one half, a land that is
    only ever a spell."""

    @pytest.mark.parametrize(
        "name",
        [
            "Expansion // Explosion",
            "Ojer Pakpatiq, Deepest Epoch // Temple of Cyclical Time",
            "Pinnacle Monk // Mystic Peak",
            "Riverglide Pathway // Lavaglide Pathway",
            "Sink into Stupor // Soporific Springs",
            "The Emperor of Palamecia // The Lord Master of Hell",
            "Urabrask // The Great Work",
        ],
    )
    def test_the_other_face_is_in_the_pool(self, name):
        registry = default_registry().registry
        card = registry.by_name(name)
        assert card is not None, f"{name} is not in the pool"
        other = card.back_face or card.second_face
        assert other is not None and registry.get(other) is not None


class TestTheManaBaseIsReal:
    def test_every_land_makes_mana_or_does_something(self, report):
        """A storm deck counts mana before it counts anything else, so a land
        generated as an inert permanent is a turn lost."""
        assert report.lands_inert == 0
