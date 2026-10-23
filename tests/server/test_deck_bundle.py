"""A Deck's import, asked of the site first and adopted here (ADR 0022).

Two apps in one process: the *site*, a hosted ``create_app`` whose Moxfield is
the trimmed fixture, and the *Deck*, a desktop one whose ``Site`` client is
wired to the first through ``site_opener`` rather than a socket.  The real
socket, the interrupted import and the relaunch are the desktop entry point's
(``test_desktop_entry.py``); this file holds the routes and the reconciliation.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

from commanderblitz.cards import importer, moxfield
from commanderblitz.cards.bundle import NEWER_RULES, adopt_bundle, closure
from commanderblitz.cards.images import generated_images_path
from commanderblitz.cards.registry import CardRegistry, default_registry, server_registry
from commanderblitz.server import upstream
from commanderblitz.server.app import create_app
from commanderblitz.server.art import ArtStore
from commanderblitz.server.settings import ServerSettings
from tests.server.test_import import do_import
from tests.server.test_import import payload as payload_fixture
from tests.server.test_import import sandbox as sandbox_fixture

sandbox = sandbox_fixture
payload = payload_fixture

DECK_URL = "https://moxfield.com/decks/vVdybWVgC0imBOlW63FlTg"
DECK_ID = "mox_vvdybwvgc0imbolw63fltg"
JPEG = b"\xff\xd8\xff\xd9"
ORIGIN = "https://site.test"
LIBRARY = "deck-library"


@pytest.fixture
def downloads(monkeypatch):
    """Every art download succeeds at once and is counted."""
    calls: list[str] = []

    def fake_download(self, url, path):
        calls.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(JPEG)
        return True

    monkeypatch.setattr(ArtStore, "_download", fake_download)
    return calls


@pytest.fixture
def site(sandbox, payload, monkeypatch):
    """The hosted app, with Moxfield answering the fixture for any link."""
    monkeypatch.setattr(moxfield, "fetch_deck", lambda public_id, *, opener=None: payload)
    return TestClient(create_app(allow_art_fetch=False))


def site_opener(client: TestClient, calls: list[str] | None = None):
    """A ``urlopen`` that sends the request to ``client`` instead of the network."""

    def opener(request: urllib.request.Request, timeout=None):
        path = request.full_url.removeprefix(ORIGIN)
        if calls is not None:
            calls.append(f"{request.get_method()} {path}")
        response = client.request(
            request.get_method(),
            path,
            content=request.data,
            headers=dict(request.header_items()),
        )
        if response.status_code >= 400:
            raise urllib.error.HTTPError(
                request.full_url, response.status_code, "", {}, io.BytesIO(response.content)
            )
        return io.BytesIO(response.content)

    return opener


def desktop(monkeypatch, opener) -> TestClient:
    """The Deck's sidecar, its site client wired to ``opener``."""

    class WiredSite(upstream.Site):
        def __init__(self, origin, **_):
            super().__init__(origin, opener=opener)

    monkeypatch.setattr("commanderblitz.server.routes.Site", WiredSite)
    settings = ServerSettings(mode="desktop", remote_origin=ORIGIN, eager_art=True)
    return TestClient(create_app(settings=settings))


def deck_file(deck_id: str = DECK_ID) -> dict:
    return json.loads((importer.decks_dir() / f"{deck_id}.deck.json").read_text(encoding="utf-8"))


def forget_the_import(deck_id: str = DECK_ID) -> None:
    """Make the sandbox the Deck's again after the site wrote into it.

    Both apps share one sandbox, so the site's import lands where the Deck's
    would.  Removing the deck file is enough for "the Deck had not imported
    it"; the pool the site wrote is the same pool the Deck would write.
    """
    importer.delete_deck(deck_id)
    server_registry.cache_clear()


