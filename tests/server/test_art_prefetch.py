"""Fetching a deck's art at import time, for a build whose next launch may be
offline.

The desktop runs the server as a sidecar and fills art lazily like the site
does -- except that a deck imported on the train would then be a grid of grey
plates until the Deck next sees a network.  ``COMMANDERBLITZ_EAGER_ART`` makes the
import fetch everything the board will ask for, in parallel, and say what it
got.  The site keeps its lazy fill: ``eager_art`` is off by default.
"""

from __future__ import annotations

import dataclasses
import threading
import time

import pytest
from fastapi.testclient import TestClient

from commanderblitz.cards.images import CardArt, art_cache_dir
from commanderblitz.cards.registry import default_registry
from commanderblitz.server.app import create_app
from commanderblitz.server.art import ArtStore, deck_art_requests
from commanderblitz.server.settings import ServerSettings
from tests.server.test_import import do_import
from tests.server.test_import import payload as payload_fixture
from tests.server.test_import import sandbox as sandbox_fixture

# The import tests' writable copy of `data/` and their canned Moxfield deck,
# re-exported under the names the tests below ask for.
sandbox = sandbox_fixture
payload = payload_fixture

JPEG = b"\xff\xd8\xff\xd9"
CHOSEN = "11112222-3333-4444-5555-666677778888"
UUIDS = [f"{i:08d}-0000-0000-0000-{i:012d}" for i in range(1, 4)]


@pytest.fixture(scope="module")
def game_data():
    return default_registry()


def counting_store(tmp_path, monkeypatch, *, images=None, delay=0.0, fail=()):
    """A store whose downloads are instant, counted, and never leave the machine."""
    store = ArtStore(images=images or {}, directory=tmp_path / "owned", cache=tmp_path / "cache")
    calls: list[str] = []
    lock = threading.Lock()

    def fake_download(url, path):
        with lock:
            calls.append(url)
        if delay:
            time.sleep(delay)
        if any(f in url for f in fail):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(JPEG)
        return True

    monkeypatch.setattr(store, "_download", fake_download)
    return store, calls


class TestWhatADeckAsksFor:
    def test_every_card_and_its_faces_with_the_decks_printing(self, game_data, tmp_path):
        store = ArtStore(images={}, directory=tmp_path, index=None)
        store.images = create_app(game_data).state.art.images
        edgar = game_data.decks["edgar"]
        deck = dataclasses.replace(
            edgar, printings={"bloodline_keeper": {"scryfall_id": CHOSEN, "artist": "A"}}
        )
        requests = dict(deck_art_requests(deck, game_data.registry, store))

        # The whole list, commanders included, each on the catalog's own art...
        assert set(edgar.unique_ids()) <= set(requests)
        assert requests["edgar_markov"] is None
        # ...except where the deck chose, and the chosen illustration follows
        # the card onto its back face, which no list ever names.
        assert requests["bloodline_keeper"] == CHOSEN
        assert requests["lord_of_lineage"] == CHOSEN

    def test_it_is_sorted_so_a_report_reads_the_same_twice(self, game_data, tmp_path):
        store = ArtStore(images={}, directory=tmp_path, index=None)
        deck = game_data.decks["aesi"]
        ids = [c for c, _ in deck_art_requests(deck, game_data.registry, store)]
        assert ids == sorted(ids)


class TestPrefetch:
    def test_fetches_what_is_missing_and_counts_what_is_not(self, tmp_path, monkeypatch):
        store, calls = counting_store(tmp_path, monkeypatch)
        (tmp_path / "cache").mkdir()
        (tmp_path / "cache" / f"{UUIDS[0]}.jpg").write_bytes(JPEG)

        report = store.prefetch([(u, None) for u in UUIDS])

        assert (report.fetched, report.cached, report.failed) == (2, 1, [])
        assert len(calls) == 2
        for u in UUIDS:
            assert (tmp_path / "cache" / f"{u}.jpg").is_file()
        # Fills land in the cache, never beside the owned bytes.
        assert not (tmp_path / "owned").exists()

    def test_a_failure_is_reported_and_remembered(self, tmp_path, monkeypatch):
        store, calls = counting_store(tmp_path, monkeypatch, fail=[UUIDS[1]])
        report = store.prefetch([(u, None) for u in UUIDS])
        assert report.failed == [UUIDS[1]]
        assert report.fetched == 2
        assert UUIDS[1] in store._missing
        # Asking again costs nothing: the miss is remembered, not retried.
        again = store.prefetch([(UUIDS[1], None)])
        assert again.failed == [UUIDS[1]] and len(calls) == 3

    def test_a_card_with_no_printing_anywhere_fails_cleanly(self, tmp_path, monkeypatch):
        store, calls = counting_store(tmp_path, monkeypatch)
        report = store.prefetch([("aetherling_serpent", None)])
        assert report.failed == ["aetherling_serpent"] and calls == []

    def test_a_chosen_printing_already_on_disk_is_cached(self, tmp_path, monkeypatch):
        store, calls = counting_store(
            tmp_path, monkeypatch, images={"forest": CardArt(card_id="forest", scryfall_id=UUIDS[0])}
        )
        (tmp_path / "cache").mkdir()
        (tmp_path / "cache" / f"{CHOSEN}.jpg").write_bytes(JPEG)
        report = store.prefetch([("forest", CHOSEN)])
        assert (report.fetched, report.cached) == (0, 1) and calls == []

    def test_an_empty_request_does_nothing(self, tmp_path, monkeypatch):
        store, calls = counting_store(tmp_path, monkeypatch)
        assert store.prefetch([]).fetched == 0 and calls == []


