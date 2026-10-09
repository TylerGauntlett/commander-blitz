"""Commander construction rules for the shipped decks."""

from __future__ import annotations

import pytest

from automtg.cards.registry import (
    COMMANDER_DECK_SIZE,
    CardRegistry,
    DeckList,
    fixture_decks_dir,
    load_decks,
    validate_deck,
)

#: The precons a player sees in the catalogue.
PRECONS = {
    "aesi_tyrant_of_gyre_strait",
    "atraxa_praetors_voice",
    "bard_king_of_dale",
    "blor_the_impervious",
    "bruvac_the_grandiloquent",
    "edgar_markov",
    "giada_font_of_hope",
    "isperia",
    "sheoldred_the_apocalypse",
    "the_ur_dragon",
    "vivi_ornitier",
    "zurgo",
}

#: The retired first Edgar and Aesi lists, kept for the seeded tests.
FIXTURES = {"aesi", "edgar"}


def _all_decks() -> dict[str, DeckList]:
    return {**load_decks(), **load_decks(fixture_decks_dir())}


DECK_IDS = sorted(_all_decks())


@pytest.fixture(scope="module")
def decks() -> dict[str, DeckList]:
    return _all_decks()


class TestDecksAreLegal:
    def test_the_shipped_decks_exist(self, decks):
        # `load_decks` reads the authored layer only, so an imported deck on the
        # developer's machine cannot make this fail.
        assert set(load_decks()) == PRECONS
        assert set(load_decks(fixture_decks_dir())) == FIXTURES

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
                card = real_registry.get(card_id)
                # 903.5b exempts basic lands, and a card whose own text says so
                # -- with no limit (Persistent Petitioners) or up to a printed
                # number (Nazgul). Asked with the same predicate `validate_deck`
                # uses, so the two cannot drift apart.
                limit = card.deck_copy_limit
                assert limit is None or qty <= limit, (
                    f"{deck_id}: {card_id} appears {qty} times, over its limit of {limit}"
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
        # The upper bound was 42 while every shipped deck was hand-built to 37.
        # `aesi` is now the Reap the Tides precon exactly as printed, and it
        # runs 44 -- Wizards builds precons land-heavy, and 30 of those are
        # basics. Raised rather than special-cased: the assertion is meant to
        # catch a deck that cannot cast its own cards, and 44 is not that.
        # The floor went to 30 for the same reason: Bruvac's mill list runs 30
        # lands on a 2.4 curve and Bard's 32 on 3.0, and both are real lists.
        assert 30 <= lands <= 45, f"{deck_id} runs {lands} lands"

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

    def test_isperia_is_a_deck_that_wants_to_be_attacked(self, decks, real_registry):
        """Isperia turns an attack aimed at you into a card.

        A deck built around that has to survive being attacked, or the trigger
        never fires twice. So the test is about the *defence*: enough blockers
        and sweepers that swinging at this seat is the worst option on the table.
        """
        deck = decks["isperia"]
        cards = [real_registry.get(cid) for cid, _ in deck.cards]
        blockers = [c for c in cards if c.is_creature and c.toughness >= 3]
        assert len(blockers) >= 12, f"only {len(blockers)} creatures that block well"
        sweepers = [
            c
            for c in cards
            if any(
                effect.get("op") in ("destroy", "exile", "return_to_hand")
                and (effect.get("objects") or {}).get("count") == "all"
                for effect in c.spell_effects
            )
        ]
        assert len(sweepers) >= 3, f"only {len(sweepers)} sweepers"

    def test_isperia_flies(self, decks, real_registry):
        fliers = sum(
            1
            for card_id, _ in decks["isperia"].cards
            if "flying" in real_registry.get(card_id).keywords
        )
        assert fliers >= 12, f"only {fliers} fliers"

    def test_zurgo_makes_tokens(self, decks, real_registry):
        """Zurgo's engine is a token that dies. The deck has to supply them.

        Mobilize makes one a turn; a deck relying on that alone is one removal
        spell away from doing nothing.
        """
        makers = 0
        for card_id, _ in decks["zurgo"].cards:
            card = real_registry.get(card_id)
            sources = list(card.spell_effects) + [
                effect for ability in card.abilities for effect in ability.effects
            ]
            if any(effect.get("op") == "create_token" for effect in sources):
                makers += 1
        assert makers >= 8, f"only {makers} cards make tokens"

    def test_zurgo_pays_off_a_creature_dying(self, decks, real_registry):
        payoffs = 0
        for card_id, _ in decks["zurgo"].cards:
            card = real_registry.get(card_id)
            for ability in card.abilities:
                trigger = ability.trigger
                if trigger is not None and trigger.event in ("creature_dies", "dies"):
                    payoffs += 1
                    break
        assert payoffs >= 6, f"only {payoffs} death payoffs"