class TestTheBundleRoute:
    def test_it_carries_the_deck_and_every_card_behind_it(self, site):
        assert site.post("/api/decks/import", json={"url": DECK_URL}).status_code == 201
        body = site.get(f"/api/decks/{DECK_ID}/bundle").json()

        assert body["deck"] == deck_file()
        carried = {card["id"] for card in body["cards"]}
        deck_ids = set(body["deck"]["commanders"]) | {e["id"] for e in body["deck"]["cards"]}
        assert deck_ids <= carried
        # Faces and tokens ride along: a card the Deck lacks must link there.
        registry = server_registry().registry
        assert carried == closure(deck_ids, lambda c: registry.get(c) if c in registry else None)
        # The proxies the site wrote say what they lost; hand-written cards do not.
        assert body["coverage"], "the fixture deck has proxies"
        assert set(body["coverage"]) <= carried
        assert all(registry.get(c).name for c in body["coverage"])
        # And which printing shows each card, for a machine that has never seen it.
        assert set(body["images"]) <= carried and body["images"]

    def test_a_precon_has_none(self, site):
        assert site.get("/api/decks/aesi/bundle").status_code == 404

    def test_another_librarys_deck_is_refused(self, site):
        site.post("/api/decks/import", json={"url": DECK_URL}, headers={"X-Library-Id": "a"})
        response = site.get(f"/api/decks/{DECK_ID}/bundle", headers={"X-Library-Id": "b"})
        assert response.status_code == 403


class TestImportingThroughTheSite:
    def test_the_deck_asks_the_site_and_never_moxfield(
        self, site, monkeypatch, downloads
    ):
        calls: list[str] = []
        deck = desktop(monkeypatch, site_opener(site, calls))

        def no_moxfield(*_, **__):
            raise AssertionError("the Deck read Moxfield although the site answered")

        response = deck.post(
            "/api/decks/import", json={"url": DECK_URL}, headers={"X-Library-Id": LIBRARY}
        )
        assert response.status_code == 201, response.text
        assert calls == ["POST /api/decks/import", f"GET /api/decks/{DECK_ID}/bundle"]
        monkeypatch.setattr(moxfield, "fetch_deck", no_moxfield)

        body = response.json()
        assert body["deck"]["id"] == DECK_ID
        assert body["art_prefetch"]["complete"] is True
        assert body["art_prefetch"]["missing"] == []
        assert body["deck"]["complete"] is True
        # The site imported it under the Deck's library, and so does the Deck.
        assert deck_file()["owner"] == LIBRARY
        assert deck_file()["complete"] is True

    def test_the_report_matches_the_sites(self, site, monkeypatch, downloads):
        from_site = site.post("/api/decks/import", json={"url": DECK_URL}).json()
        forget_the_import()
        through = desktop(monkeypatch, site_opener(site)).post(
            "/api/decks/import", json={"url": DECK_URL}
        ).json()
        for key in ("total", "playable", "simplified", "lands", "lands_producing_mana"):
            assert through[key] == from_site[key], key
        assert sorted((c["card_id"], c["origin"]) for c in through["cards"]) == sorted(
            (c["card_id"], c["origin"]) for c in from_site["cards"]
        )

    def test_a_site_that_does_not_answer_falls_back_to_moxfield(
        self, sandbox, payload, monkeypatch, downloads
    ):
        def unreachable(request, timeout=None):
            raise urllib.error.URLError("no route to host")

        deck = desktop(monkeypatch, unreachable)
        response = do_import(deck, payload, url=DECK_URL)
        assert response.status_code == 201, response.text
        assert response.json()["art_prefetch"]["complete"] is True

    def test_a_site_error_falls_back_too(self, sandbox, payload, monkeypatch, downloads):
        def broken(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 502, "", {}, io.BytesIO(b"<html>"))

        response = do_import(desktop(monkeypatch, broken), payload, url=DECK_URL)
        assert response.status_code == 201, response.text

    def test_a_refusal_from_the_site_is_the_answer(self, sandbox, monkeypatch, downloads):
        # The site read Moxfield and was told "private"; asking again would
        # only hear it again.
        site = TestClient(create_app(allow_art_fetch=False))

        def private(public_id, *, opener=None):
            raise moxfield.ImportFailed("private", "That deck is private.")

        monkeypatch.setattr(moxfield, "fetch_deck", private)
        deck = desktop(monkeypatch, site_opener(site))
        response = deck.post("/api/decks/import", json={"url": DECK_URL})
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "private"