class TestDownloadsRunInParallel:
    """The store lock used to be held across the download, which made a
    hundred-card prefetch a hundred sequential round trips."""

    def test_three_workers_fetch_three_cards_at_once(self, tmp_path, monkeypatch):
        store = ArtStore(images={}, directory=tmp_path)
        # Each download waits for the other two.  Serialised, this deadlocks;
        # the barrier's timeout turns that into a failure rather than a hang.
        barrier = threading.Barrier(3, timeout=5)

        def gated_download(url, path):
            barrier.wait()
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(store, "_download", gated_download)
        report = store.prefetch([(u, None) for u in UUIDS], workers=3)
        assert report.fetched == 3 and not barrier.broken

    def test_the_same_card_is_downloaded_once(self, tmp_path, monkeypatch):
        store, calls = counting_store(tmp_path, monkeypatch, delay=0.05)
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(store.resolve(UUIDS[0])))
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(calls) == 1
        assert all(r == tmp_path / "cache" / f"{UUIDS[0]}.jpg" for r in results)
        assert store._inflight == {}, "gates are released once the file exists"

    def test_a_miss_is_recorded_once_and_shared(self, tmp_path, monkeypatch):
        store, calls = counting_store(tmp_path, monkeypatch, delay=0.05, fail=UUIDS)
        threads = [threading.Thread(target=lambda: store.resolve(UUIDS[0])) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(calls) == 1 and UUIDS[0] in store._missing


class TestADeckThatChoseTheCatalogsPrinting:
    """A deck naming the printing the catalog already shows is served with no
    ``?p``, so the card's own art must answer from the file its prefetch
    wrote under the printing's name -- offline, with nothing left to fetch."""

    def test_the_prefetched_file_serves_the_card(self, tmp_path, monkeypatch):
        images = {"bear": CardArt(card_id="bear", scryfall_id=CHOSEN, artist="A")}
        store, calls = counting_store(tmp_path, monkeypatch, images=images)
        assert store.url_for("bear", printing=CHOSEN) == "/art/bear.jpg"

        report = store.prefetch([("bear", CHOSEN)])
        assert report.fetched == 1 and len(calls) == 1
        assert store.missing([("bear", CHOSEN)]) == []

        store.allow_fetch = False  # offline
        assert store.resolve("bear") == tmp_path / "cache" / f"{CHOSEN}.jpg"
        assert store.missing([("bear", None)]) == []
        assert len(calls) == 1


class TestTheImportRoute:
    @pytest.fixture
    def downloads(self, monkeypatch):
        calls: list[str] = []

        def fake_download(self, url, path):
            calls.append(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(ArtStore, "_download", fake_download)
        return calls

    def test_the_desktop_fetches_the_decks_art_at_import(self, sandbox, payload, downloads):
        client = TestClient(create_app(settings=ServerSettings(eager_art=True)))
        body = do_import(client, payload).json()

        report = body["art_prefetch"]
        assert report is not None
        assert report["fetched"] > 50, report
        assert report["cached"] == 0 and report["failed"] == []
        # The sandbox ships no art, so every file in the cache is one download
        # -- and the cache is the generated directory, not the data.  Fewer
        # downloads than cards fetched is right: two cards that chose the same
        # illustration share one file, and the second finds it on disk.
        assert len(list(art_cache_dir().glob("*.jpg"))) == len(downloads)
        assert report["fetched"] >= len(downloads)
        assert art_cache_dir().is_relative_to(sandbox / "generated")

    def test_the_site_does_not(self, sandbox, payload, downloads):
        client = TestClient(create_app())
        body = do_import(client, payload).json()
        assert body["art_prefetch"] is None
        assert downloads == []

    def test_a_dry_run_fetches_nothing(self, sandbox, payload, downloads):
        client = TestClient(create_app(settings=ServerSettings(eager_art=True)))
        body = do_import(client, payload, dry_run=True).json()
        assert body["art_prefetch"] is None
        assert downloads == []
