"""One real decklist, every card engine-native — the pasted-link guarantee.

`docs/deck-import.md` makes a promise about a Moxfield link: every card is on the
board with its real name, art, cost, types and stats, and the ones nobody
implemented keep their printed text but do nothing. The honest version of that
promise is a number, and for a long time the number was bad — a real imported
deck had 41 of its 100 cards doing nothing.

This is the counter-example, pinned. A mono-white Commander list built around
Lucy MacLean, Positively Armed, imported through the same `importer.import_deck`
a pasted link goes through, with **every one of its 70 distinct cards resolving
`native`** — the engine's own rules, not a proxy.

It started at 16 of 70. The other 54 took fourteen token definitions and
twenty-four engine capabilities, and this file is what stops that quietly
rotting: a card dropping out of `data/cards/auto/` or an engine change
invalidating one turns a `native` into a `partial` here, on a list somebody
actually plays, rather than in a game.

Deliberately a *list* and not a `data/decks/*.deck.json`: the deliverable was
card-level support reached through the importer, so the test asserts what the
importer says rather than what a committed deck file would.
"""

from __future__ import annotations

import pytest

from automtg.cards.images import load_index
from automtg.cards.importer import import_deck
from automtg.cards.moxfield import ParsedDeck
from automtg.cards.registry import default_registry

COMMANDER = "Lucy MacLean, Positively Armed"

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
DECK: tuple[tuple[str, int], ...] = (
    ("Academy Manufactor", 1),
    ("Ainok Strike Leader", 1),
    ("Arcane Signet", 1),
    ("Bovine Intervention", 1),
    ("Brave the Elements", 1),
    ("Captain of the Watch", 1),
    ("Castle Ardenvale", 1),
    ("Champions from Beyond", 1),
    ("Charisma Bobblehead", 1),
    ("Combat Calligrapher", 1),
    ("Commander Sofia Daguerre", 1),
    ("Crisis of Conscience", 1),
    ("Diamond City", 1),
    ("Divine Visitation", 1),
    ("Emergency Eject", 1),
    ("Endurance Bobblehead", 1),
    ("Entrapment Maneuver", 1),
    ("Excavation Technique", 1),
    ("Fateful Absence", 1),
    ("Felidar Retreat", 1),
    ("Fellwar Stone", 1),
    ("Gary Clone", 1),
    ("Get Lost", 1),
    ("Halo Fountain", 1),
    ("Heraldic Banner", 1),
    ("Hero of Bladehold", 1),
    ("Hour of Reckoning", 1),
    ("Inspiring Leader", 1),
    ("Intangible Virtue", 1),
    ("Intelligence Bobblehead", 1),
    ("Keeper of the Accord", 1),
    ("Kinbinding", 1),
    ("Lightning Greaves", 1),
    ("Lossarnach Captain", 1),
    ("Luck Bobblehead", 1),
    ("Marble Diamond", 1),
    ("Marshal's Anthem", 1),
    ("Martial Coup", 1),
    ("Memorial to Glory", 1),
    ("Mind Stone", 1),
    ("Oketra's Monument", 1),
    ("Oltec Matterweaver", 1),
    ("Overencumbered", 1),
    ("Parting Gust", 1),
    ("Pearl Medallion", 1),
    ("Perception Bobblehead", 1),
    ("Pip-Boy 3000", 1),
    ("Plains", 31),
    ("Prava of the Steel Legion", 1),
    ("Pre-War Formalwear", 1),
    ("Rabble Rousing", 1),
    ("Reliquary Tower", 1),
    ("Reprieve", 1),
    ("Secure the Wastes", 1),
    ("Securitron Squadron", 1),
    ("Silverquill Lecturer", 1),
    ("Sol Ring", 1),
    ("Soul Foundry", 1),
    ("Strength Bobblehead", 1),
    ("Stroke of Midnight", 1),
    ("Swiftfoot Boots", 1),
    ("Swords to Plowshares", 1),
    ("Thought Vessel", 1),
    ("Toby, Beastie Befriender", 1),
    ("Valorous Stance", 1),
    ("Vault 101: Birthday Party", 1),
    ("Wedding Ring", 1),
    ("Windbrisk Heights", 1),
    ("Yes Man, Personal Securitron", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run — it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="lucymaclean",
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
        assert len(report.cards) == 70

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
        deck that looks like 36 lands and plays like 34. `lands_inert` counts
        the ones doing nothing at all.
        """
        assert report.lands == 36
        assert report.lands_inert == 0
