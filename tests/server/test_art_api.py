"""Serving card art, and the catalog behind it.

The property under test throughout is **self-ownership**: the browser is only
ever handed a same-origin path, and a game renders with the network unplugged.
Anything that would put a ``cards.scryfall.io`` URL in a response is a
regression, so there is a test that says so directly.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from automtg.cards.images import catalog_path
from automtg.cards.registry import default_registry
from automtg.server.app import create_app
from automtg.server.art import ArtStore

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

    def test_it_leaves_out_cards_no_seat_can_draw(self, client, game_id, game_data):
        scoped = set(client.get(f"/api/images?game_id={game_id}").json()["images"])
        reachable = {c.id for c in game_data.registry if c.is_token}
        for deck_id in ("aesi", "edgar"):
            reachable |= game_data.deck(deck_id).unique_ids()
        assert scoped == reachable

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


class TestDegradesWithoutTheArtifacts:
    """A fresh clone has neither the index nor the images and must still play."""

    def test_the_app_boots_and_deals_a_game(self, tmp_path, game_data, monkeypatch):
        monkeypatch.setenv("AUTOMTG_DATA_DIR", str(tmp_path))
        from automtg.cards import images as images_module

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
