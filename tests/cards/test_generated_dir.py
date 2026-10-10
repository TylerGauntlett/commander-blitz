"""``AUTOMTG_GENERATED_DIR``: where runtime writes land, apart from the data.

The desktop build runs the server from a read-only AppImage, so imports and
fetched art must be able to go somewhere else without moving the authored
cards, decks and catalog along with them.  Every write path in the package
resolves through ``generated_dir()``; these tests hold it to that.
"""

from __future__ import annotations

import shutil

import pytest

from automtg.cards import images, importer
from automtg.cards.registry import (
    DEFAULT_DATA_DIR,
    data_dir,
    default_registry,
    generated_dir,
    load_game_data,
    server_registry,
)


@pytest.fixture
def clean_registries():
    default_registry.cache_clear()
    server_registry.cache_clear()
    yield
    default_registry.cache_clear()
    server_registry.cache_clear()


def test_default_is_under_data_dir(monkeypatch):
    monkeypatch.delenv("AUTOMTG_DATA_DIR", raising=False)
    monkeypatch.delenv("AUTOMTG_GENERATED_DIR", raising=False)
    assert generated_dir() == data_dir() / "generated"
    assert data_dir() == DEFAULT_DATA_DIR


def test_override_moves_every_runtime_write(tmp_path, monkeypatch):
    monkeypatch.delenv("AUTOMTG_DATA_DIR", raising=False)
    monkeypatch.setenv("AUTOMTG_GENERATED_DIR", str(tmp_path))

    # Every path an import or a lazy art fill writes to.
    for path in (
        importer.cards_path(),
        importer.coverage_path(),
        importer.decks_dir(),
        images.generated_images_path(),
        images.art_cache_dir(),
    ):
        assert path.is_relative_to(tmp_path), path

    # ...and nothing the server only reads has moved.
    assert data_dir() == DEFAULT_DATA_DIR
    assert images.art_dir() == DEFAULT_DATA_DIR / "art"
    assert not images.catalog_path().is_relative_to(tmp_path)


def test_server_registry_reads_decks_from_the_override(tmp_path, monkeypatch, clean_registries):
    monkeypatch.delenv("AUTOMTG_DATA_DIR", raising=False)
    monkeypatch.delenv("AUTOMTG_FIXTURE_DECKS", raising=False)
    monkeypatch.setenv("AUTOMTG_GENERATED_DIR", str(tmp_path))

    # A retired fixture list: legal, every card authored, and not in the
    # catalogue unless the fixtures are asked for -- so finding it proves it
    # came from the override.
    decks = tmp_path / "decks"
    decks.mkdir()
    shutil.copy(DEFAULT_DATA_DIR / "decks" / "fixtures" / "aesi.deck.json", decks)

    assert "aesi" not in load_game_data(include_generated=False).decks
    assert "aesi" in load_game_data(include_generated=True).decks
    assert "aesi" in server_registry().decks
