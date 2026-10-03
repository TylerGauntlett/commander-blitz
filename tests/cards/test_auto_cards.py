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

#: The second entries of two-faced cards, by id -- both links. `back_face` is a
#: transforming card's other side and `second_face` is a modal DFC's, a split
#: half, an Adventure, or the spell half of a prepared creature; either way the
#: entry is not a card in its own right. A meld result (`melds_into`) is the
#: same: two permanents become it, and nobody owns a copy (701.37). It
#: is never drawn or shuffled into a deck on its own, it has no expectation --
#: there is no position to cast it in by itself -- and it is checked *through*
#: its front, which names it as a companion below.
BACK_FACE_IDS = frozenset(
    str(c[key])
    for c in PAYLOADS
    for key in ("back_face", "second_face", "prepared_face", "melds_into")
    if c.get(key)
)

CARD_IDS = sorted(
    c["id"] for c in PAYLOADS if "id" in c and c["id"] not in BACK_FACE_IDS
)


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
        payload = by_id[card_id]
        expectation = _expectations().get(card_id, {})
        # A transforming card is two entries and one object, so its back face
        # travels with it -- exactly as the answer file that produced it did.
        # Verified apart, the front fails the registry gate on a `back_face`
        # pointing at a card that is not in the pool.
        companions = [
            by_id[str(payload[key])]
            for key in ("back_face", "second_face", "prepared_face", "melds_into")
            if payload.get(key) and str(payload[key]) in by_id
        ]
        # A meld half names its partner, which is a card of its own: verified
        # through its own answer, and brought into the pool here only when it
        # is machine-authored too -- exactly as `--collect` brings it in.
        partner = payload.get("melds_with")
        partners = (
            [by_id[partner]] if partner and partner in by_id and partner not in hand_written else []
        )
        verdict = V.verify(
            payload, expectation, hand_written, companions=companions, partners=partners
        )
        assert verdict.ok, str(verdict)

    def test_every_card_has_an_expectation(self, by_id):
        # Gate 5 enforces this at authoring time; this catches an expectation
        # deleted afterwards, which would leave a card nobody is checking.
        #
        # Back faces are exempt and have to be: there is no position in which to
        # cast one, so there is nothing an expectation could asserted about it.
        # What it does is proven through its front.
        expectations = _expectations()
        missing = sorted(set(by_id) - set(expectations) - BACK_FACE_IDS)
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
