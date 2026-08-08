"""Every card the engine ships, matched to a printing -- or honestly not.

These run against the **committed** ``data/catalog/`` artifacts and touch no
network.  They are the gate that stops a card silently losing its art: the
failure mode this guards against is not an exception, it is a board that quietly
renders one more grey plate than it did yesterday.
"""

from __future__ import annotations

import pytest

from automtg.cards.images import (
    CardArt,
    build_registry_images,
    catalog_path,
    load_index,
    read_registry_images,
    registry_images_path,
    resolve,
    strip_token_suffix,
    token_key,
)
from automtg.cards.registry import default_registry

#: The five cards in ``data/cards/`` that are original designs with no printing
#: anywhere.  Frozen deliberately: a *sixth* entry appearing here means a real
#: card stopped resolving, which is a bug, not a new custom card.
KNOWN_ARTLESS = frozenset(
    {
        "aetherling_serpent",  # "Gyre Strait Leviathan"
        "hydra_broodmaster",  # "Tidal Broodmaster"
        "kiora_growth_surge",  # "Surge of Growth"
        "kraken_hatchling_swarm",  # "Whelming Tide"
        "overrun_lite",  # "Wave of Growth"
    }
)

pytestmark = pytest.mark.skipif(
    not catalog_path().exists(),
    reason="no card index built; run scripts/build_card_index.py",
)


@pytest.fixture(scope="module")
def index():
    return load_index()


@pytest.fixture(scope="module")
def registry():
    return default_registry().registry


class TestTokenNaming:
    """The rule that a plain suffix strip gets wrong, and gets wrong silently."""

    def test_a_token_is_named_by_its_subtypes(self, registry):
        assert token_key(registry.get("vampire_1_1_b_lifelink")) == "Vampire"

    def test_multiple_subtypes_join_in_printed_order(self, registry):
        # `build_type_line` sorts subtypes alphabetically, and so does Scryfall.
        assert token_key(registry.get("frog_lizard_3_3_g")) == "Frog Lizard"

    def test_stripping_the_suffix_alone_would_have_missed_it(self, registry, index):
        # The regression this whole rule exists for. "Vampire Lifelink Token"
        # minus " Token" is "Vampire Lifelink", which has no printing at all --
        # so the card would have fallen back to the no-art plate forever, with
        # nothing anywhere reporting a problem.
        card = registry.get("vampire_1_1_b_lifelink")
        assert index.lookup(strip_token_suffix(card.name), token=True) is None
        assert index.lookup(token_key(card), token=True) is not None

    def test_the_token_resolves(self, registry, index):
        entry = resolve(registry.get("vampire_1_1_b_lifelink"), index)
        assert entry is not None
        assert entry.name == "Vampire"
        assert entry.is_token


class TestResolution:
    def test_a_basic_land_resolves(self, registry, index):
        assert resolve(registry.get("forest"), index).name == "Forest"

    def test_a_commander_resolves(self, registry, index):
        entry = resolve(registry.get("aesi_tyrant_of_gyre_strait"), index)
        assert entry.name == "Aesi, Tyrant of Gyre Strait"
        assert entry.art_url().startswith("https://cards.scryfall.io/art_crop/")

    def test_a_custom_card_resolves_to_nothing(self, registry, index):
        # Not a failure: the client draws a deliberate plate for these.
        assert resolve(registry.get("aetherling_serpent"), index) is None

    def test_exactly_the_known_customs_are_artless(self, registry, index):
        artless = {card.id for card in registry if resolve(card, index) is None}
        assert artless == KNOWN_ARTLESS


class TestTheCommittedArtifact:
    def test_it_exists(self):
        assert registry_images_path().exists(), (
            "run scripts/build_card_index.py to regenerate registry_images.json"
        )

    def test_every_engine_card_has_an_entry(self, registry):
        images = read_registry_images()
        missing = sorted(set(registry.ids()) - set(images))
        assert not missing, f"cards absent from registry_images.json: {missing}"

    def test_no_stale_entries(self, registry):
        images = read_registry_images()
        extra = sorted(set(images) - set(registry.ids()))
        assert not extra, f"registry_images.json names cards the engine dropped: {extra}"

    def test_it_agrees_with_a_fresh_resolution(self, registry, index):
        # The committed file is generated, so it can go stale against the index
        # sitting next to it. This is what notices.
        assert read_registry_images() == build_registry_images(registry, index)

    def test_artless_entries_are_present_and_explicitly_empty(self):
        images = read_registry_images()
        for card_id in KNOWN_ARTLESS:
            assert card_id in images
            assert images[card_id].has_printing is False
            assert images[card_id].remote_url() is None

    def test_resolved_entries_carry_an_artist(self):
        images = read_registry_images()
        resolved = [art for art in images.values() if art.has_printing]
        assert len(resolved) >= 140
        # The preview rail credits the artist; a null here is a blank line there.
        assert all(art.artist for art in resolved)


class TestCardArt:
    def test_an_artless_card_has_no_url(self):
        assert CardArt(card_id="x").remote_url() is None

    def test_a_resolved_card_derives_both_sizes(self):
        art = CardArt(card_id="x", scryfall_id="0000419b-0bba-4488-8f7a-6194544ce91e")
        assert "/art_crop/" in art.remote_url()
        assert "/normal/" in art.remote_url("normal")
