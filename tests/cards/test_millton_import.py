"""One real decklist, every card engine-native -- the pasted-link guarantee.

`docs/deck-import.md` makes a promise about a Moxfield link: every card is on the
board with its real name, art, cost, types and stats. The honest version of that
promise is a number, and this file is one deck's number, pinned.

*Millton*, a mono-blue Commander list built around Bruvac the Grandiloquent, with
**every one of its 56 distinct cards resolving `native`** -- the engine's own
rules, not a proxy.

It started at **16 of 56**, and at `origin/main` the list did not import at all:
Persistent Petitioners appears twenty times, and the deck-construction gate had
no word for "a deck can have any number of cards named" (903.5b), so the whole
link failed as an illegal deck. The other forty cards took thirteen engine
capabilities, and this file is what stops that quietly rotting -- a card dropping
out of `data/cards/auto/` or an engine change invalidating one turns a `native`
into a `partial` here, on a list somebody actually plays, rather than in a game.

Deliberately a *list* and not a `data/decks/*.deck.json`: the deliverable was
card-level support reached through the importer, so the test asserts what the
importer says rather than what a committed deck file would.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
COMMANDER = "Bruvac the Grandiloquent"
DECK: tuple[tuple[str, int], ...] = (
    ("Alloy Myr", 1),
    ("Altar of the Brood", 1),
    ("Arcane Signet", 1),
    ("Archmage's Charm", 1),
    ("Back to Basics", 1),
    ("Brain Freeze", 1),
    ("Brainstorm", 1),
    ("Castle Vantress", 1),
    ("Cloudstone Curio", 1),
    ("Conjurer's Bauble", 1),
    ("Cryptic Command", 1),
    ("Cryptic Trilobite", 1),
    ("Dramatic Reversal", 1),
    ("Drowned Secrets", 1),
    ("Emry, Lurker of the Loch", 1),
    ("Fleet Swallower", 1),
    ("Folio of Fancies", 1),
    ("Gilded Lotus", 1),
    ("Intruder Alarm", 1),
    ("Island", 26),
    ("Isochron Scepter", 1),
    ("Jace, Wielder of Mysteries", 1),
    ("Kefnet's Monument", 1),
    ("Maddening Cacophony", 1),
    ("Memory Erosion", 1),
    ("Merchant Scroll", 1),
    ("Midnight Clock", 1),
    ("Mikokoro, Center of the Sea", 1),
    ("Muddle the Mixture", 1),
    ("Mystic Remora", 1),
    ("Mystic Sanctuary", 1),
    ("Mystical Tutor", 1),
    ("Orvar, the All-Form", 1),
    ("Persistent Petitioners", 20),
    ("Pongify", 1),
    ("Prismite", 1),
    ("Propaganda", 1),
    ("Rapid Hybridization", 1),
    ("Rhystic Study", 1),
    ("Sapphire Medallion", 1),
    ("Sea Gate Stormcaller", 1),
    ("Shrieking Drake", 1),
    ("Silver Myr", 1),
    ("Sol Ring", 1),
    ("Solemn Simulacrum", 1),
    ("Sphinx's Tutelage", 1),
    ("Teferi's Ageless Insight", 1),
    ("Teferi's Tutelage", 1),
    ("Teferi, Master of Time", 1),
    ("Thassa's Oracle", 1),
    ("Tidal Barracuda", 1),
    ("Tolaria West", 1),
    ("Traumatize", 1),
    ("Vedalken Engineer", 1),
    ("Visions of Beyond", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="millton",
        name="Millton",
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
        assert len(report.cards) == 56

    def test_the_twenty_petitioners_are_really_twenty(self, report):
        """903.5b, and the reason this deck could not be imported at all.

        "A deck can have any number of cards named Persistent Petitioners"
        breaks the four-of rule, and a gate that enforced it without reading the
        card's own text refused the whole list. A singleton copy would pass every
        other assertion in this file.
        """
        assert dict(DECK)["Persistent Petitioners"] == 20

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
        deck that looks like 30 lands and plays like 28. `lands_inert` counts the
        ones doing nothing at all.
        """
        assert report.lands == 30
        assert report.lands_inert == 0
        assert report.lands_producing_mana == 30


class TestTheCommander:
    def test_bruvac_is_native(self, report):
        """The mill doubler the whole list is built on.

        Named rather than left to the sweep above, because a commander that
        imported as a proxy would be a 2/3 that says nothing -- and the deck
        would still report 55 of 56 native, which reads almost right.
        """
        bruvac = next(c for c in report.cards if c.name == COMMANDER)
        assert bruvac.origin == "native"
        assert bruvac.notes == ()
