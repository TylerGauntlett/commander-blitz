"""Rule 903.5b's other half: the cards that lift their own one-copy limit.

    Persistent Petitioners — "{1}, {T}: Target player mills a card. … A deck can
    have any number of cards named Persistent Petitioners."

903.5b says a Commander deck may contain only one of any card with a particular
English name **other than basic lands**, and then adds "unless that card's text
says otherwise". `validate_deck` had only the basic-land exemption, so the twenty
Petitioners the Bruvac mill deck is built on failed construction with
``'persistent_petitioners' appears 20 times but is not a basic land`` and the deck
could not be imported at all.

Three things this has to get right, each of which would be wrong in a different
direction:

- **The sentence names the card it applies to.** Shadowborn Apostle's text does
  not license a playset of Relentless Rats, so the name in the sentence is
  matched against the card's own name rather than merely found.
- **Basic lands keep their exemption from the rule itself**, with no printed
  sentence to read — Island says nothing about deck construction.
- **An unread limit must reject, not admit.** Nazgûl prints "A deck can have up
  to nine cards named Nazgûl.", a *different* limit, and is deliberately not
  matched: unmatched it keeps the one-copy default, which refuses a legal deck
  rather than waving through an illegal one.
"""

from __future__ import annotations

from automtg.cards.registry import CardRegistry, DeckList, validate_deck
from automtg.engine.carddef import CardDef

PETITIONERS_TEXT = (
    "{1}, {T}: Target player mills a card.\n"
    "Tap four untapped Advisors you control: Target player mills twelve cards.\n"
    "A deck can have any number of cards named Persistent Petitioners."
)


def _card(card_id: str, name: str, **kwargs) -> CardDef:
    kwargs.setdefault("types", ["Creature"])
    kwargs.setdefault("colors", ["U"])
    kwargs.setdefault("color_identity", ["U"])
    return CardDef(id=card_id, name=name, **kwargs)


def _deck(cards: tuple[tuple[str, int], ...]) -> tuple[DeckList, CardRegistry]:
    """A 100-card mono-blue deck: a legendary commander plus `cards`, padded."""
    commander = _card(
        "bruvac",
        "Bruvac the Grandiloquent",
        supertypes=["Legendary"],
        power=1,
        toughness=4,
    )
    island = _card(
        "island",
        "Island",
        types=["Land"],
        subtypes=["Island"],
        supertypes=["Basic"],
        colors=[],
    )
    listed = sum(qty for _, qty in cards)
    pool = {c.id: c for c in (commander, island)}
    for card_id, _ in cards:
        pool.setdefault(card_id, _card(card_id, card_id))
    entries = (*cards, ("island", 99 - listed))
    deck = DeckList(
        id="t",
        name="T",
        commanders=("bruvac",),
        color_identity=frozenset("U"),
        cards=entries,
    )
    return deck, CardRegistry(pool)


class TestACardMayLiftItsOwnLimit:
    def test_twenty_petitioners_are_legal(self):
        petitioners = _card(
            "persistent_petitioners", "Persistent Petitioners", oracle_text=PETITIONERS_TEXT
        )
        deck, registry = _deck((("persistent_petitioners", 20),))
        registry = CardRegistry({**{c.id: c for c in registry}, petitioners.id: petitioners})
        assert validate_deck(deck, registry) == []

    def test_a_card_without_the_sentence_is_still_singleton(self):
        """The near miss: same deck slot, ordinary card, twenty copies."""
        deck, registry = _deck((("brainstorm", 20),))
        problems = validate_deck(deck, registry)
        assert any("appears 20 times" in p for p in problems)

    def test_one_copy_of_an_ordinary_card_is_fine(self):
        deck, registry = _deck((("brainstorm", 1),))
        assert validate_deck(deck, registry) == []


class TestTheSentenceNamesItsOwnCard:
    def test_quoting_another_cards_sentence_does_not_count(self):
        """A card that merely mentions the exemption does not receive it.

        Without the name check this is the failure mode: any card whose oracle
        text contains the template — a card that *copies* another card's text,
        or reminder text quoting it — would become a playset.
        """
        impostor = _card(
            "impostor",
            "Impostor",
            oracle_text="A deck can have any number of cards named Persistent Petitioners.",
        )
        assert not impostor.any_number_in_deck

    def test_the_real_card_receives_it(self):
        real = _card(
            "persistent_petitioners", "Persistent Petitioners", oracle_text=PETITIONERS_TEXT
        )
        assert real.any_number_in_deck

    def test_a_card_with_no_oracle_text_does_not(self):
        assert not _card("plain", "Plain").any_number_in_deck


class TestTheUnreadLimitRejects:
    def test_nazgul_is_not_matched(self):
        """"Up to nine" is a different limit; unmatched, it keeps the default.

        This is the incomplete-in-the-safe-direction assertion: the check refuses
        a legal Nazgûl deck rather than admitting an unbounded one.
        """
        nazgul = _card(
            "nazgul",
            "Nazgûl",
            oracle_text="Menace\nA deck can have up to nine cards named Nazgûl.",
        )
        assert not nazgul.any_number_in_deck

    def test_a_basic_land_needs_no_sentence(self):
        island = _card(
            "island", "Island", types=["Land"], subtypes=["Island"], supertypes=["Basic"]
        )
        assert island.is_basic
        assert not island.any_number_in_deck
