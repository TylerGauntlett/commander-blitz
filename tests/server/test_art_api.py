"""Serving card art, and the catalog behind it.

The property under test throughout is **self-ownership**: the browser is only
ever handed a same-origin path, and a game renders with the network unplugged.
Anything that would put a ``cards.scryfall.io`` URL in a response is a
regression, so there is a test that says so directly.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from commanderblitz.cards.images import CardArt, catalog_path
from commanderblitz.cards.registry import default_registry
from commanderblitz.server.app import create_app
from commanderblitz.server.art import ArtStore
from commanderblitz.server.art import spread_across_faces as _spread_across_faces

# A 1x1 JPEG, so a planted file is a real image rather than bytes that happen to
# have the right extension.
JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffc00011080001000103012200021101031101ffc4001f000001"
    "05010101010101000000000000000000010203040506070809"
    "0a0bffda0008010100003f00d2cf20ffd9"
)


@pytest.fixture(scope="module")
def game_data():
    return default_registry()


@pytest.fixture(scope="module")
def client(game_data) -> TestClient:
    # Fetching is off: a test must never depend on Scryfall being reachable.
    return TestClient(create_app(game_data, allow_art_fetch=False))


class TestImagesEndpoint:
    def test_covers_every_engine_card(self, client, game_data):
        body = client.get("/api/images").json()
        assert set(body["images"]) == set(game_data.registry.ids())
        assert body["art_base"] == "/art"

    def test_a_resolved_card_points_at_this_server(self, client):
        entry = client.get("/api/images").json()["images"]["forest"]
        assert entry["art"] == "/art/forest.jpg"
        assert entry["artist"]

    def test_nothing_in_the_map_is_null(self, client):
        """Was "a card with no printing is null", pointed at `aetherling_serpent`.

        Null rather than a dangling path was the right contract and still is --
        the client draws a plate and never issues a request it knows will 404 --
        but there is no card left in the pool to exercise it with. The five
        invented designs in the hand-curated Aesi list went when the printed
        precon shipped, so the claim worth holding is that *nothing* is null.
        """
        images = client.get("/api/images").json()["images"]
        assert images
        assert not [card_id for card_id, art in images.items() if art is None]


class TestScopingToAGame:
    """`?game_id=` exists because the unscoped map is no longer bounded.

    It used to carry the ~149 cards the engine shipped. With deck import a
    server can hold thousands, and a board still only ever draws its own ninety.
    """

    @pytest.fixture
    def game_id(self, client) -> str:
        return client.post(
            "/api/games",
            json={
                "seats": [
                    {"deck_id": "aesi", "kind": "human"},
                    {"deck_id": "edgar", "kind": "ai", "agent": "random"},
                ],
                "seed": 5,
            },
        ).json()["game_id"]

    def test_it_covers_the_cards_in_that_game(self, client, game_id, game_data):
        scoped = client.get(f"/api/images?game_id={game_id}").json()["images"]
        for deck_id in ("aesi", "edgar"):
            assert game_data.deck(deck_id).unique_ids() <= set(scoped)

    def test_it_still_covers_the_tokens(self, client, game_id, game_data):
        # A token is never in a deck list but is very much on the board, and a
        # missing one is a blank plate the first time somebody attacks.
        scoped = client.get(f"/api/images?game_id={game_id}").json()["images"]
        tokens = {c.id for c in game_data.registry if c.is_token}
        assert tokens
        assert tokens <= set(scoped)

    def test_it_covers_the_other_face_of_a_double_faced_card(
        self, client, game_id, game_data
    ):
        """The regression: a transformed permanent is serialized under the *back
        face's* id, and an id missing from this map is one the client reads as a
        card with no printing -- so a transformed Bloodline Keeper (or Henrika
        Domnathi, in a deck that plays her) drew the hatched plate, with its art
        sitting in `data/art` under exactly that name."""
        scoped = client.get(f"/api/images?game_id={game_id}").json()["images"]
        front = "bloodline_keeper"
        assert front in scoped, "the deck's own card"
        assert game_data.registry.get(front).back_face == "lord_of_lineage"
        # Present *and* carrying a URL. A key mapped to `null` is the map saying
        # "this card has no printing", which draws the same hatched plate a
        # missing key does -- so key presence alone would not be the claim.
        assert scoped.get("lord_of_lineage"), "the back face resolves to art"
        assert scoped["lord_of_lineage"]["art"]

    def test_it_leaves_out_cards_no_seat_can_draw(self, client, game_id, game_data):
        scoped = set(client.get(f"/api/images?game_id={game_id}").json()["images"])
        reachable = {c.id for c in game_data.registry if c.is_token}
        for deck_id in ("aesi", "edgar"):
            reachable |= game_data.deck(deck_id).unique_ids()
        # Plus the other faces of everything reachable, which is what a seat can
        # actually put on the board: a card in a deck list can transform, and a
        # card cast as its adventure or its second half is serialized under that
        # face's own id.
        faces = set(reachable)
        for card_id in reachable:
            card = game_data.registry.get(card_id)
            faces |= {f for f in (card.back_face, card.second_face) if f}
        assert scoped == faces

    def test_the_unscoped_form_is_unchanged(self, client, game_id, game_data):
        # Scripts depend on it, and "every card the engine has" is a genuinely
        # different question from "every card in this game".
        assert set(client.get("/api/images").json()["images"]) == set(
            game_data.registry.ids()
        )

    def test_an_unknown_game_is_a_404(self, client):
        assert client.get("/api/images?game_id=nope").status_code == 404

    def test_no_third_party_url_reaches_the_client(self, client):
        # The whole point. If this fails the board has a runtime dependency on
        # Scryfall again, and it will fail on someone's plane.
        raw = client.get("/api/images").text
        assert "scryfall" not in raw.lower()

    def test_the_card_endpoint_agrees(self, client):
        card = client.get("/api/cards/forest").json()
        assert card["art_url"] == "/art/forest.jpg"
        assert card["artist"]

    def test_a_card_the_pool_does_not_have_is_a_404(self, client):
        """The replacement for "a custom card has no art_url". There is no
        artless card left to ask about, so the neighbouring case is the one
        worth pinning: an id nobody defined is absent, not null."""
        assert client.get("/api/cards/aetherling_serpent").status_code == 404


class TestArtRoute:
    def test_serves_a_cached_file(self, client):
        response = client.get("/art/forest.jpg")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content[:3] == b"\xff\xd8\xff"

    def test_sends_validators_so_the_browser_can_revalidate(self, client):
        # FileResponse supplies these; a StaticFiles mount would too, but the
        # mount could not do the lazy fill, so this asserts we did not lose
        # them by hand-rolling the route.
        headers = client.get("/art/forest.jpg").headers
        assert headers.get("etag")
        assert headers.get("last-modified")

    def test_an_artless_card_is_404(self, client):
        assert client.get("/art/aetherling_serpent.jpg").status_code == 404

    def test_an_unknown_card_is_404(self, client):
        assert client.get("/art/black_lotus.jpg").status_code == 404

    @pytest.mark.parametrize(
        "path",
        [
            "/art/..%2F..%2Fsecret.jpg",
            "/art/%2Fetc%2Fpasswd.jpg",
            "/art/Forest.jpg",  # ids are lower-case; a capital is not one
            "/art/forest.png",
            "/art/forest",
        ],
    )
    def test_rejects_anything_that_is_not_a_card_id(self, client, path):
        assert client.get(path).status_code == 404


class TestLazyFill:
    """A card outside data/cards/ is fetched once, then it is a local file."""

    def _store(self, tmp_path, monkeypatch, payload=JPEG, fail=False):
        store = ArtStore(images={}, directory=tmp_path, index=None)
        calls: list[str] = []

        def fake_download(url: str, path):
            calls.append(url)
            if fail:
                return False
            path.write_bytes(payload)
            return True

        monkeypatch.setattr(store, "_download", fake_download)
        return store, calls

    def test_fetches_a_catalog_card_by_scryfall_id(self, tmp_path, monkeypatch):
        store, calls = self._store(tmp_path, monkeypatch)
        uuid = "0000419b-0bba-4488-8f7a-6194544ce91e"
        path = store.resolve(uuid)
        assert path is not None and path.read_bytes() == JPEG
        assert calls == [
            f"https://cards.scryfall.io/art_crop/front/0/0/{uuid}.jpg"
        ]

    def test_the_second_request_hits_disk_not_the_network(self, tmp_path, monkeypatch):
        store, calls = self._store(tmp_path, monkeypatch)
        uuid = "0000419b-0bba-4488-8f7a-6194544ce91e"
        store.resolve(uuid)
        store.resolve(uuid)
        assert len(calls) == 1

    def test_a_failed_fetch_is_remembered(self, tmp_path, monkeypatch):
        # Without the negative set, a board holding one unresolvable card
        # re-attempts a download on every single re-render.
        store, calls = self._store(tmp_path, monkeypatch, fail=True)
        uuid = "0000419b-0bba-4488-8f7a-6194544ce91e"
        assert store.resolve(uuid) is None
        assert store.resolve(uuid) is None
        assert len(calls) == 1

    def test_never_fetches_for_a_malformed_id(self, tmp_path, monkeypatch):
        store, calls = self._store(tmp_path, monkeypatch)
        for bad in ("../../etc/passwd", "Forest", "not a uuid", ""):
            assert store.resolve(bad) is None
        assert calls == []

    def test_fetching_can_be_switched_off_entirely(self, tmp_path, monkeypatch):
        store, calls = self._store(tmp_path, monkeypatch)
        store.allow_fetch = False
        assert store.resolve("0000419b-0bba-4488-8f7a-6194544ce91e") is None
        assert calls == []


#: A printing no catalog row of ours names -- which is the normal case for a
#: deck's choice, since the catalog keeps one row per card *name*.
CHOSEN = "11112222-3333-4444-5555-666677778888"


class TestADecksOwnPrinting:
    """`?p=` is a deck saying "this illustration, not the one you picked"."""

    def _store(self, tmp_path, monkeypatch, *, images=None, fail=False):
        store = ArtStore(images=images or {}, directory=tmp_path, index=None)
        calls: list[str] = []

        def fake_download(url: str, path):
            calls.append(url)
            if fail:
                return False
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(store, "_download", fake_download)
        return store, calls

    def _art(self, scryfall_id, *, back=False):
        return CardArt(card_id="forest", scryfall_id=scryfall_id, artist="A", back=back)

    def test_it_fetches_the_printing_the_deck_asked_for(self, tmp_path, monkeypatch):
        store, calls = self._store(
            tmp_path, monkeypatch, images={"forest": self._art("0" * 8 + "-0000-0000-0000-" + "0" * 12)}
        )
        path = store.resolve("forest", printing=CHOSEN)
        assert path is not None and path.read_bytes() == JPEG
        assert calls == [f"https://cards.scryfall.io/art_crop/front/1/1/{CHOSEN}.jpg"]

    def test_it_is_cached_under_the_printing_not_the_card(self, tmp_path, monkeypatch):
        """Two decks that chose the same illustration share one file -- and so
        does the catalog hover path, which already writes `{uuid}.jpg`."""
        store, _ = self._store(tmp_path, monkeypatch)
        store.resolve("forest", printing=CHOSEN)
        assert (tmp_path / f"{CHOSEN}.jpg").is_file()
        assert not (tmp_path / "forest.jpg").exists()

    def test_a_transformed_card_gets_the_back_of_that_printing(self, tmp_path, monkeypatch):
        """The deck names an illustration, not a face. Two faces share one
        Scryfall id and differ only by `back`, which only our registry knows --
        so a back face asking for a deck's printing must still get its back."""
        store, calls = self._store(
            tmp_path, monkeypatch, images={"forest": self._art("0" * 8 + "-0000-0000-0000-" + "0" * 12, back=True)}
        )
        store.resolve("forest", printing=CHOSEN)
        assert calls == [f"https://cards.scryfall.io/art_crop/back/1/1/{CHOSEN}.jpg"]
        assert (tmp_path / f"{CHOSEN}_back.jpg").is_file()

    def test_an_unfetchable_printing_falls_back_to_the_cards_own_art(
        self, tmp_path, monkeypatch
    ):
        """The load-bearing failure path. A deck list's printing cannot be
        validated before it is served -- the catalog has one row per name, not
        one per printing -- so a dud id must cost the *right* illustration, not
        the card. A 404 here is a broken image in the preview rail."""
        (tmp_path / "forest.jpg").write_bytes(JPEG)
        store, calls = self._store(tmp_path, monkeypatch, fail=True)
        assert store.resolve("forest", printing=CHOSEN) == tmp_path / "forest.jpg"
        assert len(calls) == 1, "and it does not re-try on every render"
        store.resolve("forest", printing=CHOSEN)
        assert len(calls) == 1

    def test_a_failed_printing_does_not_blacklist_the_cards_own_art(
        self, tmp_path, monkeypatch
    ):
        """The negative set is keyed by printing and face, not by card id. Keyed
        by card id, one bad printing would also suppress the ordinary art."""
        base = "0" * 8 + "-0000-0000-0000-" + "0" * 12
        store, calls = self._store(tmp_path, monkeypatch, images={"forest": self._art(base)})

        def only_the_printing_fails(url, path):
            calls.append(url)
            if CHOSEN in url:
                return False
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(store, "_download", only_the_printing_fails)
        assert store.resolve("forest", printing=CHOSEN) is not None, "fell back"
        assert "forest" not in store._missing
        assert f"{CHOSEN}|False" in store._missing, "only the printing is remembered"
        assert store.resolve("forest") == tmp_path / "forest.jpg"

    @pytest.mark.parametrize("junk", ["../../etc/passwd", "Forest", "", "not a uuid"])
    def test_a_printing_that_is_not_a_scryfall_id_is_ignored(
        self, tmp_path, monkeypatch, junk
    ):
        (tmp_path / "forest.jpg").write_bytes(JPEG)
        store, calls = self._store(tmp_path, monkeypatch)
        assert store.resolve("forest", printing=junk) == tmp_path / "forest.jpg"
        assert calls == [], "nothing was fetched, and no junk reached a path"

    def test_agreeing_with_the_catalog_adds_no_url(self, tmp_path, monkeypatch):
        # Otherwise every card in a deck gets a second URL for a picture this
        # repository already ships -- a cache miss and a download, for nothing.
        store, _ = self._store(tmp_path, monkeypatch, images={"forest": self._art(CHOSEN)})
        assert store.url_for("forest", printing=CHOSEN) == "/art/forest.jpg"

    def test_a_card_with_no_catalog_printing_still_gets_the_decks(
        self, tmp_path, monkeypatch
    ):
        # `has_printing` false means *we* found nothing, not that the card has
        # no art. The author chose one, and that is the whole point.
        store, _ = self._store(
            tmp_path, monkeypatch, images={"forest": CardArt(card_id="forest")}
        )
        assert store.url_for("forest") is None
        assert store.url_for("forest", printing=CHOSEN) == f"/art/forest.jpg?p={CHOSEN}"


