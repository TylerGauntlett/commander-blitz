"""``source_id``: the Moxfield id a deck came from, kept with its case.

``deck_id_for`` lowercases the public id into a slug and cannot be reversed,
so the id had to be recorded on its own.  The desktop build sends these to the
hosted server so a deck imported at home can be imported there too.
"""

from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from commanderblitz.cards.registry import DeckList, default_registry
from commanderblitz.server.app import create_app
from commanderblitz.server.deckinfo import source_id_of
from tests.server.test_import import do_import
from tests.server.test_import import payload as payload_fixture
from tests.server.test_import import sandbox as sandbox_fixture

sandbox = sandbox_fixture
payload = payload_fixture

PUBLIC_ID = "vVdybWVgC0imBOlW63FlTg"


def test_an_import_records_its_moxfield_id_with_its_case(sandbox, payload):
    client = TestClient(create_app(allow_art_fetch=False))
    body = do_import(client, payload).json()
    assert body["deck"]["source_id"] == PUBLIC_ID
    assert body["deck"]["id"] == f"mox_{PUBLIC_ID.lower()}"

    listed = {d["id"]: d for d in client.get("/api/decks").json()}
    assert listed[body["deck"]["id"]]["source_id"] == PUBLIC_ID


def test_a_precon_has_none():
    data = default_registry()
    assert source_id_of(data.decks["aesi"]) == ""
    client = TestClient(create_app(data))
    assert all(d["source_id"] == "" for d in client.get("/api/decks").json())


def test_a_deck_imported_before_the_field_existed_is_read_from_its_note():
    old = dataclasses.replace(
        default_registry().decks["aesi"],
        source="moxfield",
        notes=f"Imported from Moxfield ({PUBLIC_ID}).",
    )
    assert isinstance(old, DeckList)
    assert source_id_of(old) == PUBLIC_ID


def test_a_moxfield_deck_with_no_note_and_no_field_is_honest():
    old = dataclasses.replace(default_registry().decks["aesi"], source="moxfield", notes="")
    assert source_id_of(old) == ""
