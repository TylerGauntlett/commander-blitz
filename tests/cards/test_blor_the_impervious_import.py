"""One real decklist, every card engine-native -- the pasted-link guarantee.

`docs/deck-import.md` makes a promise about a Moxfield link: every card is on the
board with its real name, art, cost, types and stats, and the ones nobody
implemented keep their printed text but do nothing. The honest version of that
promise is a number, and this file is the number for a second real list.

A mono-green Commander deck built around Blor the Impervious, imported through
the same `importer.import_deck` a pasted link goes through, with **every one of
its 76 distinct cards resolving `native`** -- the engine's own rules, not a
proxy.

It started at **17** of 76, with 59 cards proxied and only 41 of the 100 playable
at all. The rest took one authoring wave and **thirty-four engine
capabilities**, each its own commit.

This file is what stops that quietly rotting: a card dropping out of
`data/cards/auto/` or an engine change invalidating one turns a `native` into a
`partial` here, on a list somebody actually plays, rather than in a game.

The arithmetic is asserted first and deliberately: if a name were dropped from
the tuple below, every other assertion here would still pass, and the count is
the only thing that would notice.

Deliberately a *list* and not a `data/decks/*.deck.json`, for
`test_lucy_maclean_import.py`'s reason: the deliverable was card-level support
reached through the importer, so the test asserts what the importer says rather
than what a committed deck file would.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
COMMANDER = "Blor the Impervious"
DECK: tuple[tuple[str, int], ...] = (
    ("Adaptive Omnitool", 1),
    ("Arbor Elf", 1),
    ("Archdruid's Charm", 1),
    ("Assault Suit", 1),
    ("Bala Ged Recovery // Bala Ged Sanctuary", 1),
    ("Basilisk Collar", 1),
    ("Bear Umbra", 1),
    ("Beast Within", 1),
    ("Berserk", 1),
    ("Bloodforged Battle-Axe", 1),
    ("Bone Sabres", 1),
    ("Boseiju, Who Endures", 1),
    ("Brass Knuckles", 1),
    ("Bridgeworks Battle // Tanglespan Bridgeworks", 1),
    ("Buried Ruin", 1),
    ("Buster Sword", 1),
    ("Cavern of Souls", 1),
    ("Commander's Plate", 1),
    ("Conqueror's Flail", 1),
    ("Creeping Renaissance", 1),
    ("Delighted Halfling", 1),
    ("Elvish Mystic", 1),
    ("Eternal Witness", 1),
    ("Excalibur, Sword of Eden", 1),
    ("Fanatic of Rhonas", 1),
    ("Forest", 25),
    ("Fyndhorn Elves", 1),
    ("Gemrazer", 1),
    ("Genji Glove", 1),
    ("Hammer of Nazahn", 1),
    ("High Score", 1),
    ("Hunter's Insight", 1),
    ("Hunter's Talent", 1),
    ("Inquisitor's Flail", 1),
    ("Inventors' Fair", 1),
    ("Keen Sense", 1),
    ("Krosan Grip", 1),
    ("Lavaspur Boots", 1),
    ("Legolas's Quick Reflexes", 1),
    ("Level Up", 1),
    ("Llanowar Elves", 1),
    ("Mask of Memory", 1),
    ("Masterwork of Ingenuity", 1),
    ("Mosswort Bridge", 1),
    ("Nature's Lore", 1),
    ("Nettlecyst", 1),
    ("Pip-Boy 3000", 1),
    ("Power Fist", 1),
    ("Ram Through", 1),
    ("Return of the Wildspeaker", 1),
    ("Rishkar's Expertise", 1),
    ("Sakura-Tribe Elder", 1),
    ("Selvala, Heart of the Wilds", 1),
    ("Shifting Woodland", 1),
    ("Silkguard", 1),
    ("Sixth Sense", 1),
    ("Sol Ring", 1),
    ("Song of the Dryads", 1),
    ("Staff of Titania", 1),
    ("Strip Mine", 1),
    ("Strong Back", 1),
    ("Sword of Fire and Ice", 1),
    ("Swordsman's Steel", 1),
    ("Sylvan Library", 1),
    ("Talon Gates of Madara", 1),
    ("Tanuki Transplanter", 1),
    ("The Irencrag", 1),
    ("The Mycosynth Gardens", 1),
    ("Three Visits", 1),
    ("Toski, Bearer of Secrets", 1),
    ("Ulvenwald Tracker", 1),
    ("Urza's Saga", 1),
    ("Utopia Sprawl", 1),
    ("Wild Growth", 1),
    ("Yavimaya, Cradle of Growth", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="blortheimpervious",
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
        assert len(report.cards) == 76

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

    def test_the_mana_base_is_the_one_the_list_asked_for(self, report):
        """Urza's Saga and Boseiju are lands that make no mana of their own, so
        `producing` is two short of `lands` here and that is correct rather than
        a defect -- the row above is what catches an inert one."""
        assert report.lands_producing_mana == 34
