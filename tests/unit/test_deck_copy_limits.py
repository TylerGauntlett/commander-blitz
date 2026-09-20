"""Rule 903.5b's other half: the cards that set their own copy limit.

    Persistent Petitioners — "{1}, {T}: Target player mills a card. … A deck can
    have any number of cards named Persistent Petitioners."

903.5b says a Commander deck may contain only one of any card with a particular
English name **other than basic lands**, and then adds "unless that card's text
says otherwise". `validate_deck` had only the basic-land exemption, so the twenty
Petitioners the Bruvac mill deck is built on failed construction with
``'persistent_petitioners' appears 20 times but is not a basic land`` and the deck
could not be imported at all.

"Otherwise" is sometimes a number rather than a blank cheque: two cards in the
catalog print a *ceiling* instead — "A deck can have up to nine cards named
Nazgûl." and Seven Dwarves' "up to seven". `CardDef.deck_copy_limit` is the
whole of 903.5b in one place, and the number it returns is what a deck is
checked against.

Four things this has to get right, each of which would be wrong in a different
direction:

- **The sentence names the card it applies to.** Shadowborn Apostle's text does
  not license a playset of Relentless Rats, so the name in the sentence is
  matched against the card's own name rather than merely found.
- **Basic lands keep their exemption from the rule itself**, with no printed
  sentence to read — Island says nothing about deck construction.
- **A ceiling is a ceiling in both directions.** Nine Nazgûl are legal and a
  tenth is not, and the refusal has to say what the real limit was rather than
  claiming the card is not a basic land.
- **An unread limit must reject, not admit.** A number this cannot read falls
  back to one copy, which refuses a legal deck rather than waving through an
  illegal one.
"""

from __future__ import annotations

from automtg.cards.authoring.verify import _covered
from automtg.cards.registry import CardRegistry, DeckList, validate_deck
from automtg.engine.carddef import CardDef

PRINTED_LINE = "A deck can have any number of cards named Persistent Petitioners."

PETITIONERS_TEXT = (
    "{1}, {T}: Target player mills a card.\n"
    "Tap four untapped Advisors you control: Target player mills twelve cards.\n"
    "A deck can have any number of cards named Persistent Petitioners."
)


NAZGUL_LINE = "A deck can have up to nine cards named Nazgûl."


def _card(card_id: str, name: str, **kwargs) -> CardDef:
    kwargs.setdefault("types", ["Creature"])
    kwargs.setdefault("colors", ["U"])
    kwargs.setdefault("color_identity", ["U"])
    return CardDef(id=card_id, name=name, **kwargs)


def _nazgul() -> CardDef:
    return _card("nazgul", "Nazgûl", oracle_text=f"Menace\n{NAZGUL_LINE}")


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


class TestACeilingIsNotABlankCheque:
    """A printed ceiling grants nine Nazgul, and withholds the tenth."""

    def test_nazgul_is_bounded_not_unbounded(self):
        assert not _nazgul().any_number_in_deck
        assert _nazgul().deck_copy_limit == 9

    def test_nine_nazgul_are_legal(self):
        deck, registry = _deck((("nazgul", 9),))
        registry = CardRegistry({**{c.id: c for c in registry}, "nazgul": _nazgul()})
        assert validate_deck(deck, registry) == []

    def test_a_tenth_nazgul_is_not(self):
        deck, registry = _deck((("nazgul", 10),))
        registry = CardRegistry({**{c.id: c for c in registry}, "nazgul": _nazgul()})
        problems = validate_deck(deck, registry)
        assert problems == ["'nazgul' appears 10 times but a deck can have up to 9 of them"]

    def test_seven_dwarves_reads_its_own_number(self):
        """The other printing of the form, and a different number.

        Two cards in the catalog print a ceiling. Pinning both means the word
        is genuinely read off the card rather than one case being special-cased
        into passing.
        """
        dwarves = _card(
            "seven_dwarves",
            "Seven Dwarves",
            oracle_text=(
                "Seven Dwarves gets +1/+1 for each other creature you control named "
                "Seven Dwarves.\nA deck can have up to seven cards named Seven Dwarves."
            ),
        )
        assert dwarves.deck_copy_limit == 7

    def test_quoting_a_ceiling_does_not_raise_your_own(self):
        """The name check guards the bounded form too, not just the unbounded one."""
        impostor = _card(
            "impostor", "Impostor", oracle_text="A deck can have up to nine cards named Nazgûl."
        )
        assert impostor.deck_copy_limit == 1