class TestAdoptingABundle:
    """``adopt_bundle`` against an authored layer older than the site's."""

    @pytest.fixture
    def bundle(self, site):
        site.post("/api/decks/import", json={"url": DECK_URL})
        body = site.get(f"/api/decks/{DECK_ID}/bundle").json()
        forget_the_import()
        return body

    @staticmethod
    def without(card_id: str) -> CardRegistry:
        """This machine's authored layer, from before ``card_id`` was written."""
        return CardRegistry({c.id: c for c in default_registry().registry if c.id != card_id})

    @staticmethod
    def a_native_card(bundle: dict) -> str:
        """A hand-written, non-land card the deck names: no coverage entry."""
        ids = [e["id"] for e in bundle["deck"]["cards"]]
        registry = default_registry().registry
        return next(
            cid
            for cid in ids
            if cid in registry
            and cid not in bundle["coverage"]
            and not registry.get(cid).is_land
            and not registry.get(cid).back_face
        )

    def test_a_card_authored_since_arrives_with_its_rules(self, sandbox, bundle):
        newer = self.a_native_card(bundle)
        index = create_app(allow_art_fetch=False).state.card_index
        report = adopt_bundle(bundle, self.without(newer), index)

        row = next(c for c in report.cards if c.card_id == newer)
        assert row.origin == "native" and row.notes == ()
        site_cards = json.loads(importer.site_cards_path().read_text(encoding="utf-8"))
        assert newer in {c["id"] for c in site_cards["cards"]}
        # With the printing that shows it, or it would be a card with no art here.
        images = json.loads(generated_images_path().read_text(encoding="utf-8"))
        assert images[newer] == bundle["images"][newer] and images[newer]
        assert newer in {e["id"] for e in deck_file()["cards"]}

    def test_a_card_this_engine_cannot_run_becomes_a_proxy(self, sandbox, bundle):
        newer = self.a_native_card(bundle)
        for card in bundle["cards"]:
            if card["id"] == newer:
                card["keywords"] = [*card.get("keywords", []), "a keyword from the future"]
        index = create_app(allow_art_fetch=False).state.card_index
        report = adopt_bundle(bundle, self.without(newer), index)

        name = default_registry().registry.get(newer).name
        row = next(c for c in report.cards if c.name == name)
        assert row.card_id != newer, "a proxy of its own, never the site's id"
        assert row.origin in ("full", "partial")
        assert NEWER_RULES in row.notes
        assert newer not in {e["id"] for e in deck_file()["cards"]}
        assert row.card_id in {e["id"] for e in deck_file()["cards"]}
        assert not importer.site_cards_path().exists()

    def test_nothing_is_written_when_the_bundle_is_not_a_deck(self, sandbox, bundle):
        with pytest.raises(moxfield.ImportFailed) as caught:
            adopt_bundle({"deck": {"id": DECK_ID}, "cards": []}, default_registry().registry, None)
        assert caught.value.code == "bad_bundle"
        assert not (importer.decks_dir() / f"{DECK_ID}.deck.json").exists()


class TestFinishingADeck:
    def test_an_incomplete_deck_is_finished_and_nothing_is_fetched_twice(
        self, site, monkeypatch
    ):
        calls: list[str] = []
        written: list[str] = []
        failing = {"on": True}

        def flaky(self, url, path):
            calls.append(url)
            # Half the files fail from every source the first time round: an
            # import that lost its connection halfway.
            if failing["on"] and sum(path.name.encode()) % 2:
                return False
            written.append(path.name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(ArtStore, "_download", flaky)
        deck = desktop(monkeypatch, site_opener(site))
        first = deck.post("/api/decks/import", json={"url": DECK_URL}).json()
        assert first["art_prefetch"]["complete"] is False
        assert first["art_prefetch"]["missing"]
        assert first["deck"]["complete"] is False
        assert deck_file()["complete"] is False
        listed = {d["id"]: d for d in deck.get("/api/decks").json()}
        assert listed[DECK_ID]["complete"] is False

        failing["on"] = False
        before = list(written)
        done = deck.post("/api/decks/complete").json()
        assert [d["deck_id"] for d in done] == [DECK_ID]
        assert done[0]["complete"] is True and done[0]["missing"] == []
        assert deck_file()["complete"] is True
        # Only what was missing went out again: no file was written twice.
        assert written[len(before):], "the retry fetched the missing files"
        assert not set(written[len(before):]) & set(before)
        assert len(written) == len(set(written))

        # And a launch with every deck complete costs nothing.
        again = len(calls)
        assert deck.post("/api/decks/complete").json() == []
        assert len(calls) == again

    def test_the_site_finishes_nothing(self, site):
        assert site.post("/api/decks/complete").json() == []

    def test_a_card_with_no_printing_anywhere_is_not_missing(self, tmp_path):
        from commanderblitz.cards.images import CardArt

        store = ArtStore(
            images={"custom": CardArt(card_id="custom")},
            directory=tmp_path / "owned",
            cache=tmp_path / "cache",
            allow_fetch=False,
        )
        assert store.missing([("custom", None)]) == []
        assert store.missing([("custom", "11112222-3333-4444-5555-666677778888")]) == ["custom"]
