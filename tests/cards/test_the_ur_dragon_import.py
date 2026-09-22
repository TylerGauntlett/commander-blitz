"""One real decklist, every card engine-native -- the pasted-link guarantee.

`docs/deck-import.md` makes a promise about a Moxfield link: every card is on the
board with its real name, art, cost, types and stats, and the ones nobody
implemented keep their printed text but do nothing. The honest version of that
promise is a number, and this file is the number for a third real list.

A five-colour Dragon deck built around The Ur-Dragon, imported through the same
`importer.import_deck` a pasted link goes through, with **every one of its 100
distinct cards resolving `native`** -- the engine's own rules, not a proxy.

It started at **40** of 100. The rest took ten authoring waves and **twenty-seven
engine capabilities**, each its own commit, including a battles subsystem
`docs/rules-coverage.md` had listed as deliberately out.

This deck is a harder shape than the two before it. A 99-card list is 99 chances
for one sentence nobody implemented; this one is 100 *distinct* cards -- no
`("Forest", 25)` line doing a quarter of the work -- so every entry below had to
be earned separately.

This file is what stops that quietly rotting: a card dropping out of
`data/cards/auto/` or an engine change invalidating one turns a `native` into a
`partial` here, on a list somebody actually plays, rather than in a game.

The arithmetic is asserted first and deliberately: if a name were dropped from
the tuple below, every other assertion here would still pass, and the count is
the only thing that would notice.

**The list is pinned, not fetched.** It is a snapshot of the Moxfield deck as it
stood when this was written, and that is the point: the deck is live and was
edited *during* the import that produced it -- Sylvia Brightspear went out and
Kinnan, Bonder Prodigy came in, which is why Sylvia is in `data/cards/auto/` and
not in the tuple below. A later edit upstream should fail this file and be
re-imported deliberately, not silently change what the test claims.

Deliberately a *list* and not a `data/decks/*.deck.json`, for
`test_lucy_maclean_import.py`'s reason: the deliverable was card-level support
reached through the importer, so the test asserts what the importer says rather
than what a committed deck file would.
"""

from __future__ import annotations

import pytest

from automtg.cards.images import load_index
from automtg.cards.importer import import_deck
from automtg.cards.moxfield import ParsedDeck
from automtg.cards.registry import default_registry

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
COMMANDER = "The Ur-Dragon"
DECK: tuple[tuple[str, int], ...] = (
    ("Ancient Copper Dragon", 1),
    ("Ancient Gold Dragon", 1),
    ("Arcane Signet", 1),
    ("Arena of Glory", 1),
    ("Arid Mesa", 1),
    ("Avatar's Wrath", 1),
    ("Badlands", 1),
    ("Bayou", 1),
    ("Birds of Paradise", 1),
    ("Bloodstained Mire", 1),
    ("Bloom Tender", 1),
    ("Bonehoard Dracosaur", 1),
    ("Boseiju, Who Endures", 1),
    ("Cavern of Souls", 1),
    ("Cavern-Hoard Dragon", 1),
    ("Chromatic Orrery", 1),
    ("Chrome Mox", 1),
    ("City of Brass", 1),
    ("Command Tower", 1),
    ("Crux of Fate", 1),
    ("Delighted Halfling", 1),
    ("Demonic Tutor", 1),
    ("Dracogenesis", 1),
    ("Draconic Visitor", 1),
    ("Dragon Tempest", 1),
    ("Dragonhawk, Fate's Tempest", 1),
    ("Dragonlord Dromoka", 1),
    ("Dragonlord Kolaghan", 1),
    ("Exotic Orchard", 1),
    ("Fellwar Stone", 1),
    ("Firdoch Core", 1),
    ("Flooded Strand", 1),
    ("Forbidden Orchard", 1),
    ("Ganax, Astral Hunter", 1),
    ("Gleaming Splendor", 1),
    ("Goldlust Triad", 1),
    ("Goldspan Dragon", 1),
    ("Helga, Skittish Seer", 1),
    ("Hellkite Courser", 1),
    ("Horizon of Progress", 1),
    ("Ignoble Hierarch", 1),
    ("Ketria Triome", 1),
    ("Kinnan, Bonder Prodigy", 1),
    ("Kiora, Behemoth Beckoner", 1),
    ("Klauth, Unrivaled Ancient", 1),
    ("Korvold, Fae-Cursed King", 1),
    ("Lathliss, Dragon Queen", 1),
    ("Maelstrom of the Spirit Dragon", 1),
    ("Majestic Genesis", 1),
    ("Mana Confluence", 1),
    ("Mana Vault", 1),
    ("Marang River Regent // Coil and Catch", 1),
    ("Marsh Flats", 1),
    ("Miirym, Sentinel Wyrm", 1),
    ("Misty Rainforest", 1),
    ("Mountain", 1),
    ("Mox Diamond", 1),
    ("Neriv, Heart of the Storm", 1),
    ("Noble Hierarch", 1),
    ("Old Gnawbone", 1),
    ("Plateau", 1),
    ("Polluted Delta", 1),
    ("Reflecting Pool", 1),
    ("Rhythm of the Wild", 1),
    ("Roaming Throne", 1),
    ("Savai Triome", 1),
    ("Savannah", 1),
    ("Scalding Tarn", 1),
    ("Scourge of Valkas", 1),
    ("Scrubland", 1),
    ("Selvala, Heart of the Wilds", 1),
    ("Smaug the Magnificent", 1),
    ("Smaug, Wicked Worm", 1),
    ("Smothering Tithe", 1),
    ("Smuggler's Surprise", 1),
    ("Sol Ring", 1),
    ("Steely Resolve", 1),
    ("Stubborn Denial", 1),
    ("Swan Song", 1),
    ("Taiga", 1),
    ("Tannuk, Steadfast Second", 1),
    ("Teferi's Protection", 1),
    ("Temur Ascendancy", 1),
    ("Temur Battlecrier", 1),
    ("Terror of the Peaks", 1),
    ("The One Ring", 1),
    ("Tiamat", 1),
    ("Tropical Island", 1),
    ("Tundra", 1),
    ("Twinflame Tyrant", 1),
    ("Underground Sea", 1),
    ("Up the Beanstalk", 1),
    ("Ureni of the Unwritten", 1),
    ("Verdant Catacombs", 1),
    ("Volcanic Island", 1),
    ("Windswept Heath", 1),
    ("Wooded Foothills", 1),
    ("Zagoth Triome", 1),
    ("Zurgo and Ojutai", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="otndvxb8bkqlpk_kanurka",
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

        `total` and `distinct` are equal here and that is not a coincidence:
        the list runs a singleton mana base, one Mountain and no other repeat,
        so there is no quantity above 1 anywhere in the tuple.
        """
        assert report.total == 100
        assert len(report.cards) == 100

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
        deck that looks like 35 lands and plays like 25. `lands_inert` counts
        the ones doing nothing at all.

        This one started the import with an inert land: Reflecting Pool, whose
        "any type that a land you control could produce" the generator refused
        rather than approximate as "any colour", because that version cannot
        tap off a Wastes. It took a capability, not a fix here.
        """
        assert report.lands == 35
        assert report.lands_inert == 0

    def test_ten_lands_make_no_mana_of_their_own_and_that_is_correct(self, report):
        """`producing` is ten short of `lands`, and every one is a fetchland.

        Arid Mesa and its nine siblings sacrifice themselves to search; they
        have never tapped for mana in their lives. The row above is what would
        catch a land that is inert by *accident*, which is a different thing
        from one that is inert by printing.
        """
        assert report.lands_producing_mana == 25
