"""Doctor's companion: the third word that only builds a deck (702.124).

    "Doctor's companion (You can have two commanders if the other is the
    Doctor.)" -- Yasmin Khan, and every companion in the Doctor Who precons.

Like partner and choose a Background, the rule is a deck-construction
permission: by the time the engine sees anything there is a finished deck and
its commanders are already in the command zone, so no game rule is left to run.
What was wrong without it was a card that could not be written at all. Yasmin
Khan's other line was fully expressible, and the residual gate still rejected
her for an unclaimed sentence nothing on an `AbilityModel` can carry.

Two things are pinned here beyond "the word loads". The printed spelling has an
apostrophe the engine's word does not, so `KEYWORD_ALIASES` folds it, and the
line must be claimed through that fold, reminder text and all. And it stays its
own word: partner pairs two commanders that both print *partner*, choose a
Background pairs one with an enchantment, and this pairs one with a Time Lord
Doctor. One word standing for two of them would validate a deck against the
wrong rule the moment `validate_deck` checks pairings.

Inert is tested rather than assumed: `chars` reports the word, and nothing
reads it -- in particular 122.1c's keyword-counter derivation, where a
*Doctor's companion* counter must grant nothing.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.vocabulary import normalize_keyword
from commanderblitz.cards.proxy import lift_keywords
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import INERT_KEYWORDS, KEYWORD_COUNTERS, Keyword
from commanderblitz.engine.sandbox import GameBuilder
from tests.conftest import only_oid

BEAR = "t_bear"

#: The printed line, reminder text and all -- the thing the residual gate reads.
PRINTED = "Doctor's companion (You can have two commanders if the other is the Doctor.)"

COMPANION_TEXT = "Vigilance\n" + PRINTED


def a_companion(keywords: list[str]) -> dict:
    """A commander-shaped card carrying whatever words it is given."""
    return {
        "id": "t_companion_probe",
        "name": "Companion Probe",
        "oracle_text": COMPANION_TEXT,
        "mana_cost": "{1}{W}",
        "types": ["Creature"],
        "supertypes": ["Legendary"],
        "subtypes": ["Human"],
        "power": 2,
        "toughness": 2,
        "colors": ["W"],
        "color_identity": ["W"],
        "keywords": keywords,
    }


def on_the_battlefield(registry: CardRegistry, keywords: list[str]):
    """``(game, oid)`` for a permanent printing the word."""
    card = compile_card(CardModel.model_validate(a_companion(keywords)))
    pool = CardRegistry({**{c.id: c for c in registry}, card.id: card})
    game = GameBuilder(pool, players=2).battlefield(0, [card.id]).build()
    return game, only_oid(game, card.id, 0)


def a_bear(builder, counters: dict[str, int] | None = None):
    """A vanilla 2/2, so every keyword it has came from a counter."""
    game = builder(players=2).battlefield(0, [BEAR], counters=counters).build()
    return game, only_oid(game, BEAR, 0)


class TestTheCardCanSayIt:
    def test_the_word_loads_as_a_keyword(self, registry):
        game, oid = on_the_battlefield(registry, ["vigilance", "doctors_companion"])
        assert Keyword.DOCTORS_COMPANION.value in chars(game.state, oid).keywords

    def test_the_printed_apostrophe_folds_onto_the_word(self):
        assert normalize_keyword("doctor's_companion") == Keyword.DOCTORS_COMPANION.value

    def test_the_printed_line_is_claimed_reminder_and_all(self):
        found, consumed = lift_keywords(
            COMPANION_TEXT, ("vigilance", "doctors_companion"), strict=True
        )
        assert found == ["vigilance", "doctors_companion"]
        assert PRINTED in consumed

    def test_scryfalls_printed_spelling_lifts_it_too(self):
        """Generating a proxy, ``printed`` is Scryfall's array, which keeps the
        apostrophe; it must meet the same word."""
        found, consumed = lift_keywords(PRINTED, ("Doctor's companion",))
        assert found == ["doctors_companion"]
        assert PRINTED in consumed

    def test_a_card_that_does_not_carry_it_claims_nothing(self):
        found, consumed = lift_keywords(COMPANION_TEXT, ("vigilance",), strict=True)
        assert found == ["vigilance"]
        assert PRINTED not in consumed


class TestItIsNotAnotherPairing:
    def test_partner_does_not_claim_the_companion_line(self):
        _, consumed = lift_keywords(COMPANION_TEXT, ("vigilance", "partner"), strict=True)
        assert PRINTED not in consumed

    def test_choose_a_background_does_not_claim_it(self):
        _, consumed = lift_keywords(
            COMPANION_TEXT, ("vigilance", "choose_a_background"), strict=True
        )
        assert PRINTED not in consumed

    def test_the_companion_word_claims_neither_of_theirs(self):
        _, consumed = lift_keywords("Partner", ("doctors_companion",), strict=True)
        assert consumed == set()
        _, consumed = lift_keywords(
            "Choose a Background", ("doctors_companion",), strict=True
        )
        assert consumed == set()


class TestItDoesNothingInAGame:
    def test_it_is_inert_by_declaration(self):
        assert Keyword.DOCTORS_COMPANION in INERT_KEYWORDS

    def test_there_is_no_doctors_companion_counter(self):
        assert Keyword.DOCTORS_COMPANION.value not in KEYWORD_COUNTERS

    def test_such_a_counter_grants_nothing(self, builder):
        game, bear = a_bear(builder, {"doctors_companion": 1})
        assert chars(game.state, bear).keywords == frozenset()

    def test_it_grants_no_evasion_or_protection(self, registry):
        with_word, oid = on_the_battlefield(registry, ["doctors_companion"])
        without, plain = on_the_battlefield(registry, [])
        gained = chars(with_word.state, oid).keywords - chars(without.state, plain).keywords
        assert gained == {Keyword.DOCTORS_COMPANION.value}
