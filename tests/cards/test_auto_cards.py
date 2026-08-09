"""Re-verify every machine-authored card, every run.

`data/cards/auto/` is only worth having if its contents are *known* to work
rather than assumed to. A card was accepted because it cleared six gates at the
moment it was written; an engine change months later can quietly invalidate that,
and nothing about the card file would look different.

So the gates run again here, over everything committed, as part of the ordinary
suite. A card that stops passing is a card that has to come out.
"""

from __future__ import annotations

import json

import pytest

from automtg.cards.authoring import verify as V
from automtg.cards.authoring.queue import auto_cards_dir
from automtg.cards.registry import CardRegistry, data_dir


def _auto_payloads() -> list[dict]:
    out: list[dict] = []
    for path in sorted(auto_cards_dir().glob("*.cards.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        out.extend(raw.get("cards", []))
    return out


def _expectations() -> dict:
    path = auto_cards_dir() / "expectations.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


PAYLOADS = _auto_payloads()
CARD_IDS = sorted(c["id"] for c in PAYLOADS if "id" in c)


@pytest.fixture(scope="module")
def hand_written() -> CardRegistry:
    """The pool minus `auto/` -- what an authored card is verified against."""
    return CardRegistry.from_paths(sorted((data_dir() / "cards").glob("*.cards.json")))


@pytest.fixture(scope="module")
def by_id() -> dict:
    return {c["id"]: c for c in PAYLOADS if "id" in c}


@pytest.mark.skipif(not CARD_IDS, reason="no machine-authored cards yet")
class TestEveryAutoCardStillPasses:
    @pytest.mark.parametrize("card_id", CARD_IDS)
    def test_it_clears_every_gate(self, card_id, by_id, hand_written):
        expectation = _expectations().get(card_id, {})
        verdict = V.verify(by_id[card_id], expectation, hand_written)
        assert verdict.ok, str(verdict)

    def test_every_card_has_an_expectation(self, by_id):
        # Gate 5 enforces this at authoring time; this catches an expectation
        # deleted afterwards, which would leave a card nobody is checking.
        expectations = _expectations()
        missing = sorted(set(by_id) - set(expectations))
        assert missing == [], f"authored with no expectation: {missing[:10]}"

    def test_no_orphan_expectations(self, by_id):
        expectations = _expectations()
        orphans = sorted(set(expectations) - set(by_id))
        assert orphans == [], f"expectations for cards that are gone: {orphans[:10]}"


def test_the_auto_directory_is_wired_into_the_registry():
    """A card written here must actually reach a game.

    `CardRegistry.from_dir` globs `*.cards.json`; without `authored_card_paths`
    picking up the subdirectory, every card the pipeline writes would sit on disk
    doing nothing -- the exact failure the pipeline exists to fix.
    """
    from automtg.cards.registry import authored_card_paths

    paths = authored_card_paths()
    assert any(p.parent.name == "cards" for p in paths), "hand-written cards are not loaded"
    if CARD_IDS:
        assert any(p.parent.name == "auto" for p in paths), "auto/ is not loaded"
        registry = CardRegistry.from_dir()
        for card_id in CARD_IDS:
            assert card_id in registry
