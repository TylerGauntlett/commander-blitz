"""``scripts/backfill_art.py``: the crawl that fills the art store.

The property under test is the one ADR 0021 leans on: the crawl is run on a
schedule, capped, and can be killed at any point, so it must be resumable and
must never fetch a file twice.  The fetcher is injected throughout; nothing
here touches the network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commanderblitz.cards.images import STORE_STATE, STORE_UNAVAILABLE, store_path
from commanderblitz.cards.registry import default_registry
from commanderblitz.server.art import ArtStore

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backfill_art.py"

JPEG = b"\xff\xd8\xff\xd9"


def _id(n: int) -> str:
    return f"{n:08x}-0000-0000-0000-{n:012x}"


@pytest.fixture(scope="module")
def bf():
    spec = importlib.util.spec_from_file_location("backfill_art", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("backfill_art", module)
    spec.loader.exec_module(module)
    return module


class Interrupted(BaseException):
    """A kill, as the run sees it: not an error the crawl may swallow."""


class Fetcher:
    def __init__(self, *, missing=(), interrupt_after=None):
        self.calls: list[str] = []
        self.missing = set(missing)
        self.interrupt_after = interrupt_after

    def __call__(self, url: str) -> bytes | None:
        if self.interrupt_after is not None and len(self.calls) == self.interrupt_after:
            raise Interrupted
        self.calls.append(url)
        if any(m in url for m in self.missing):
            return None
        return JPEG


def _run(bf, faces, store, fetcher, **kw):
    def committed(face):
        return store_path(store, face.scryfall_id, back=face.back).is_file()

    return bf.backfill(faces, store, committed=committed, fetch=fetcher, delay=0, **kw)


class TestResumable:
    def test_an_interrupted_run_resumes_and_fetches_nothing_twice(self, bf, tmp_path):
        faces = [bf.Face(_id(n)) for n in range(6)] + [bf.Face(_id(1), back=True)]
        first = Fetcher(interrupt_after=3)
        with pytest.raises(Interrupted):
            _run(bf, faces, tmp_path, first)
        second = Fetcher()
        report = _run(bf, faces, tmp_path, second)

        assert len(first.calls) == 3
        assert not set(first.calls) & set(second.calls), "a file was fetched twice"
        assert len(first.calls) + len(second.calls) == len(faces)
        assert report.held == len(faces)
        for face in faces:
            assert store_path(tmp_path, face.scryfall_id, back=face.back).read_bytes() == JPEG
        assert not list(tmp_path.glob("*/*.part"))

    def test_a_third_run_fetches_nothing(self, bf, tmp_path):
        faces = [bf.Face(_id(n)) for n in range(3)]
        _run(bf, faces, tmp_path, Fetcher())
        again = Fetcher()
        assert _run(bf, faces, tmp_path, again).fetched == 0
        assert again.calls == []

    def test_a_printing_the_cdn_lacks_is_recorded_and_not_asked_again(self, bf, tmp_path):
        faces = [bf.Face(_id(1)), bf.Face(_id(2))]
        first = Fetcher(missing={_id(2)})
        _run(bf, faces, tmp_path, first)
        assert json.loads((tmp_path / STORE_UNAVAILABLE).read_text()) == [f"{_id(2)}.jpg"]
        second = Fetcher()
        _run(bf, faces, tmp_path, second)
        assert second.calls == []

    def test_what_an_interrupted_run_learned_is_kept(self, bf, tmp_path):
        faces = [bf.Face(_id(n)) for n in range(4)]
        with pytest.raises(Interrupted):
            _run(bf, faces, tmp_path, Fetcher(missing={_id(0)}, interrupt_after=2))
        assert f"{_id(0)}.jpg" in json.loads((tmp_path / STORE_UNAVAILABLE).read_text())

    def test_a_transient_failure_is_retried_next_run(self, bf, tmp_path):
        def flaky(url):
            raise TimeoutError("slow")

        report = _run(bf, [bf.Face(_id(1))], tmp_path, flaky)
        assert report.failed and report.fetched == 0
        assert json.loads((tmp_path / STORE_UNAVAILABLE).read_text()) == []
        assert _run(bf, [bf.Face(_id(1))], tmp_path, Fetcher()).fetched == 1

    def test_the_limit_caps_a_run(self, bf, tmp_path):
        faces = [bf.Face(_id(n)) for n in range(5)]
        report = _run(bf, faces, tmp_path, Fetcher(), limit=2)
        assert report.fetched == 2 and report.capped
        assert not json.loads((tmp_path / STORE_STATE).read_text())["complete"]


class TestTheRecord:
    def test_the_state_says_how_far_and_when(self, bf, tmp_path):
        at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        _run(bf, [bf.Face(_id(1)), bf.Face(_id(2))], tmp_path, Fetcher(missing={_id(2)}), now=lambda: at)
        state = json.loads((tmp_path / STORE_STATE).read_text())
        assert state == {
            "last_run": "2026-01-02T03:04:05+00:00",
            "wanted": 2,
            "held": 1,
            "unavailable": 1,
            "complete": True,
        }

    def test_the_server_reads_it_for_health(self, tmp_path):
        from commanderblitz.cards.images import read_store_state

        assert read_store_state(tmp_path) == {}
        (tmp_path / STORE_STATE).write_text("not json")
        assert read_store_state(tmp_path) == {}, "a bad record must not stop a boot"


class TestWhatIsWanted:
    def test_owned_art_is_not_crawled_again(self, bf, tmp_path):
        """The committed `data/art` already answers for its printings, and
        `ArtStore.committed` is what both the crawl and the server ask."""
        from commanderblitz.cards.images import CardArt

        owned = tmp_path / "owned"
        owned.mkdir()
        (owned / "forest.jpg").write_bytes(JPEG)
        art = ArtStore(
            images={"forest": CardArt(card_id="forest", scryfall_id=_id(7))},
            directory=owned,
            store=tmp_path / "store",
        )
        fetcher = Fetcher()
        bf.backfill(
            [bf.Face(_id(7)), bf.Face(_id(8))],
            tmp_path / "store",
            committed=lambda f: art.committed(f.scryfall_id, f.back) is not None,
            fetch=fetcher,
            delay=0,
        )
        assert fetcher.calls == [f"https://cards.scryfall.io/art_crop/front/0/0/{_id(8)}.jpg"]

    def test_decks_printings_and_their_faces_are_wanted(self, bf):
        from commanderblitz.server.art import build_store

        data = default_registry()
        art = build_store(data.registry, None, allow_fetch=False)
        wanted = bf.wanted_faces(None, data, art)
        chosen = {
            (p["scryfall_id"])
            for deck in data.decks.values()
            for p in deck.printings.values()
            if p.get("scryfall_id")
        }
        assert chosen, "the shipped decks choose printings"
        assert chosen <= {f.scryfall_id for f in wanted}
