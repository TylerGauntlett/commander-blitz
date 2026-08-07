"""Commander construction rules for the shipped decks."""

from __future__ import annotations

import pytest

from automtg.cards.registry import (
    COMMANDER_DECK_SIZE,
    CardRegistry,
    DeckList,
    load_decks,
    validate_deck,
)

DECK_IDS = sorted(load_decks())


@pytest.fixture(scope="module")
def decks() -> dict[str, DeckList]:
    return load_decks()


class TestDecksAreLegal:
    def test_both_decks_exist(self, decks):
        assert set(decks) == {"aesi", "edgar"}

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_deck_is_commander_legal(self, deck_id, decks, real_registry: CardRegistry):
        problems = validate_deck(decks[deck_id], real_registry)
        assert problems == [], f"{deck_id}: " + "; ".join(problems)

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_deck_has_exactly_one_hundred_cards(self, deck_id, decks):
        assert decks[deck_id].total_cards() == COMMANDER_DECK_SIZE

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_singleton_except_basic_lands(self, deck_id, decks, real_registry):
        for card_id, qty in decks[deck_id].cards:
            if qty > 1:
                assert real_registry.get(card_id).is_basic, (
                    f"{deck_id}: {card_id} appears {qty} times but is not a basic land"
                )

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_colour_identity_is_respected(self, deck_id, decks, real_registry):
        deck = decks[deck_id]
        identity: set[str] = set()
        for commander_id in deck.commanders:
            identity |= set(real_registry.get(commander_id).color_identity)
        for card_id, _ in deck.cards:
            card = real_registry.get(card_id)
            assert set(card.color_identity) <= identity, (
                f"{deck_id}: {card_id} is {sorted(card.color_identity)}, "
                f"outside {sorted(identity)}"
            )

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_commander_is_a_legendary_creature(self, deck_id, decks, real_registry):
        for commander_id in decks[deck_id].commanders:
            card = real_registry.get(commander_id)
            assert card.is_legendary and card.is_creature

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_deck_has_a_playable_mana_base(self, deck_id, decks, real_registry):
        """A deck that cannot cast its own cards is legal but useless."""
        lands = sum(
            qty for card_id, qty in decks[deck_id].cards if real_registry.get(card_id).is_land
        )
        assert 33 <= lands <= 42, f"{deck_id} runs {lands} lands"

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_no_tokens_in_the_deck_list(self, deck_id, decks, real_registry):
        for card_id, _ in decks[deck_id].cards:
            assert not real_registry.get(card_id).is_token

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_substitutions_are_documented(self, deck_id, decks):
        """Every swap made for DSL reasons must record what it replaced and why."""
        for sub in decks[deck_id].substitutions:
            assert sub["slot"] and sub["replaced_with"] and sub["reason"]

    @pytest.mark.parametrize("deck_id", DECK_IDS)
    def test_curve_is_not_absurd(self, deck_id, decks, real_registry):
        spells = [
            real_registry.get(card_id)
            for card_id, qty in decks[deck_id].cards
            for _ in range(qty)
            if not real_registry.get(card_id).is_land
        ]
        average = sum(c.mana_value for c in spells) / len(spells)
        assert 2.0 <= average <= 4.5, f"{deck_id} average mana value is {average:.2f}"


class TestDeckIdentity:
    def test_aesi_is_a_landfall_deck(self, decks, real_registry):
        """The deck should actually do what its commander rewards."""
        deck = decks["aesi"]
        landfall = 0
        for card_id, _ in deck.cards:
            card = real_registry.get(card_id)
            for ability in card.abilities:
                trigger = ability.trigger
                if trigger is None:
                    continue
                if trigger.event == "land_played" or (trigger.event == "permanent_enters" and (trigger.filter or {}).get(
                    "types"
                ) == ["Land"]):
                    landfall += 1
        assert landfall >= 5, f"only {landfall} landfall payoffs"

    def test_edgar_is_a_vampire_deck(self, decks, real_registry):
        deck = decks["edgar"]
        vampires = sum(
            1
            for card_id, _ in deck.cards
            if "Vampire" in real_registry.get(card_id).subtypes
        )
        assert vampires >= 25, f"only {vampires} vampires"
