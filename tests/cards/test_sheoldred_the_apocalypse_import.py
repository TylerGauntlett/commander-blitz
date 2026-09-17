"""The Sheoldred, the Apocalypse "Draw Death" list, every card engine-native -- pinned.

Modelled on `test_lucy_maclean_import.py`, and the same promise: a pasted
Moxfield link for this deck imports through `importer.import_deck` with **every
one of its 74 distinct cards resolving `native`**.

It started at 24 of 74. What closed the rest is listed in the pull request that
added this file -- among it emblems, Role tokens, life-gain doubling and
prohibition, the life lost this way, extort, a triggered mana ability, paying
{B} with life, casting exiled cards with any colour of mana, halving, and an
{X} paid on resolution -- and this file is what stops any of it quietly
rotting: a card falling out of `data/cards/auto/` turns a `native` into a
`partial` here.
"""

from __future__ import annotations

import pytest

from automtg.cards.images import load_index
from automtg.cards.importer import import_deck
from automtg.cards.moxfield import ParsedDeck
from automtg.cards.registry import default_registry

#: Names exactly as printed, since `importer` reconciles against the catalog by
#: name and a typo here would be indistinguishable from a missing card.
COMMANDER = "Sheoldred, the Apocalypse"
DECK: tuple[tuple[str, int], ...] = (
    ("Alhammarret's Archive", 1),
    ("Arcane Signet", 1),
    ("Baleful Mastery", 1),
    ("Blood Pact", 1),
    ("Bloodgift Demon", 1),
    ("Bojuka Bog", 1),
    ("Cabal Stronghold", 1),
    ("Charcoal Diamond", 1),
    ("Commander's Plate", 1),
    ("Crypt Ghast", 1),
    ("Damnable Pact", 1),
    ("Dark Deal", 1),
    ("Dark Ritual", 1),
    ("Decanter of Endless Water", 1),
    ("Defile", 1),
    ("Demolition Field", 1),
    ("Dismember", 1),
    ("Dread Presence", 1),
    ("Elder Brain", 1),
    ("Eldritch Pact", 1),
    ("Erebos, God of the Dead", 1),
    ("Fate Unraveler", 1),
    ("Feed the Swarm", 1),
    ("Feign Death", 1),
    ("Font of Mythos", 1),
    ("Geier Reach Sanitarium", 1),
    ("Ghost Quarter", 1),
    ("Gixian Puppeteer", 1),
    ("Gray Merchant of Asphodel", 1),
    ("Greed", 1),
    ("Howling Mine", 1),
    ("Infernal Grasp", 1),
    ("Jet Medallion", 1),
    ("K'rrik, Son of Yawgmoth", 1),
    ("Lightning Greaves", 1),
    ("Malakir Rebirth // Malakir Mire", 1),
    ("Marauding Blight-Priest", 1),
    ("Master of the Feast", 1),
    ("Mikokoro, Center of the Sea", 1),
    ("Mind Stone", 1),
    ("Mutilate", 1),
    ("Myriad Landscape", 1),
    ("Night's Whisper", 1),
    ("Not Dead After All", 1),
    ("Ob Nixilis Reignited", 1),
    ("Ob Nixilis, the Hate-Twisted", 1),
    ("Otherworld Atlas", 1),
    ("Peer into the Abyss", 1),
    ("Phyrexian Arena", 1),
    ("Psychosis Crawler", 1),
    ("Rankle, Master of Pranks", 1),
    ("Read the Bones", 1),
    ("Reliquary Tower", 1),
    ("Sanguine Bond", 1),
    ("Scrawling Crawler", 1),
    ("Seizan, Perverter of Truth", 1),
    ("Sheoldred's Edict", 1),
    ("Sign in Blood", 1),
    ("Snuff Out", 1),
    ("Sol Ring", 1),
    ("Solemn Simulacrum", 1),
    ("Swamp", 27),
    ("Swiftfoot Boots", 1),
    ("Teferi's Puzzle Box", 1),
    ("Temple Bell", 1),
    ("Thought Vessel", 1),
    ("Toxic Deluge", 1),
    ("Underworld Dreams", 1),
    ("Undying Malice", 1),
    ("Vilis, Broker of Blood", 1),
    ("Vito, Thorn of the Dusk Rose", 1),
    ("Well of Lost Dreams", 1),
    ("Witch of the Moors", 1),
)

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run — it writes nothing to `data/generated/`."""
    deck = ParsedDeck(
        public_id="sheoldredtheapocalypse",
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

        A fetchland or creature-land generated as an inert permanent leaves a
        deck that looks like 32 lands and plays like 30. `lands_inert` counts
        the ones doing nothing at all.
        """
        assert report.lands == 35
        assert report.lands_inert == 0
