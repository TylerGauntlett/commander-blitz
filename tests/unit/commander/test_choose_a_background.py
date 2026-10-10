"""Choose a Background (702.124): the second word that only builds a deck.

    "Choose a Background (You can have a Background as a second commander.)"
    -- Ganax, Astral Hunter.

The rule is entirely a deck-construction permission. By the time the engine sees
anything there is a finished deck and up to two commanders already in the command
zone, so there is no game rule left to run -- exactly the argument `partner` was
added on, and the reason both sit in `INERT_KEYWORDS`.

What was wrong without it was not a mis-played rule but a card that could not be
written at all. An `AbilityModel` is activated, triggered or static and a
deck-construction permission is none of the three, so nothing on Ganax could
claim the printed line; `verify`'s residual gate rejected the card with its other
two sentences -- flying, and the Treasure trigger -- fully implemented and
verified. The census's own routing rule puts the first row first for this case:
deck-construction only means an inert `Keyword`, "it must still be listed, or the
residual gate has an unclaimed line".

**Folding it onto `partner` would have been wrong**, which is the one design
decision here worth pinning. The two words look interchangeable -- both say "a
second commander" -- and they build different decks: a partner pair is two
commanders that each print *partner*, while this is one commander plus a
Background, an enchantment that prints nothing. One word standing for both would
be a deck validated against the wrong rule the moment `validate_deck` grows an
opinion about either, so the two normalise apart and neither claims the other's
printed line.

Inert has a precise meaning and it is tested here rather than assumed: the word
is a characteristic the card really carries -- `chars` reports it, and a card
whose text says something must be able to say it -- and nothing at all reads it.
The keyword-counter derivation is where that bites, because 122.1c turns any
keyword the engine implements into a counter that grants it: a *choose a
Background* counter must grant nothing, or the rule quietly invents a second
commander mid-game.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.proxy import lift_keywords
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import INERT_KEYWORDS, KEYWORD_COUNTERS, Keyword
from commanderblitz.engine.sandbox import GameBuilder
from tests.conftest import only_oid

BEAR = "t_bear"

#: The printed line, reminder text and all -- the thing the residual gate reads.
PRINTED = "Choose a Background (You can have a Background as a second commander.)"

GANAX_TEXT = "Flying\n" + PRINTED


def a_dragon(keywords: list[str]) -> dict:
    """A commander-shaped card carrying whatever words it is given."""
    return {
        "id": "t_background_probe",
        "name": "Background Probe",
        "oracle_text": GANAX_TEXT,
        "mana_cost": "{3}{R}",
        "types": ["Creature"],
        "supertypes": ["Legendary"],
        "subtypes": ["Dragon"],
        "power": 4,
        "toughness": 4,
        "colors": ["R"],
        "color_identity": ["R"],
        "keywords": keywords,
    }


def on_the_battlefield(registry: CardRegistry, keywords: list[str]):
    """``(game, oid)`` for a permanent printing the word."""
    card = compile_card(CardModel.model_validate(a_dragon(keywords)))
    pool = CardRegistry({**{c.id: c for c in registry}, card.id: card})
    game = GameBuilder(pool, players=2).battlefield(0, [card.id]).build()
    return game, only_oid(game, card.id, 0)


def a_bear(builder, counters: dict[str, int] | None = None):
    """A vanilla 2/2, so every keyword it has came from a counter."""
    game = builder(players=2).battlefield(0, [BEAR], counters=counters).build()
    return game, only_oid(game, BEAR, 0)


class TestTheCardCanSayIt:
    def test_the_word_loads_as_a_keyword(self, registry):
        """The whole point: a card printing the line can declare it."""
        game, oid = on_the_battlefield(registry, ["flying", "choose_a_background"])
        assert Keyword.CHOOSE_A_BACKGROUND.value in chars(game.state, oid).keywords

    def test_the_printed_line_is_claimed_reminder_and_all(self):
        """`lift_keywords` strips the reminder, so the residual gate sees the
        whole sentence accounted for rather than a suffix of it."""
        found, consumed = lift_keywords(
            GANAX_TEXT, ("flying", "choose_a_background"), strict=True
        )
        assert found == ["flying", "choose_a_background"]
        assert PRINTED in consumed

    def test_a_card_that_does_not_carry_it_claims_nothing(self):
        """Strict mode is the residual gate's teeth: printing the word is not
        implementing it, and a card that only has flying leaves the line open."""
        found, consumed = lift_keywords(GANAX_TEXT, ("flying",), strict=True)
        assert found == ["flying"]
        assert PRINTED not in consumed


class TestItIsNotPartner:
    def test_the_two_words_are_separate_members(self):
        assert Keyword.CHOOSE_A_BACKGROUND is not Keyword.PARTNER
        assert Keyword.CHOOSE_A_BACKGROUND.value != Keyword.PARTNER.value

    def test_partner_does_not_claim_the_background_line(self):
        """A commander printing *partner* builds a different deck, so it must not
        be able to account for this sentence."""
        _, consumed = lift_keywords(GANAX_TEXT, ("flying", "partner"), strict=True)
        assert PRINTED not in consumed

    def test_the_background_word_does_not_claim_partner(self):
        """And the mirror, so neither is an alias for the other."""
        _, consumed = lift_keywords(
            "Partner", ("choose_a_background",), strict=True
        )
        assert consumed == set()


class TestItDoesNothingInAGame:
    def test_it_is_inert_by_declaration(self):
        assert Keyword.CHOOSE_A_BACKGROUND in INERT_KEYWORDS

    def test_there_is_no_choose_a_background_counter(self):
        """122.1c derives keyword counters from every keyword the engine has, so
        a new one arrives as a counter kind unless it is excluded. This one must
        be: a counter granting a deck-construction permission mid-game is the
        inert tally in a costume."""
        assert Keyword.CHOOSE_A_BACKGROUND.value not in KEYWORD_COUNTERS

    def test_such_a_counter_grants_nothing(self, builder):
        game, bear = a_bear(builder, {"choose_a_background": 1})
        assert chars(game.state, bear).keywords == frozenset()

    def test_it_grants_no_evasion_or_protection(self, registry):
        """The word is the *only* thing on the card beyond flying, so whatever
        `chars` reports beside it is what the keyword did -- which is nothing."""
        with_word, oid = on_the_battlefield(registry, ["choose_a_background"])
        without, plain = on_the_battlefield(registry, [])
        gained = chars(with_word.state, oid).keywords - chars(without.state, plain).keywords
        assert gained == {Keyword.CHOOSE_A_BACKGROUND.value}