class TestThePrintingReachesTheRoute:
    @pytest.mark.parametrize(
        "query",
        ["?p=../../etc/passwd", "?p=Forest", "?p=" + "a" * 200, "?p=", "?p=%2e%2e%2f"],
    )
    def test_junk_is_ignored_rather_than_fatal(self, client, query):
        # The card still renders: `p` is a preference, not an address.
        assert client.get(f"/art/forest.jpg{query}").status_code == 200

    def test_a_good_printing_is_passed_through(self, client, monkeypatch):
        seen: list[tuple] = []
        store = client.app.state.art
        monkeypatch.setattr(
            store, "resolve", lambda card_id, printing=None: seen.append((card_id, printing))
        )
        client.get(f"/art/forest.jpg?p={CHOSEN}")
        assert seen == [("forest", CHOSEN)]


#: Sheoldred, the Apocalypse, the card this pair of tests was written for.
#: `art_pins.json` pins the Dominaria United printing; the Secret Lair is what
#: the dedupe picked before the pin and what a deck imported before it recorded.
PINNED_DMU = "d67be074-cdd4-41d9-ac89-0a0456c4e4b2"
PROXY_SECRET_LAIR = "c68629ff-72b3-40a2-b578-cddb6ddb4ccf"


class TestTheAuthoredLayerWins:
    """`pool.images.json` may fill gaps, never overrule the committed answer.

    `load_game_data` already drops a generated *card* whose card has since been
    authored. The art map did the opposite: it applied the overlay with
    `update`, so a proxy's printing beat the authored card's.

    That combination is not hypothetical -- it is the live bug. The overlay is
    append-only (the importer `update`s entries in and never re-resolves one),
    so a card keeps whichever printing the catalog chose on the day its deck was
    imported. Sheoldred was imported as a proxy, then authored, then pinned to
    the Dominaria United art; every deployment that had imported her deck went
    on serving the Secret Lair illustration with the pin merged, tested, and
    deployed.
    """

    def _resolve(self, tmp_path, monkeypatch, *, committed, generated):
        monkeypatch.setenv("COMMANDERBLITZ_DATA_DIR", str(tmp_path))
        catalog = tmp_path / "catalog"
        catalog.mkdir(parents=True)
        (catalog / "registry_images.json").write_text(
            json.dumps(committed), encoding="utf-8"
        )
        pool = tmp_path / "generated" / "cards"
        pool.mkdir(parents=True)
        (pool / "pool.images.json").write_text(json.dumps(generated), encoding="utf-8")
        from commanderblitz.server.art import _resolve_images

        # `registry` and `index` are only consulted when the committed file is
        # missing or empty, and here it is neither.
        return _resolve_images(None, None)

    def test_a_stale_proxy_cannot_overrule_a_pinned_printing(
        self, tmp_path, monkeypatch
    ):
        images = self._resolve(
            tmp_path,
            monkeypatch,
            committed={
                "sheoldred_the_apocalypse": {
                    "scryfall_id": PINNED_DMU,
                    "artist": "Chris Rahn",
                }
            },
            generated={
                "sheoldred_the_apocalypse": {
                    "scryfall_id": PROXY_SECRET_LAIR,
                    "artist": "Nicky Barkla",
                }
            },
        )
        art = images["sheoldred_the_apocalypse"]
        assert art.scryfall_id == PINNED_DMU
        assert art.artist == "Chris Rahn"

    def test_the_overlay_still_supplies_a_card_the_registry_never_had(
        self, tmp_path, monkeypatch
    ):
        # The overlay's actual job. Losing this would leave every imported card
        # that the engine does not ship drawing a hatched plate.
        images = self._resolve(
            tmp_path,
            monkeypatch,
            committed={"forest": {"scryfall_id": PINNED_DMU, "artist": "Someone"}},
            generated={
                "an_imported_card": {
                    "scryfall_id": PROXY_SECRET_LAIR,
                    "artist": "Nicky Barkla",
                }
            },
        )
        assert images["an_imported_card"].scryfall_id == PROXY_SECRET_LAIR
        assert images["forest"].scryfall_id == PINNED_DMU


