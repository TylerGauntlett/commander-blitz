"""Every card the engine ships, matched to a printing -- or honestly not.

These run against the **committed** ``data/catalog/`` artifacts and touch no
network.  They are the gate that stops a card silently losing its art: the
failure mode this guards against is not an exception, it is a board that quietly
renders one more grey plate than it did yesterday.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.images import (
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
from commanderblitz.cards.registry import default_registry

#: Cards in ``data/cards/`` that are original designs with no printing anywhere.
#:
#: **Empty, and that is the claim.** It used to hold five: the Aesi deck carried
#: invented cards wearing real cards' ids -- "Tidal Broodmaster" under
#: ``hydra_broodmaster``, "Gyre Strait Leviathan" under ``aetherling_serpent``.
#: They existed because the deck was a hand-curated approximation of the Aesi
#: precon rather than the precon, and they went when the real list shipped.
#:
#: So an entry appearing here now means a real card stopped resolving, which is
#: a bug -- there is no longer such a thing as a card in this pool without a
#: printing to check it against.
KNOWN_ARTLESS: frozenset[str] = frozenset()

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

    def test_no_card_in_the_pool_is_artless(self, registry, index):
        """Was "exactly the known customs are artless", over a frozen set of
        five. The five were invented cards in the hand-curated Aesi list and
        went with it, so the claim is now the stronger one: every card here has
        a printing to be checked against."""
        artless = {card.id for card in registry if resolve(card, index) is None}
        assert artless == KNOWN_ARTLESS == frozenset()


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
