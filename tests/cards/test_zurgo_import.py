"""The Zurgo precon, pasted as a link, every card engine-native.

`data/decks/zurgo_stormrender.deck.json` is played straight from the
registry, so nothing about it ever went through `importer.import_deck` -- the path
a pasted Moxfield link takes. The imported siblings (`test_lander_commander_import.py`
and the rest) pin that path for a list somebody plays; this pins it for the list
the engine ships.

The deck file names cards by id, so the list here is derived from it rather than
retyped: the registry turns each id into the printed name a Moxfield export would
carry, and the importer has to resolve that name back to the same card. A card
whose name and id drifted apart, or one superseded into `data/cards/auto/` that
lost a face on the way, turns a `native` into a `partial` here.
"""

from __future__ import annotations

import json

import pytest

from automtg.cards.images import load_index
from automtg.cards.importer import import_deck
from automtg.cards.moxfield import ParsedDeck
from automtg.cards.registry import data_dir, default_registry

DECK_FILE = data_dir() / "decks" / "zurgo_stormrender.deck.json"

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


def deck_file() -> dict:
    return json.loads(DECK_FILE.read_text(encoding="utf-8"))


def deck_ids() -> set[str]:
    """Every distinct id the deck file names, commander included."""
    raw = deck_file()
    return {entry["id"] for entry in raw["cards"]} | set(raw["commanders"])


@pytest.fixture(scope="module")
def report():
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    registry = default_registry().registry
    raw = deck_file()
    deck = ParsedDeck(
        public_id=raw["id"],
        name=raw["name"],
        format="commander",
        commanders=tuple(registry.get(cid).name for cid in raw["commanders"]),
        cards=tuple(
            (registry.get(entry["id"]).name, entry["qty"])
            for entry in raw["cards"]
            if entry["id"] not in raw["commanders"]
        ),
    )
    return import_deck(deck, registry, load_index(), dry_run=True)


class TestEveryCardIsNative:
    def test_the_list_is_a_hundred_cards(self, report):
        """Asserted first: a dropped card would leave every other check green."""
        assert report.total == 100
        assert len(report.cards) == len(deck_ids())

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

    def test_every_name_resolves_to_the_id_the_deck_file_names(self, report):
        """The round trip: id -> printed name -> the importer's id."""
        assert {c.card_id for c in report.cards} == deck_ids()


class TestTheManaBaseIsReal:
    def test_every_land_makes_mana_or_does_something(self, report):
        assert report.lands_inert == 0