class TestOwnedBytesBeatTheCache:
    """Two directories, and the committed one is authoritative.

    The owned bytes ship in the image and are never written at runtime; the
    cache holds what the lazy fill downloaded and lives on a Docker volume. A
    single directory for both is what made the volume shadow the image, so that
    a corrected illustration could be committed, built and deployed and still
    never reach the site -- the volume seeds once and no later image re-seeds it.
    """

    def _dirs(self, tmp_path):
        owned = tmp_path / "art"
        cache = tmp_path / "generated" / "art"
        owned.mkdir(parents=True)
        cache.mkdir(parents=True)
        return owned, cache

    def test_a_cached_file_never_shadows_the_committed_one(self, tmp_path):
        owned, cache = self._dirs(tmp_path)
        (owned / "forest.jpg").write_bytes(JPEG)
        (cache / "forest.jpg").write_bytes(b"what an older image shipped")
        store = ArtStore(images={}, directory=owned, cache=cache, index=None)
        assert store.resolve("forest").read_bytes() == JPEG

    def test_the_lazy_fill_writes_to_the_cache_only(self, tmp_path, monkeypatch):
        owned, cache = self._dirs(tmp_path)
        store = ArtStore(images={}, directory=owned, cache=cache, index=None)

        def fake_download(url: str, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(store, "_download", fake_download)
        uuid = "0000419b-0bba-4488-8f7a-6194544ce91e"
        assert store.resolve(uuid) == cache / f"{uuid}.jpg"
        # The owned directory is repository content and read-only in the image;
        # a fill that landed there would be unwritable in production anyway.
        assert list(owned.iterdir()) == []

    def test_the_cache_still_serves_a_card_the_image_does_not_own(self, tmp_path):
        owned, cache = self._dirs(tmp_path)
        uuid = "0000419b-0bba-4488-8f7a-6194544ce91e"
        (cache / f"{uuid}.jpg").write_bytes(JPEG)
        store = ArtStore(
            images={}, directory=owned, cache=cache, index=None, allow_fetch=False
        )
        assert store.resolve(uuid) == cache / f"{uuid}.jpg"

    def test_health_counts_both_directories(self, tmp_path):
        owned, cache = self._dirs(tmp_path)
        (owned / "forest.jpg").write_bytes(JPEG)
        (cache / "black_lotus.jpg").write_bytes(JPEG)
        store = ArtStore(images={}, directory=owned, cache=cache, index=None)
        assert store.cached_ids() == {"forest", "black_lotus"}

    def test_one_directory_serving_as_both_is_not_double_counted(self, tmp_path):
        # `cache=None` means "beside the owned bytes" -- what a caller with a
        # single directory gets, and what every checkout got before the split.
        owned = tmp_path / "art"
        owned.mkdir()
        (owned / "forest.jpg").write_bytes(JPEG)
        store = ArtStore(images={}, directory=owned, index=None)
        assert store.cache == owned
        assert store.cached_ids() == {"forest"}


class TestTheStoreLayer:
    """The crawled store sits behind the committed art and ahead of the cache.

    ADR 0021. It is keyed by printing, so a card is answered through the
    printing it resolves to, and a deck's choice is answered without a fetch.
    """

    BASE = "0" * 8 + "-0000-0000-0000-" + "0" * 12

    def _store(self, tmp_path, monkeypatch, *, back=False, upstream=None, fail=()):
        from commanderblitz.cards.images import store_path

        for name in ("owned", "store", "cache"):
            (tmp_path / name).mkdir()
        store = ArtStore(
            images={"forest": CardArt(card_id="forest", scryfall_id=self.BASE, back=back)},
            directory=tmp_path / "owned",
            cache=tmp_path / "cache",
            store=tmp_path / "store",
            upstream=upstream,
            index=None,
        )
        calls: list[str] = []

        def fake_download(url, path):
            calls.append(url)
            if any(f in url for f in fail):
                return False
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(store, "_download", fake_download)

        def plant(scryfall_id, *, back=False):
            path = store_path(tmp_path / "store", scryfall_id, back=back)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(JPEG)
            return path

        return store, calls, plant

    def test_a_store_file_is_served_ahead_of_a_cached_one(self, tmp_path, monkeypatch):
        store, calls, plant = self._store(tmp_path, monkeypatch)
        (tmp_path / "cache" / "forest.jpg").write_bytes(JPEG)
        stored = plant(self.BASE)
        assert store.resolve("forest") == stored
        assert calls == []

    def test_a_committed_file_is_served_ahead_of_the_store(self, tmp_path, monkeypatch):
        store, _, plant = self._store(tmp_path, monkeypatch)
        plant(self.BASE)
        (tmp_path / "owned" / "forest.jpg").write_bytes(JPEG)
        assert store.resolve("forest") == tmp_path / "owned" / "forest.jpg"

    def test_the_back_face_is_its_own_file(self, tmp_path, monkeypatch):
        store, calls, plant = self._store(tmp_path, monkeypatch, back=True)
        plant(self.BASE)
        back = plant(self.BASE, back=True)
        assert store.resolve("forest") == back
        assert calls == []

    def test_a_decks_printing_is_served_from_the_store(self, tmp_path, monkeypatch):
        store, calls, plant = self._store(tmp_path, monkeypatch)
        chosen = plant(CHOSEN)
        assert store.resolve("forest", printing=CHOSEN) == chosen
        assert calls == []
        assert store.fell_through == 0

    def test_a_printing_the_store_lacks_still_fills_lazily(self, tmp_path, monkeypatch):
        store, calls, _ = self._store(tmp_path, monkeypatch)
        path = store.resolve("forest", printing=CHOSEN)
        assert path == tmp_path / "cache" / f"{CHOSEN}.jpg"
        assert calls == [f"https://cards.scryfall.io/art_crop/front/1/1/{CHOSEN}.jpg"]
        assert store.fell_through == 1, "and /health hears about it"

    def test_a_printing_owned_under_a_card_id_is_served_by_printing(self, tmp_path, monkeypatch):
        """The crawl skips printings `data/art` owns, so a catalog hover or a
        sidecar asking by uuid must be answered from the owned file."""
        store, calls, _ = self._store(tmp_path, monkeypatch)
        (tmp_path / "owned" / "forest.jpg").write_bytes(JPEG)
        assert store.resolve(self.BASE) == tmp_path / "owned" / "forest.jpg"
        assert calls == []

    def test_the_back_of_a_printing_is_addressable_by_its_store_name(
        self, tmp_path, monkeypatch
    ):
        store, calls, plant = self._store(tmp_path, monkeypatch)
        back = plant(CHOSEN, back=True)
        assert store.resolve(f"{CHOSEN}_back") == back
        assert store.resolve(f"{CHOSEN}_front") is None, "only the one suffix"
        assert calls == []


class TestTheDeckAsksTheSiteFirst:
    """A sidecar's fill asks the hosted store, then Scryfall (ADR 0021)."""

    def _store(self, tmp_path, monkeypatch, *, fail=()):
        store = ArtStore(
            images={"lord_of_lineage": CardArt(card_id="lord_of_lineage", scryfall_id=CHOSEN, back=True)},
            directory=tmp_path,
            upstream="https://commanderblitz.com",
            index=None,
        )
        calls: list[str] = []

        def fake_download(url, path):
            calls.append(url)
            if any(f in url for f in fail):
                return False
            path.write_bytes(JPEG)
            return True

        monkeypatch.setattr(store, "_download", fake_download)
        return store, calls

    def test_the_site_is_asked_by_the_stores_own_name(self, tmp_path, monkeypatch):
        store, calls = self._store(tmp_path, monkeypatch)
        assert store.resolve("lord_of_lineage") is not None
        assert calls == [f"https://commanderblitz.com/art/{CHOSEN}_back.jpg"]

    def test_scryfall_is_asked_when_the_site_fails(self, tmp_path, monkeypatch):
        store, calls = self._store(tmp_path, monkeypatch, fail=("commanderblitz.com",))
        assert store.resolve("lord_of_lineage") is not None
        assert calls == [
            f"https://commanderblitz.com/art/{CHOSEN}_back.jpg",
            f"https://cards.scryfall.io/art_crop/back/1/1/{CHOSEN}.jpg",
        ]

    def test_the_sidecar_gets_the_site_and_the_site_gets_nobody(self, game_data):
        from commanderblitz.server.settings import ServerSettings

        desktop = create_app(
            game_data,
            allow_art_fetch=False,
            settings=ServerSettings(mode="desktop", remote_origin="https://commanderblitz.com"),
        )
        assert desktop.state.art.upstream == "https://commanderblitz.com"
        hosted = create_app(game_data, allow_art_fetch=False)
        assert hosted.state.art.upstream is None


class TestTheDeployedShape:
    """The two invariants that live outside Python and broke it from there."""

    def test_the_cache_is_inside_the_tree_the_volume_persists(self):
        from commanderblitz.cards.images import art_cache_dir, art_dir, generated_dir

        assert art_dir() != art_cache_dir()
        # `generated/` is the one mount point, so the cache has to be under it
        # to outlive a container -- and the owned bytes have to be outside it.
        assert generated_dir() in art_cache_dir().parents
        assert generated_dir() not in art_dir().parents

    def test_no_volume_is_mounted_over_the_committed_art(self):
        """The regression, stated where it can actually be caught.

        Nothing in Python can observe this: the shadowing happens in the mount
        namespace, and every test above passes just as well with the volume
        back. `:/app/data/art` in a volume entry is the whole bug.
        """
        from pathlib import Path

        compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
        assert ":/app/data/art" not in compose.read_text(encoding="utf-8"), (
            "a volume mounted over /app/data/art seeds once and is never "
            "re-seeded, so committed art can never be updated by a deploy"
        )

    def test_the_image_carries_the_store_in_a_layer_of_its_own(self):
        """ADR 0021. One `COPY data/` again would put the whole corpus in the
        layer every card edit rebuilds, and every deploy would re-ship it."""
        from pathlib import Path

        dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text(encoding="utf-8")
        copies = [line for line in dockerfile.splitlines() if line.startswith("COPY")]
        assert "COPY data/art_store/ ./data/art_store/" in copies
        data = [line for line in copies if " data/ " in line]
        assert data == ["COPY --exclude=**/art_store data/ ./data/"]
        assert copies.index(data[0]) > copies.index("COPY data/art_store/ ./data/art_store/")
        assert dockerfile.startswith("# syntax=docker/dockerfile:1.7-labs\n"), "for --exclude"
        ignored = (Path(__file__).resolve().parents[2] / ".dockerignore").read_text(encoding="utf-8")
        assert "art_store" not in ignored

    def test_the_decks_package_leaves_the_store_out(self):
        """A Deck asks the site for the store's art; carrying it would put the
        whole corpus in every content update."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        assembler = (root / "desktop" / "scripts" / "assemble-content.mjs").read_text(encoding="utf-8")
        assert 'rel.startsWith("/art_store")' in assembler

    def test_the_gate_treats_a_crawl_as_inert(self):
        """`art-backfill.yml` opens a pull request per crawl; each would cost a
        full gate run if the store were not inert in `changes`."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        deploy = (root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        assert "data/art_store/*) return 0 ;;" in deploy


@pytest.mark.skipif(not catalog_path().exists(), reason="no card index built")
class TestCatalog:
    def test_search_returns_results_and_an_unclamped_total(self, client):
        body = client.get("/api/catalog", params={"q": "goblin", "limit": 5}).json()
        assert len(body["results"]) <= 5
        assert body["total"] >= len(body["results"])

    def test_an_exact_name_ranks_first(self, client):
        body = client.get("/api/catalog", params={"q": "Lightning Bolt"}).json()
        assert body["results"][0]["name"] == "Lightning Bolt"

    def test_results_carry_a_same_origin_art_url(self, client):
        body = client.get("/api/catalog", params={"q": "Lightning Bolt"}).json()
        art = body["results"][0]["art_url"]
        assert art.startswith("/art/") and art.endswith(".jpg")

    def test_limit_is_capped_server_side(self, client):
        # A client must not be able to ask for all 32k rows in one response.
        assert client.get("/api/catalog", params={"limit": 5000}).status_code == 422

    def test_a_bad_colour_string_is_rejected(self, client):
        assert client.get("/api/catalog", params={"colors": "ZZ"}).status_code == 422

    def test_a_single_card_round_trips(self, client):
        first = client.get("/api/catalog", params={"q": "Lightning Bolt"}).json()["results"][0]
        again = client.get(f"/api/catalog/{first['scryfall_id']}").json()
        assert again["name"] == first["name"]

    def test_an_unknown_scryfall_id_is_404(self, client):
        assert client.get("/api/catalog/00000000-0000-0000-0000-000000000000").status_code == 404


class TestHealth:
    def test_reports_the_index_provenance(self, client):
        catalog = client.get("/health").json()["catalog"]
        if catalog is None:
            pytest.skip("no card index built")
        # "Which dump is this art from" has to be answerable in one request.
        assert catalog["source_name"]
        assert catalog["rows"] > 0

    def test_reports_how_much_art_is_cached(self, client):
        art = client.get("/health").json()["art"]
        assert art["known"] > 0
        assert art["artless"] >= 0
        assert art["cached"] >= 0

    def test_reports_the_backfill(self, client):
        """How far the crawl got and when, and how often this process still
        went to the lazy fill -- the number the store exists to zero."""
        body = client.get("/health")
        store = body.json()["art"]["store"]
        assert store["fell_through"] >= 0
        assert "cards.scryfall.io" not in body.text


class TestDegradesWithoutTheArtifacts:
    """A fresh clone has neither the index nor the images and must still play."""

    def test_the_app_boots_and_deals_a_game(self, tmp_path, game_data, monkeypatch):
        monkeypatch.setenv("COMMANDERBLITZ_DATA_DIR", str(tmp_path))
        from commanderblitz.cards import images as images_module

        images_module.load_index.cache_clear()
        try:
            bare = TestClient(create_app(game_data, allow_art_fetch=False))
            assert bare.get("/health").json()["catalog"] is None
            response = bare.post(
                "/api/games",
                json={
                    "seats": [
                        {"deck_id": "aesi", "kind": "human"},
                        {"deck_id": "edgar", "kind": "ai"},
                    ],
                    "seed": 1,
                },
            )
            assert response.status_code == 201
            # Every card reports "no art"; the client draws text frames, which
            # is exactly what it did before any of this existed.
            body = bare.get("/api/images").json()
            assert set(body["images"].values()) == {None}
            assert bare.get("/api/catalog").status_code == 503
        finally:
            images_module.load_index.cache_clear()


class TestCardViewIsUnchanged:
    """The image deliberately does *not* ride along on the state payload."""

    def test_no_image_key_leaked_into_a_card(self, client):
        body = client.post(
            "/api/games",
            json={
                "seats": [
                    {"deck_id": "aesi", "kind": "human"},
                    {"deck_id": "edgar", "kind": "ai"},
                ],
                "seed": 3,
            },
        ).json()
        hand = body["state"]["players"][0]["hand"]
        assert hand, "expected an opening hand to inspect"
        for card in hand:
            leaked = {k for k in card if k in ("image", "art", "art_url", "images")}
            assert not leaked, (
                f"{leaked} appeared on card_view. player_view re-sends every card "
                "on every poll of the AI pump, so a constant belongs in /api/images."
            )

    def test_the_state_payload_names_no_image_host(self, client):
        raw = json.dumps(
            client.post(
                "/api/games",
                json={
                    "seats": [
                        {"deck_id": "aesi", "kind": "human"},
                        {"deck_id": "edgar", "kind": "ai"},
                    ],
                    "seed": 4,
                },
            ).json()
        )
        assert "scryfall" not in raw.lower()
        assert "/art/" not in raw


class TestAPrintingFollowsTheCardsOtherFaces:
    """A deck list names the front; the board can show the back.

    `bloodline_keeper` is what a deck says. The moment it transforms,
    `card_view` starts sending `lord_of_lineage` -- a card id no list mentions.
    Without this the deck's illustration would vanish mid-flip, which is the
    same class of bug `_wanted_ids` was written for.
    """

    def _art(self, client):
        return client.app.state.art

    def test_the_back_face_inherits_the_front_s_printing(self, client, game_data):
        chosen = {"scryfall_id": CHOSEN, "artist": "A"}
        spread = _spread_across_faces(
            {"bloodline_keeper": chosen}, game_data.registry, self._art(client)
        )
        assert spread["lord_of_lineage"] == chosen

    def test_a_face_with_its_own_printing_keeps_it(self, client, game_data):
        """The guard. A meld half or an adventure's other side can be a
        different catalog row, and inheriting onto one fetches the wrong
        picture outright -- not a near miss, a different card."""
        real = self._art(client)
        faked = SimpleNamespace(
            images={
                **real.images,
                "lord_of_lineage": CardArt(
                    card_id="lord_of_lineage", scryfall_id="9" * 8 + "-9999-9999-9999-" + "9" * 12
                ),
            }
        )
        spread = _spread_across_faces(
            {"bloodline_keeper": {"scryfall_id": CHOSEN}}, game_data.registry, faked
        )
        assert "lord_of_lineage" not in spread

    def test_the_back_face_asks_for_the_back_of_that_printing(self, client, game_data):
        # Same uuid, different face: `back` comes off our own registry, because
        # it is the one thing a deck list cannot tell us.
        remote = self._art(client).remote_for("lord_of_lineage", printing=CHOSEN)
        assert remote == f"https://cards.scryfall.io/art_crop/back/1/1/{CHOSEN}.jpg"
