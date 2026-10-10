"""Rule 903.3: who may lead a Commander deck.

    Teferi, Temporal Archmage — "… Teferi, Temporal Archmage can be your
    commander."

903.3 says a deck's commander is a **legendary creature**, and then the
exception: a card whose text says it "can be your commander". `validate_deck`
had neither half right. It accepted any legendary creature *or planeswalker*,
so a deck led by Liliana, the Last Hope -- who prints no such sentence -- built
cleanly, and it never read the sentence at all, so the check was correct for
Teferi only by the accident of being too loose for everybody.

Three things this has to get right:

- **The sentence licenses the card that prints it.** Read against the card's
  own name, like Persistent Petitioners' "any number" line, so quoting another
  card's text grants nothing.
- **A legendary planeswalker without it is refused** -- the near miss, and the
  line that used to pass.
- **The line is a deck-building rule, not an ability**, so the residual gate
  must accept it on a card that carries it and nowhere else.
"""

from __future__ import annotations

from commanderblitz.cards.authoring.verify import _covered
from commanderblitz.cards.registry import CardRegistry, DeckList, validate_deck
from commanderblitz.engine.carddef import CardDef

TEFERI_LINE = "Teferi, Temporal Archmage can be your commander."


def _walker(card_id: str, name: str, oracle: str) -> CardDef:
    return CardDef(
        id=card_id,
        name=name,
        oracle_text=oracle,
        types=["Planeswalker"],
        supertypes=["Legendary"],
        colors=["U"],
        color_identity=["U"],
        loyalty=5,
    )


def _teferi() -> CardDef:
    return _walker(
        "teferi_temporal_archmage",
        "Teferi, Temporal Archmage",
        "+1: Look at the top two cards of your library.\n" + TEFERI_LINE,
    )


def _deck(commander: CardDef) -> tuple[DeckList, CardRegistry]:
    """A 100-card mono-blue deck: `commander` plus 99 Islands."""
    island = CardDef(
        id="island",
        name="Island",
        types=["Land"],
        subtypes=["Island"],
        supertypes=["Basic"],
        color_identity=[],
    )
    deck = DeckList(
        id="t",
        name="T",
        commanders=(commander.id,),
        color_identity=frozenset("U"),
        cards=(("island", 99),),
    )
    return deck, CardRegistry({commander.id: commander, island.id: island})


class TestTheSentenceLicensesItsCard:
    def test_teferi_reads_his_own_line(self):
        assert _teferi().can_be_commander

    def test_teferi_leads_a_deck(self):
        assert validate_deck(*_deck(_teferi())) == []

    def test_quoting_another_card_grants_nothing(self):
        mimic = _walker(
            "mimic", "Some Walker", "Copy it. (" + TEFERI_LINE.rstrip(".") + ".)"
        )
        assert not mimic.can_be_commander


class TestALegendaryPlaneswalkerWithoutItIsRefused:
    def test_liliana_cannot_lead_a_deck(self):
        liliana = _walker(
            "liliana_the_last_hope",
            "Liliana, the Last Hope",
            "+1: Up to one target creature gets -2/-1 until your next turn.",
        )
        problems = validate_deck(*_deck(liliana))
        assert any("is not a creature" in p for p in problems)

    def test_a_legendary_creature_needs_no_sentence(self):
        creature = CardDef(
            id="bruvac",
            name="Bruvac the Grandiloquent",
            types=["Creature"],
            supertypes=["Legendary"],
            colors=["U"],
            color_identity=["U"],
            power=1,
            toughness=4,
        )
        assert validate_deck(*_deck(creature)) == []


class TestTheResidualGate:
    def test_the_line_is_claimed_on_the_card_that_prints_it(self):
        assert _covered(_teferi(), TEFERI_LINE)

    def test_not_on_a_card_whose_text_does_not_say_it(self):
        liliana = _walker("l", "Liliana, the Last Hope", "+1: Draw a card.")
        assert not _covered(liliana, TEFERI_LINE)
