"""The authored layer and the generated layer, and why they stay apart.

Importing a deck writes card definitions and a deck list to ``data/generated/``.
If those could reach ``default_registry()``, three gates would start giving
different answers on different machines: ``test_every_card_works`` parametrises
over the whole pool, ``test_image_resolution`` asserts the artless set is
*exactly* five ids, and ``ai/encoding`` builds an embedding index from
``registry.ids()`` -- so an alphabetically-earlier import would shift every card's
embedding index and a checkpoint would silently read the wrong one.

That makes the separation an invariant rather than a preference, which is why it
has a test file of its own.
"""

from __future__ import annotations

import json
import shutil

import pytest

from commanderblitz.cards import registry as registry_module
from commanderblitz.cards.registry import (
    DEFAULT_DATA_DIR,
    default_registry,
    generated_dir,
    load_game_data,
    server_registry,
)

#: A card that is not in `data/cards/` and never will be, written in the shape
#: the proxy generator emits.
PROXY_CARD = {
    "id": "test_only_proxy_bear",
    "name": "Test Only Proxy Bear",
    "mana_cost": "{1}{G}",
    "types": ["Creature"],
    "subtypes": ["Bear"],
    "power": 2,
    "toughness": 2,
    "color_identity": ["G"],
}


@pytest.fixture
def data_with_an_import(tmp_path, monkeypatch):
    """A copy of `data/` with one generated card and one deck referencing it.

    Copied rather than pointed at, because these tests must be incapable of
    writing into the repository.
    """
    root = tmp_path / "data"
    for name in ("cards", "decks"):
        shutil.copytree(DEFAULT_DATA_DIR / name, root / name)

    gen = root / "generated"
    (gen / "cards").mkdir(parents=True)
    (gen / "decks").mkdir(parents=True)
    (gen / "cards" / "pool.cards.json").write_text(
        json.dumps({"cards": [PROXY_CARD]}), encoding="utf-8"
    )

    # Reuse a real deck's list so the import is legal, swapping one card for the
    # generated one.  A deck that fails validation would not prove anything.
    aesi = json.loads((root / "decks" / "fixtures" / "aesi.deck.json").read_text())
    aesi["id"] = "mox_test"
    aesi["name"] = "Imported Test Deck"
    aesi["cards"][0] = {"id": PROXY_CARD["id"], "qty": aesi["cards"][0]["qty"]}
    (gen / "decks" / "mox_test.deck.json").write_text(json.dumps(aesi), encoding="utf-8")

    monkeypatch.setenv("COMMANDERBLITZ_DATA_DIR", str(root))
    default_registry.cache_clear()
    server_registry.cache_clear()
    yield root
    default_registry.cache_clear()
    server_registry.cache_clear()


class TestTheLayersStayApart:
    def test_the_authored_layer_cannot_see_an_import(self, data_with_an_import):
        data = default_registry()
        assert PROXY_CARD["id"] not in data.registry
        assert "mox_test" not in data.decks

    def test_the_server_layer_sees_both(self, data_with_an_import):
        data = server_registry()
        assert PROXY_CARD["id"] in data.registry
        assert "mox_test" in data.decks
        # ...and has not lost the authored cards in the process.
        assert "forest" in data.registry
        assert "zurgo" in data.decks

    def test_a_generated_card_compiles_like_any_other(self, data_with_an_import):
        card = server_registry().registry.get(PROXY_CARD["id"])
        assert card.name == "Test Only Proxy Bear"
        assert card.mana_value == 2
        assert card.type_line.startswith("Creature")


class TestAnAuthoredCardSupersedesItsOwnProxy:
    """What happens when the card pipeline implements a card somebody imported.

    An imported deck writes a proxy for every card nobody had written yet. The
    authoring pipeline then implements some of those. Both files now define the
    same id, and `CardRegistry.from_paths` raises on a duplicate -- so without
    the skip, the server stops booting the first time the two meet. It is not a
    hypothetical: it happened the moment 280 cards were authored, on
    `simic_guildgate`.

    The deck keeps referencing the id either way, so it silently picks up the
    real rules. Which is exactly what should happen.
    """

    @pytest.fixture
    def collision(self, tmp_path, monkeypatch):
        root = tmp_path / "data"
        for name in ("cards", "decks"):
            shutil.copytree(DEFAULT_DATA_DIR / name, root / name)

        # A proxy for a card that also exists in the authored pool.
        gen = root / "generated" / "cards"
        gen.mkdir(parents=True)
        inert = {
            "id": "forest",
            "name": "Forest",
            "supertypes": ["Basic"],
            "types": ["Land"],
            "subtypes": ["Forest"],
        }
        (gen / "pool.cards.json").write_text(
            json.dumps({"cards": [inert]}), encoding="utf-8"
        )
        monkeypatch.setenv("COMMANDERBLITZ_DATA_DIR", str(root))
        default_registry.cache_clear()
        server_registry.cache_clear()
        yield root
        default_registry.cache_clear()
        server_registry.cache_clear()

    def test_the_pool_still_loads(self, collision):
        data = load_game_data(include_generated=True)
        assert "forest" in data.registry

    def test_the_authored_card_wins(self, collision):
        # The proxy has no mana ability; the real Forest does. Getting this
        # backwards would leave every deck's basics unable to make mana.
        card = load_game_data(include_generated=True).registry.get("forest")
        assert any(a.is_mana_ability for a in card.abilities)


class TestNameResolutionPrefersTheAuthoredCard:
    def test_an_import_cannot_shadow_a_hand_written_card(self, tmp_path, monkeypatch):
        """The whole reason `load_game_data` loads the authored paths first.

        A generated "Forest" that shadowed the real one would replace every
        land in every precon with an inert permanent, and nothing would say so.
        """
        root = tmp_path / "data"
        for name in ("cards", "decks"):
            shutil.copytree(DEFAULT_DATA_DIR / name, root / name)
        gen = root / "generated" / "cards"
        gen.mkdir(parents=True)
        impostor = {**PROXY_CARD, "id": "forest_impostor", "name": "Forest"}
        (gen / "pool.cards.json").write_text(
            json.dumps({"cards": [impostor]}), encoding="utf-8"
        )

        monkeypatch.setenv("COMMANDERBLITZ_DATA_DIR", str(root))
        registry = load_game_data(include_generated=True).registry
        assert registry.by_name("Forest").id == "forest"


class TestTheDirectoryIsNotCommitted:
    def test_the_generated_directory_ignores_itself(self):
        # If this file goes missing, a single import turns `git status` into a
        # hundred machine-written card definitions.
        ignore = generated_dir() / ".gitignore"
        assert ignore.exists()
        assert "*" in ignore.read_text(encoding="utf-8").split()

    def test_a_missing_generated_directory_is_not_an_error(self, tmp_path, monkeypatch):
        # The common case: a fresh clone that has never imported anything.
        root = tmp_path / "data"
        for name in ("cards", "decks"):
            shutil.copytree(DEFAULT_DATA_DIR / name, root / name)
        monkeypatch.setenv("COMMANDERBLITZ_DATA_DIR", str(root))
        assert not (root / "generated").exists()
        data = load_game_data(include_generated=True)
        assert "zurgo" in data.decks


def test_the_module_exposes_both_loaders():
    # Guards against a refactor quietly collapsing them back into one.
    assert registry_module.default_registry is not registry_module.server_registry