class TestTheUnreadLimitRejects:
    def test_an_unreadable_number_falls_back_to_one(self):
        """The incomplete-in-the-safe-direction assertion.

        A word outside the number map is not a licence to guess. Falling back to
        one copy refuses a legal deck, which is recoverable; guessing high would
        admit an illegal one, which is not.
        """
        odd = _card(
            "odd",
            "Odd",
            oracle_text="A deck can have up to umpteen cards named Odd.",
        )
        assert odd.deck_copy_limit == 1
        assert not odd.any_number_in_deck

    def test_a_basic_land_needs_no_sentence(self):
        island = _card(
            "island", "Island", types=["Land"], subtypes=["Island"], supertypes=["Basic"]
        )
        assert island.is_basic
        assert not island.any_number_in_deck
        assert island.deck_copy_limit is None

    def test_an_ordinary_card_is_a_singleton(self):
        assert _card("brainstorm", "Brainstorm").deck_copy_limit == 1


class TestTheResidualGateCanHearTheLine:
    """The other half: gate 3 has to let the printed sentence be claimed.

    The rule above is read by `validate_deck` while a deck is being built, so by
    the time the card is an object in a game the line has nothing left to do and
    no ability can honestly carry it -- an AbilityModel is activated, triggered
    or static, and this is none of the three. Without a claimant in
    `verify._covered`, Persistent Petitioners failed the text-attribution gate
    with both of its real lines implemented and verified, which is what kept the
    card out of the pool.
    """

    def test_the_line_is_claimed_when_the_card_grants_it(self):
        card = _card(
            "persistent_petitioners", "Persistent Petitioners", oracle_text=PETITIONERS_TEXT
        )
        assert _covered(card, PRINTED_LINE)

    def test_quoting_another_cards_sentence_is_not_claimed(self):
        """The strictness is inherited from the rule, not restated here.

        `any_number_in_deck` is False for a card the sentence does not name, so
        the words alone cannot satisfy the gate -- the claimant cannot be used to
        launder a line onto a card that does not actually have the rule.
        """
        impostor = _card("impostor", "Impostor", oracle_text=PRINTED_LINE)
        assert not _covered(impostor, PRINTED_LINE)

    def test_the_bounded_sentence_is_claimed_too(self):
        """It is the same deck-construction rule, so it has the same claimant."""
        assert _covered(_nazgul(), NAZGUL_LINE)

    def test_quoting_a_bounded_sentence_is_not_claimed(self):
        """Strictness inherited from the rule here as well, not restated.

        `deck_copy_limit` is 1 for a card the sentence does not name, so the
        words alone cannot satisfy the gate.
        """
        impostor = _card("impostor", "Impostor", oracle_text=NAZGUL_LINE)
        assert not _covered(impostor, NAZGUL_LINE)

    def test_an_unreadable_ceiling_stays_residual(self):
        """A limit the parser could not read is not waved through on its words."""
        line = "A deck can have up to umpteen cards named Odd."
        assert not _covered(_card("odd", "Odd", oracle_text=line), line)

    def test_an_unrelated_line_is_still_residual(self):
        """The claimant is scoped to its own sentence and claims nothing else."""
        card = _card(
            "persistent_petitioners", "Persistent Petitioners", oracle_text=PETITIONERS_TEXT
        )
        assert not _covered(card, "Target player mills a card.")
