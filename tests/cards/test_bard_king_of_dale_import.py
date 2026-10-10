"""The Bard, King of Dale list, every card engine-native -- pinned.

Modelled on `test_lucy_maclean_import.py`, and the same promise: a pasted
Moxfield link for this deck imports through `importer.import_deck` with **every
one of its 97 distinct cards resolving `native`**.

It started at 48 of 97. What closed the rest is listed in the pull request that
added this file -- among it a per-caster spell ordinal, extra turns, token and
draw doubling, Station, Class levels, Strive and a token attacking a
planeswalker -- and this file is what stops any of it quietly rotting: a card
falling out of `data/cards/auto/` turns a `native` into a `partial` here.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
COMMANDER = "Bard, King of Dale"
DECK: tuple[tuple[str, int], ...] = (
    ("Abandoned Air Temple", 1),
    ("Adagia, Windswept Bastion", 1),
    ("Adarkar Wastes", 1),
    ("Adeline, Resplendent Cathar", 1),
    ("Alandra, Sky Dreamer", 1),
    ("Ancient Tomb", 1),
    ("Arcane Signet", 1),
    ("Archaeomancer's Map", 1),
    ("Arid Mesa", 1),
    ("Ashnod's Altar", 1),
    ("Austere Command", 1),
    ("Azorius Signet", 1),
    ("Bastion Protector", 1),
    ("Brainstorm", 1),
    ("Call the Coppercoats", 1),
    ("Caretaker's Talent", 1),
    ("Castle Ardenvale", 1),
    ("Cathars' Crusade", 1),
    ("Champion of Wits", 1),
    ("Chivalric Alliance", 1),
    ("Command Tower", 1),
    ("Consider", 1),
    ("Cut a Deal", 1),
    ("Cyclonic Rift", 1),
    ("Demolition Field", 1),
    ("Detective of the Month", 1),
    ("Eiganjo, Seat of the Empire", 1),
    ("Elesh Norn, Grand Cenobite", 1),
    ("Emrakul's Messenger", 1),
    ("Esper Sentinel", 1),
    ("Faerie Artisans", 1),
    ("Fellwar Stone", 1),
    ("Flawless Maneuver", 1),
    ("Flooded Strand", 1),
    ("Floodfarm Verge", 1),
    ("Frantic Search", 1),
    ("Generous Gift", 1),
    ("Gilded Lotus", 1),
    ("Glacial Fortress", 1),
    ("Hallowed Fountain", 1),
    ("Hermes, Overseer of Elpis", 1),
    ("Island", 2),
    ("Lightning Greaves", 1),
    ("Loran of the Third Path", 1),
    ("Luminarch Ascension", 1),
    ("Makindi Stampede // Makindi Mesas", 1),
    ("Mangara, the Diplomat", 1),
    ("Marsh Flats", 1),
    ("Meticulous Archive", 1),
    ("Minas Tirith", 1),
    ("Mind Stone", 1),
    ("Mischievous Mystic", 1),
    ("Misty Rainforest", 1),
    ("Monastery Mentor", 1),
    ("Moonshaker Cavalry", 1),
    ("Mystic Gate", 1),
    ("Nadir Kraken", 1),
    ("Nimbus Maze", 1),
    ("Opt", 1),
    ("Otawara, Soaring City", 1),
    ("Path to Exile", 1),
    ("Perch Protection", 1),
    ("Plains", 3),
    ("Polluted Delta", 1),
    ("Ponder", 1),
    ("Preordain", 1),
    ("Prince Imrahil the Fair", 1),
    ("Raise the Alarm", 1),
    ("Reliquary Tower", 1),
    ("Scalding Tarn", 1),
    ("Sea Gate Restoration // Sea Gate, Reborn", 1),
    ("Secret Rendezvous", 1),
    ("Shorikai, Genesis Engine", 1),
    ("Sicarian Infiltrator", 1),
    ("Sink into Stupor // Soporific Springs", 1),
    ("Skullclamp", 1),
    ("Smothering Tithe", 1),
    ("Sol Ring", 1),
    ("Swords to Plowshares", 1),
    ("Talisman of Progress", 1),
    ("Tataru Taru", 1),
    ("The Council of Four", 1),
    ("The Queen of Dale", 1),
    ("The Theorist, Jace Beleren", 1),
    ("Thopter Fabricator", 1),
    ("Thought Vessel", 1),
    ("Thran Dynamo", 1),
    ("Trouble in Pairs", 1),
    ("Tundra", 1),
    ("Urza's Saga", 1),
    ("Uthros, Titanic Godcore", 1),
    ("Voice of Victory", 1),
    ("Will of the Mardu", 1),
    ("Windswept Heath", 1),
    ("Witch Enchanter // Witch-Blessed Meadow", 1),
    ("Worn Powerstone", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run — it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="bardkingofdale",
        name=COMMANDER,
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
        assert len(report.cards) == 97

    def test_nothing_is_a_proxy(self, report):
        """The claim. `partial` means the printed text is inert."""
        not_native = sorted(c.name for c in report.cards if c.origin != "native")
        assert not_native == []

    def test_nothing_was_simplified(self, report):
        assert report.simplified == 0
        assert report.playable == 100

    def test_no_card_carries_a_note(self, report):
        """A note is the importer saying what it had to give up.

        `full` cards can carry none and `native` cards never generate at all, so
        an empty set here is the same claim as the row above, read off the other
        side of the report.
        """
        noted = {c.name: c.notes for c in report.cards if c.notes}
        assert noted == {}


class TestTheManaBaseIsReal:
    def test_every_land_makes_mana_or_does_something(self, report):
        """The hardest import defect to see from the board.

        A fetchland or creature-land generated as an inert permanent leaves a
        deck that looks like 32 lands and plays like 30. `lands_inert` counts
        the ones doing nothing at all.
        """
        assert report.lands == 32
        assert report.lands_inert == 0
