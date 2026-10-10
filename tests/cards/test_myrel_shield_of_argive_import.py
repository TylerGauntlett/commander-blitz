"""A second real decklist, every card engine-native — the pasted-link guarantee.

`tests/cards/test_lucy_maclean_import.py` pinned the first one, and this is the
second, on a list built around a different axis. Lucy MacLean is a token deck
that wins by going wide; **Myrel, Shield of Argive** is a *Soldier* deck that
wins by going wide and then doing it again — Cathars' Crusade, Mondrak, Ocelot
Pride and Moonshaker Cavalry all multiply the same board — and it carries a
control shell that the first list had nothing like: Armageddon, Winter Orb,
Teferi's Protection, Angel's Grace, Approach of the Second Sun, Rest in Peace.

That second half is the reason this file is worth having rather than being more
of the same. It started at **37 of 74 distinct cards** native, and the half that
did not resolve was not a long tail of token variants — it was the deck's whole
strategy: prohibitions ("players can't cast spells", "you can't lose the game"),
replacement effects that reach every zone, alternate win conditions, an untap
restriction, and copying an ability on the stack. Two of those were rules
subsystems the engine had recorded as deliberately unbuilt.

So this file pins the same claim as its Lucy sibling for a list that exercises a
different third of the engine: **every one of its 74 distinct cards resolving
`native`**, through the same `importer.import_deck` a pasted link goes through.
A card dropping out of `data/cards/auto/`, or an engine change invalidating one,
turns a `native` into a `partial` here rather than in somebody's game.

Deliberately a *list* and not a `data/decks/*.deck.json`, for the same reason the
Lucy pin is: the deliverable was card-level support reached through the importer,
so the test asserts what the importer says rather than what a committed deck file
would.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry

COMMANDER = "Myrel, Shield of Argive"

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
DECK: tuple[tuple[str, int], ...] = (
    ("Akroma's Will", 1),
    ("Anafenza, Unyielding Lineage", 1),
    ("Angel's Grace", 1),
    ("Angelic Aberration", 1),
    ("Approach of the Second Sun", 1),
    ("Arcane Signet", 1),
    ("Archaeomancer's Map", 1),
    ("Archetype of Courage", 1),
    ("Armageddon", 1),
    ("Authority of the Consuls", 1),
    ("Ballyrush Banneret", 1),
    ("Bastion Protector", 1),
    ("Captain of the Watch", 1),
    ("Castle Ardenvale", 1),
    ("Cathar Commando", 1),
    ("Cathars' Crusade", 1),
    ("Commander's Sphere", 1),
    ("Court Street Denizen", 1),
    ("Daru Warchief", 1),
    ("Day of Judgment", 1),
    ("Decree of Justice", 1),
    ("Esgaroth Garrison", 1),
    ("Exalted Sunborn", 1),
    ("Firemane Commando", 1),
    ("Generous Gift", 1),
    ("Gleaming Splendor", 1),
    ("Goldnight Commander", 1),
    ("Haliya, Guided by Light", 1),
    ("Idyllic Grange", 1),
    ("Intangible Virtue", 1),
    ("Keeper of the Accord", 1),
    ("Kinbinding", 1),
    ("Lightning Greaves", 1),
    ("Marble Diamond", 1),
    ("Martial Coup", 1),
    ("Master of Ceremonies", 1),
    ("Memorial to Glory", 1),
    ("Mind Stone", 1),
    ("Mondrak, Glory Dominus", 1),
    ("Moogles' Valor", 1),
    ("Moonshaker Cavalry", 1),
    ("Myriad Landscape", 1),
    ("Ocelot Pride", 1),
    ("Odric, Lunarch Marshal", 1),
    ("Odric, Master Tactician", 1),
    ("Path of Ancestry", 1),
    ("Pearl Medallion", 1),
    ("Peter Parker's Camera", 1),
    ("Plains", 27),
    ("Prava of the Steel Legion", 1),
    ("Preeminent Captain", 1),
    ("Recruitment Officer", 1),
    ("Reprieve", 1),
    ("Rescue Retriever", 1),
    ("Resolute Reinforcements", 1),
    ("Rest in Peace", 1),
    ("Rogue's Passage", 1),
    ("Secluded Steppe", 1),
    ("Sentinel Totem", 1),
    ("Skullclamp", 1),
    ("Sol Ring", 1),
    ("Soul Warden", 1),
    ("Swords to Plowshares", 1),
    ("Teferi's Protection", 1),
    ("Terrain Generator", 1),
    ("Thalia, Heretic Cathar", 1),
    ("The Eagles Are Coming!", 1),
    ("Unbreakable Formation", 1),
    ("Valiant Veteran", 1),
    ("Wayfarer's Bauble", 1),
    ("Windbrisk Heights", 1),
    ("Winter Orb", 1),
    ("Worn Powerstone", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run — it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="myrelshieldofargive",
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
        assert len(report.cards) == 74

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

        This deck's mana base is most of the risk: Castle Ardenvale, Memorial to
        Glory and Windbrisk Heights are lands whose whole point is a second
        ability, Myriad Landscape and Terrain Generator fetch, and Idyllic Grange
        and Secluded Steppe each carry a rider. Any of them generated as an inert
        permanent leaves a deck that looks like 36 lands and plays like 30.
        """
        assert report.lands == 36
        assert report.lands_inert == 0
