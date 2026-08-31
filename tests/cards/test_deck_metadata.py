"""The lobby's deck metadata: the authored half and the derived half.

The authored half -- tags, ratings, strategy, signature cards -- is editorial
copy that nothing else in the codebase reads, which is exactly the sort of thing
that rots silently.  ``TestSignatureCardsResolve`` is the gate: a signature card
that is renamed or dropped from the deck list fails here rather than rendering a
blank frame in the dossier six months later.

The derived half -- curve, land count, swap count -- comes from the deck list at
request time, so it cannot drift.  What is worth testing there is that the
derivation is the *right* one, which is what the explicit 37 below pins.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from automtg.cards.registry import CardRegistry, DeckList, default_registry, load_decks
from automtg.server.app import create_app

SHIPPED = sorted(load_decks())


@pytest.fixture(scope="module")
def decks() -> dict[str, DeckList]:
    return load_decks()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(default_registry(), allow_art_fetch=False))


class TestAuthoredFields:
    @pytest.mark.parametrize("deck_id", SHIPPED)
    def test_every_shipped_deck_is_described(self, deck_id, decks):
        deck = decks[deck_id]
        assert deck.tags, f"{deck_id} has no tags"
        assert deck.strategy, f"{deck_id} has no strategy paragraph"
        assert deck.ratings is not None, f"{deck_id} has no ratings"
        assert deck.signature, f"{deck_id} has no signature cards"

    @pytest.mark.parametrize("deck_id", SHIPPED)
    def test_ratings_are_on_a_one_to_four_scale(self, deck_id, decks):
        ratings = decks[deck_id].ratings
        assert set(ratings) == {
            "speed",
            "complexity",
            "interaction",
            "resilience",
            "pilot",
        }
        for axis, value in ratings.items():
            assert 1 <= value <= 4, f"{deck_id}.{axis} = {value}"


class TestSignatureCardsResolve:
    """The gate that stops the editorial fields rotting."""

    @pytest.mark.parametrize("deck_id", SHIPPED)
    def test_every_signature_card_is_a_real_card(
        self, deck_id, decks, real_registry: CardRegistry
    ):
        for row in decks[deck_id].signature:
            assert row["card_id"] in real_registry, f"{deck_id}: {row['card_id']}"

    @pytest.mark.parametrize("deck_id", SHIPPED)
    def test_every_signature_card_is_actually_in_the_deck(self, deck_id, decks):
        """A card the deck does not run is not its signature card."""
        deck = decks[deck_id]
        for row in deck.signature:
            assert row["card_id"] in deck.unique_ids(), f"{deck_id}: {row['card_id']}"

    @pytest.mark.parametrize("deck_id", SHIPPED)
    def test_every_signature_card_says_why(self, deck_id, decks):
        for row in decks[deck_id].signature:
            assert row["why"].strip(), f"{deck_id}: {row['card_id']} has no reason"


class TestDerivedFields:
    def test_the_curve_accounts_for_every_nonland_card(self, client, decks):
        for deck_id in SHIPPED:
            detail = client.get(f"/api/decks/{deck_id}").json()
            nonland = sum(qty for _, qty in decks[deck_id].cards) - detail["lands"]
            assert sum(detail["curve"]) == nonland, deck_id

    def test_the_curve_has_seven_buckets(self, client):
        assert len(client.get("/api/decks/aesi").json()["curve"]) == 7

    def test_lands_are_counted(self, client):
        # Hand-counted from the list.  A derived number that nothing pins is a
        # number that can silently start counting the wrong thing.
        # 44 since `aesi` became the printed Reap the Tides list: 15 Forests,
        # 15 Islands and 14 others.
        assert client.get("/api/decks/aesi").json()["lands"] == 44

    def test_no_shipped_deck_has_a_substitution_left(self, client, decks):
        """All four are the printed precons now.

        `aesi` got there first; `edgar` was the last, and its seven swaps came
        out one mechanic at a time -- gain-control, tap-permanents, add-subtype,
        shares-a-type, top-of-library-revealed and transform. A swap reappearing
        here means a card stopped being expressible, which is worth a failing
        test even though the field is derived and would report it honestly.
        """
        for deck_id in decks:
            detail = client.get(f"/api/decks/{deck_id}").json()
            assert detail["swaps"] == len(decks[deck_id].substitutions) == 0, deck_id
            assert detail["swap_note"] == "", deck_id

    def test_the_note_still_says_what_a_swap_would_mean(self, game_data):
        """The derivation outlives the last deck that needed it.

        `swap_note` exists so that deleting a substitution from a deck file is
        the *only* edit needed when a card becomes expressible -- which is
        exactly what just happened seven times. With no shipped deck left to
        exercise it, it is tested against a synthetic pair rather than deleted.
        """
        from automtg.server.deckinfo import swap_note

        one = swap_note([{"slot": "mortify"}], game_data)
        assert "1 card swapped" in one
        assert "Mortify" in one

        two = swap_note([{"slot": "mortify"}, {"slot": "bedevil"}], game_data)
        assert "2 cards swapped" in two
        assert "Mortify and Bedevil" in two

    def test_signature_cards_carry_a_name_and_art(self, client):
        """The joined name is the house spelling for a double-faced card.

        It reads "Bloodline Keeper // Lord of Lineage" and not "Bloodline
        Keeper" because the card is now authored rather than hand-written, and
        every authored double-faced card carries the joined name -- Edgar,
        Charmed Groom, Henrika Domnathi and Joshua all do. The hand-written
        pair was the one exception, and it was also the one carrying a
        `Legendary` supertype the printed card does not have and an upkeep
        trigger where the back face prints `{T}`.

        The joined name is not cosmetic: the residual gate reads a card's
        oracle text through `index.lookup(name)`, and the catalog knows this
        card only under both halves -- "Bloodline Keeper" and "Lord of
        Lineage" each resolve to nothing. A front-face-only name here would
        mean a card whose printed text no gate could check.
        """
        signature = client.get("/api/decks/edgar").json()["signature"]
        assert next(row["name"] for row in signature) == (
            "Bloodline Keeper // Lord of Lineage"
        )
        assert all(row["art_url"] for row in signature)

    def test_the_summary_list_stays_light(self, client):
        """The catalogue renders every tile; it must not pay for four essays."""
        rows = client.get("/api/decks").json()
        assert rows and "strategy" not in rows[0]
        assert rows[0]["tags"]

    def test_an_unknown_deck_is_a_404(self, client):
        assert client.get("/api/decks/black_lotus").status_code == 404


class TestImportedDecksLoadWithoutMetadata:
    def test_the_fields_are_all_optional(self):
        """An imported deck writes none of this, and must still load.

        ``DeckModel`` is ``extra="forbid"``, so the failure mode this guards
        against is the opposite one -- a required field would break every deck
        file that predates it.
        """
        from automtg.cards.schema import DeckModel

        deck = DeckModel(
            id="imported",
            name="Imported",
            commanders=["sol_ring"],
            cards=[{"id": "forest", "qty": 99}],
            source="moxfield",
        )
        assert deck.tags == []
        assert deck.ratings is None
        assert deck.strategy == ""
        assert deck.signature == []
