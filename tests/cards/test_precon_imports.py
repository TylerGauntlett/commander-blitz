"""Every shipped precon, as its list would import: every card engine-native.

The import pin per deck that ADR 0024 asks for, written once for all of them:
a precon's deck file is the published list (``scripts/sync_precons.py
--write-deck``), so its names go back through the same `importer.import_deck`
a pasted link goes through, and every card must resolve ``native`` -- the
engine's own rules, never a proxy. A card dropping out of ``data/cards/`` or an
engine change invalidating one turns a ``native`` into a proxy here, on a list
Wizards sold, rather than in somebody's game.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import load_index
from commanderblitz.cards.importer import import_deck
from commanderblitz.cards.moxfield import ParsedDeck
from commanderblitz.cards.registry import default_registry
from tests.cards.test_deck_legality import PRECONS

pytestmark = pytest.mark.skipif(
    load_index() is None, reason="no card catalog; run scripts/build_card_index.py"
)


def _as_parsed(deck_id: str) -> ParsedDeck:
    data = default_registry()
    deck = data.decks[deck_id]
    name = data.registry.get
    return ParsedDeck(
        public_id=deck_id,
        name=deck.name,
        format="commander",
        commanders=tuple(name(c).name for c in deck.commanders),
        cards=tuple((name(card_id).name, qty) for card_id, qty in deck.cards),
    )


@pytest.fixture(scope="module", params=sorted(PRECONS))
def report(request):
    """The import, as a dry run -- it writes nothing to `data/generated/`."""
    return import_deck(
        _as_parsed(request.param), default_registry().registry, load_index(), dry_run=True
    )


class TestEveryCardIsNative:
    def test_the_list_is_a_hundred_cards(self, report):
        assert report.total == 100

    def test_every_card_resolves_native(self, report):
        proxied = sorted(c.name for c in report.cards if c.origin != "native")
        assert proxied == []

    def test_nothing_was_simplified(self, report):
        assert report.simplified == 0
