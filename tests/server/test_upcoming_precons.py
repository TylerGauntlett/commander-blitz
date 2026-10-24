"""The coming-soon precons: the manifest's window, minus what already ships.

The shelf represents the whole precon catalog (ADR 0024). A precon whose cards
are not all native yet is a shell: a product name, a release to group it by and
its commander's art, served by printing so the engine need not know the card.
What holds that promise is subtraction: a precon that ships leaves this list
because its deck file loads, never because somebody remembered to edit it.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from commanderblitz.cards.registry import data_dir
from commanderblitz.server.app import create_app
from tests.cards.test_deck_legality import PRECONS


@pytest.fixture(scope="module")
def client() -> TestClient:
    from commanderblitz.cards.registry import default_registry

    return TestClient(create_app(default_registry()))


@pytest.fixture(scope="module")
def manifest() -> list[dict]:
    return json.loads((data_dir() / "decks" / "sources.json").read_text(encoding="utf-8"))["rows"]


@pytest.fixture(scope="module")
def upcoming(client) -> list[dict]:
    response = client.get("/api/precons/upcoming")
    assert response.status_code == 200
    return response.json()


class TestTheShells:
    def test_every_row_that_does_not_ship_is_a_shell(self, upcoming, manifest):
        assert {p["id"] for p in upcoming} == {r["id"] for r in manifest} - PRECONS

    def test_a_shipped_precon_is_not_also_a_shell(self, upcoming, client):
        shipped = {d["id"] for d in client.get("/api/decks").json()}
        assert not shipped & {p["id"] for p in upcoming}

    def test_newest_first(self, upcoming):
        dates = [p["date"] for p in upcoming]
        assert dates == sorted(dates, reverse=True)

    def test_each_names_its_release_and_commanders(self, upcoming):
        for shell in upcoming:
            assert shell["product"] and shell["set_name"] and shell["set_code"]
            assert shell["commanders"], shell["id"]
            for commander in shell["commanders"]:
                assert commander["name"]

    def test_a_commanders_art_is_served_by_its_printing(self, upcoming, manifest):
        rows = {r["id"]: r for r in manifest}
        shell = upcoming[0]
        printing = rows[shell["id"]]["commanders"][0]["scryfall_id"]
        assert shell["commanders"][0]["art_url"] == f"/art/{printing}.jpg"
