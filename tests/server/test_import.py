"""Importing a Moxfield deck, from a pasted URL to a dealt game.

The network is never touched: ``moxfield.fetch_deck`` takes its opener as an
argument, and every test here passes a fake one. The payload behind that fake is
a **real, trimmed** v3 response (``tests/data/moxfield_deck.json``), for the same
reason ``mini_cards.jsonl`` is real -- the shapes that break this code are the
ones nobody would think to invent, like the em-dash in ``type_line`` and the
``boards.{commanders,mainboard}`` nesting.

Nothing here writes into the repository: ``AUTOMTG_DATA_DIR`` is pointed at a
copy of ``data/`` under ``tmp_path`` first, and the registry caches are cleared
around it, because the env var is read per call and the cache is not.
"""

from __future__ import annotations

import io
import json
import shutil
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from automtg.cards import moxfield
from automtg.cards.registry import (
    DEFAULT_DATA_DIR,
    default_registry,
    server_registry,
)
from automtg.server.app import create_app

PAYLOAD = Path(__file__).resolve().parents[1] / "data" / "moxfield_deck.json"
DECK_URL = "https://moxfield.com/decks/vVdybWVgC0imBOlW63FlTg"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def fake_opener(payload: dict | bytes, *, status: int | None = None):
    """An opener that answers with a canned body, or raises a canned error."""

    def opener(request, timeout=None):
        if status is not None:
            raise urllib.error.HTTPError(request.full_url, status, "nope", {}, None)
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return io.BytesIO(body)

    return opener


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A writable copy of `data/`, so no test can dirty the repository."""
    root = tmp_path / "data"
    for name in ("cards", "decks", "catalog"):
        shutil.copytree(DEFAULT_DATA_DIR / name, root / name, ignore=shutil.ignore_patterns("bulk"))
    (root / "art").mkdir(exist_ok=True)
    monkeypatch.setenv("AUTOMTG_DATA_DIR", str(root))

    from automtg.cards import images as images_module

    default_registry.cache_clear()
    server_registry.cache_clear()
    images_module.load_index.cache_clear()
    yield root
    default_registry.cache_clear()
    server_registry.cache_clear()
    images_module.load_index.cache_clear()


@pytest.fixture
def client(sandbox):
    # `allow_art_fetch=False`: the lazy fill would otherwise reach Scryfall for
    # every generated card the moment a board renders.
    return TestClient(create_app(allow_art_fetch=False))


def do_import(client, payload, *, url=DECK_URL, dry_run=False, status=None, library=None):
    monkey = fake_opener(payload, status=status)
    original = moxfield.fetch_deck

    def patched(public_id, *, opener=None):
        return original(public_id, opener=monkey)

    moxfield.fetch_deck = patched
    try:
        return client.post(
            "/api/decks/import",
            json={"url": url, "dry_run": dry_run},
            headers=as_library(library),
        )
    finally:
        moxfield.fetch_deck = original


def as_library(library: str | None) -> dict[str, str]:
    """The header a browser sends, or nothing at all -- both are real callers."""
    return {} if library is None else {"X-Library-Id": library}


def deck_ids(client, library=None) -> set[str]:
    return {d["id"] for d in client.get("/api/decks", headers=as_library(library)).json()}


# ----------------------------------------------------------------------
# parsing a pasted string
# ----------------------------------------------------------------------


class TestReadingTheLink:
    @pytest.mark.parametrize(
        "text",
        [
            "https://moxfield.com/decks/abc123",
            "http://www.moxfield.com/decks/abc123",
            "moxfield.com/decks/abc123",
            "https://moxfield.com/decks/abc123/primer",
            "  https://moxfield.com/decks/abc123  ",
        ],
    )
    def test_accepts_the_shapes_people_actually_paste(self, text):
        assert moxfield.parse_public_id(text) == "abc123"

    def test_accepts_a_bare_id(self):
        # What somebody who has done this once before will try.
        assert moxfield.parse_public_id("vVdybWVgC0imBOlW63FlTg") == "vVdybWVgC0imBOlW63FlTg"

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "https://example.com/decks/abc", "https://moxfield.com/users/somebody", "!!"],
    )
    def test_rejects_everything_else(self, text):
        assert moxfield.parse_public_id(text) is None


class TestTheFixtureIsWhatWeThink:
    """If the payload drifts, every assertion below becomes meaningless."""

    def test_it_is_a_hundred_card_commander_deck(self, payload):
        deck = moxfield.normalise(payload, "test")
        assert deck.format == "commander"
        assert len(deck.commanders) == 1
        assert deck.total() == 100

    def test_the_type_lines_carry_the_em_dash(self, payload):
        # The separator `split_type_line` has to handle. An ASCII hyphen here
        # would make this fixture prove nothing.
        lines = [
            c["card"]["type_line"]
            for c in payload["boards"]["mainboard"]["cards"].values()
        ]
        assert any("—" in line for line in lines)

    def test_normalising_is_stable(self, payload):
        # A re-import of an unchanged deck must write an identical file, and
        # Moxfield's own key order is not stable.
        assert moxfield.normalise(payload, "t") == moxfield.normalise(payload, "t")


# ----------------------------------------------------------------------
# failures, which is where this feature spends its life
# ----------------------------------------------------------------------


class TestEveryFailureSaysSomethingUseful:
    def test_a_link_that_is_not_a_deck(self, client, payload):
        response = do_import(client, payload, url="https://example.com/nope")
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "bad_url"

    def test_a_private_deck_is_not_a_missing_deck(self, client, payload):
        # 403 and 404 send somebody to two different places -- their Moxfield
        # settings, or the address bar. Collapsing them sends them to neither.
        response = do_import(client, payload, status=403)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "private"
        assert "public" in response.json()["detail"]["detail"]

    def test_a_missing_deck(self, client, payload):
        response = do_import(client, payload, status=404)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"

    def test_an_html_body_reads_as_private(self, client):
        # A Cloudflare interstitial where JSON was promised.
        response = do_import(client, b"<!DOCTYPE html><title>Just a moment</title>")
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "private"

    def test_a_deck_that_is_not_commander(self, client, payload):
        response = do_import(client, {**payload, "format": "modern"})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "not_commander"

    def test_a_list_that_is_not_a_hundred_cards(self, client, payload):
        trimmed = json.loads(json.dumps(payload))
        cards = trimmed["boards"]["mainboard"]["cards"]
        for key in list(cards)[:3]:
            del cards[key]
        response = do_import(client, trimmed)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "bad_size"
        assert "100" in response.json()["detail"]["detail"]

    def test_a_card_the_catalog_has_never_heard_of(self, client, payload):
        renamed = json.loads(json.dumps(payload))
        entry = next(iter(renamed["boards"]["mainboard"]["cards"].values()))
        entry["card"]["name"] = "Definitely Not A Real Magic Card"
        response = do_import(client, renamed)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "unknown_cards"
        # Naming the card is the whole point -- "import failed" is useless.
        assert "Definitely Not A Real Magic Card" in response.json()["detail"]["detail"]

    def test_nothing_is_written_when_an_import_fails(self, client, payload, sandbox):
        do_import(client, payload, status=404)
        assert not (sandbox / "generated" / "decks").exists()


# ----------------------------------------------------------------------
# the happy path
# ----------------------------------------------------------------------


class TestAnImportedDeck:
    def test_it_reports_what_it_did(self, client, payload):
        body = do_import(client, payload).json()
        assert body["total"] == 100
        assert body["playable"] + body["simplified"] == 100
        # A real deck is mostly cards nobody hand-wrote, so this is not zero.
        assert body["simplified"] > 0
        assert len(body["cards"]) == 89

    def test_every_simplified_card_explains_itself(self, client, payload):
        body = do_import(client, payload).json()
        for card in body["cards"]:
            if card["origin"] == "partial":
                assert card["notes"], f"{card['name']} is simplified but says nothing"

    def test_it_reuses_hand_written_cards_rather_than_generating_them(self, client, payload):
        body = do_import(client, payload).json()
        native = {c["name"] for c in body["cards"] if c["origin"] == "native"}
        # The precons ship basics, so an imported deck's Forests are `forest` --
        # real rules, existing art, no duplicate definition.
        assert native, "nothing was reused from data/cards/"
        forest = next((c for c in body["cards"] if c["name"] == "Forest"), None)
        if forest is not None:
            assert forest["card_id"] == "forest"

    def test_it_counts_the_lands_that_actually_make_mana(self, client, payload):
        body = do_import(client, payload).json()
        assert body["lands"] > 0
        assert body["lands_producing_mana"] <= body["lands"]

    def test_a_land_that_makes_no_mana_is_only_inert_if_it_does_nothing(self, client, payload):
        """The two counts answer different questions, and only one is a warning.

        A fetchland has no mana ability and never will -- that is what the card
        says. Reporting it as a hole in the mana base would flag a working card
        forever, so `lands_inert` counts abilities rather than mana.
        """
        body = do_import(client, payload).json()
        assert body["lands_inert"] <= body["lands"] - body["lands_producing_mana"]

    def test_it_appears_in_the_deck_list_without_a_restart(self, client, payload):
        deck_id = do_import(client, payload).json()["deck"]["id"]
        decks = {d["id"]: d for d in client.get("/api/decks").json()}
        assert deck_id in decks
        assert decks[deck_id]["source"] == "moxfield"
        assert decks[deck_id]["card_count"] == 100

    def test_the_precons_are_still_there(self, client, payload):
        do_import(client, payload)
        decks = {d["id"] for d in client.get("/api/decks").json()}
        assert {"aesi", "edgar"} <= decks

    def test_a_dry_run_writes_nothing(self, client, payload, sandbox):
        body = do_import(client, payload, dry_run=True).json()
        assert body["total"] == 100
        assert not (sandbox / "generated" / "decks").exists()
        assert body["deck"]["id"] not in {d["id"] for d in client.get("/api/decks").json()}

    def test_a_dry_run_still_reports_the_mana_base(self, client, payload):
        """The dry run is exactly when the mana base matters.

        Counting it off the server's registry would give zero here, because a
        dry run writes nothing for the registry to have seen -- and "37 lands, 0
        make mana" on the one screen meant to inform the decision is worse than
        not showing it at all.
        """
        dry = do_import(client, payload, dry_run=True).json()
        assert dry["lands"] > 0
        wet = do_import(client, payload).json()
        assert (dry["lands"], dry["lands_producing_mana"], dry["lands_inert"]) == (
            wet["lands"],
            wet["lands_producing_mana"],
            wet["lands_inert"],
        )

    def test_re_importing_is_idempotent(self, client, payload, sandbox):
        first = do_import(client, payload).json()
        pool = (sandbox / "generated" / "cards" / "pool.cards.json").read_text(encoding="utf-8")
        second = do_import(client, payload).json()
        assert first["deck"]["id"] == second["deck"]["id"]
        assert first["cards"] == second["cards"]
        # Byte-identical: ids are derived from names, never from a counter.
        assert (sandbox / "generated" / "cards" / "pool.cards.json").read_text(
            encoding="utf-8"
        ) == pool
        # One more than ships, not a literal: precons get added over time and
        # this test is about the import not duplicating itself.
        assert len(client.get("/api/decks").json()) == len(default_registry().decks) + 1


class TestTheImportedDeckIsPlayable:
    def test_a_game_deals_from_it(self, client, payload):
        """The point of persisting rather than holding a deck in memory.

        The imported deck is a `deck_id` like any other, so this goes through
        `POST /api/games` with no new code path at all.
        """
        deck_id = do_import(client, payload).json()["deck"]["id"]
        response = client.post(
            "/api/games",
            json={"seats": [
                {"deck_id": deck_id, "kind": "human"},
                {"deck_id": "aesi", "kind": "ai", "agent": "random"},
            ], "seed": 7},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        seat = body["your_seat"]
        assert len(body["state"]["players"][seat]["hand"]) == 7
        assert body["actions"]

    def test_its_commander_is_in_the_command_zone(self, client, payload):
        deck_id = do_import(client, payload).json()["deck"]["id"]
        body = client.post(
            "/api/games",
            json={"seats": [
                {"deck_id": deck_id, "kind": "human"},
                {"deck_id": "edgar", "kind": "ai", "agent": "random"},
            ], "seed": 3},
        ).json()
        seat = body["your_seat"]
        commanders = body["state"]["players"][seat]["command"]
        assert len(commanders) == 1
        # Generated or not, it is a real legendary creature the engine can cast.
        assert "Legendary" in commanders[0]["type_line"]

    def test_its_art_is_served_from_this_server(self, client, payload):
        # Generated cards get their images the same way authored ones do: a
        # local path, never a cards.scryfall.io URL in the payload.
        do_import(client, payload)
        images = client.get("/api/images").text
        assert "cards.scryfall.io" not in images


class TestDeleting:
    def test_an_imported_deck_can_be_removed(self, client, payload):
        deck_id = do_import(client, payload).json()["deck"]["id"]
        assert client.delete(f"/api/decks/{deck_id}").status_code == 204
        assert deck_id not in {d["id"] for d in client.get("/api/decks").json()}

    def test_a_precon_cannot(self, client):
        response = client.delete("/api/decks/aesi")
        assert response.status_code == 400
        assert "aesi" in {d["id"] for d in client.get("/api/decks").json()}

    def test_deleting_something_that_is_not_there(self, client):
        assert client.delete("/api/decks/mox_nope").status_code == 404


class TestLibraries:
    """Whose deck is whose.

    There are no accounts in this server, so ownership is a random id the browser
    keeps in its own ``localStorage`` and sends as ``X-Library-Id``.  These tests
    are the whole of what that buys: an import is yours, other people's imports
    are not on your rack, and you cannot throw away somebody else's.

    ``None`` for a library is not an edge case being tolerated -- it is the CLI,
    it is ``curl``, and it is a browser with storage switched off.  It gets the
    shared view, which is what every test above this line already assumes.
    """

    def test_an_import_is_stamped_with_the_library_that_asked(self, client, payload, sandbox):
        deck_id = do_import(client, payload, library="alice").json()["deck"]["id"]
        written = json.loads(
            (sandbox / "generated" / "decks" / f"{deck_id}.deck.json").read_text(
                encoding="utf-8"
            )
        )
        assert written["owner"] == "alice"

    def test_your_deck_is_yours_alone(self, client, payload):
        deck_id = do_import(client, payload, library="alice").json()["deck"]["id"]
        assert deck_id in deck_ids(client, "alice")
        assert deck_id not in deck_ids(client, "bob")
        # Not even to a caller with no library at all: an owned deck is owned,
        # and "I sent no header" is not a skeleton key.
        assert deck_id not in deck_ids(client)

    def test_precons_belong_to_everybody(self, client, payload):
        do_import(client, payload, library="alice")
        for who in ("alice", "bob", None):
            assert "aesi" in deck_ids(client, who)

    def test_an_import_from_before_libraries_stays_shared(self, client, payload):
        """The decks already on somebody's disk have no owner recorded.

        Hiding those would make them invisible *and* undeletable -- the one state
        this whole change exists to get rid of -- so an ownerless import is
        everybody's, and anybody may clean it up.
        """
        deck_id = do_import(client, payload).json()["deck"]["id"]
        for who in ("alice", "bob", None):
            assert deck_id in deck_ids(client, who)

    def test_you_cannot_throw_away_somebody_elses_deck(self, client, payload):
        deck_id = do_import(client, payload, library="alice").json()["deck"]["id"]

        refused = client.delete(f"/api/decks/{deck_id}", headers=as_library("bob"))
        assert refused.status_code == 403
        assert deck_id in deck_ids(client, "alice"), "a refused delete must not delete"

        assert (
            client.delete(f"/api/decks/{deck_id}", headers=as_library("alice")).status_code == 204
        )
        assert deck_id not in deck_ids(client, "alice")

    def test_anybody_may_clean_up_an_ownerless_deck(self, client, payload):
        deck_id = do_import(client, payload).json()["deck"]["id"]
        assert client.delete(f"/api/decks/{deck_id}", headers=as_library("bob")).status_code == 204

    def test_a_precon_is_still_a_precon_to_its_owner(self, client):
        """Which of the two refusals a precon gets, and it is not the ownership one.

        ``aesi`` has no owner, so the ownership check would wave it through; the
        400 is what stops it, and getting that order wrong would answer "that is
        not yours" to somebody asking why they cannot delete a shipped deck.
        """
        response = client.delete("/api/decks/aesi", headers=as_library("alice"))
        assert response.status_code == 400
        assert "ships with the engine" in response.json()["detail"]

    def test_the_last_importer_owns_it(self, client, payload):
        """Two people pasting one URL is a collision the deck id cannot avoid.

        ``deck_id_for`` is derived from the Moxfield public id, so the second
        import lands on the first one's file. It takes it: the alternative is
        handing somebody an import they are not allowed to see.
        """
        deck_id = do_import(client, payload, library="alice").json()["deck"]["id"]
        do_import(client, payload, library="bob")
        assert deck_id in deck_ids(client, "bob")
        assert deck_id not in deck_ids(client, "alice")


class TestNoTestWritesIntoTheRepository:
    def test_the_real_data_directory_is_untouched(self, client, payload):
        """The fixture's deck must not land in the developer's own `data/`.

        Asserted on *this deck's* file rather than on the directory being empty:
        `data/generated/` is where a real import goes, so anyone who has actually
        used the feature has decks in there, and a test that fails because the
        developer imported something is a test that gets deleted.
        """
        before = sorted((DEFAULT_DATA_DIR / "generated" / "decks").glob("*.deck.json"))
        deck_id = do_import(client, payload).json()["deck"]["id"]
        after = sorted((DEFAULT_DATA_DIR / "generated" / "decks").glob("*.deck.json"))
        assert after == before
        assert not (DEFAULT_DATA_DIR / "generated" / "decks" / f"{deck_id}.deck.json").exists()
