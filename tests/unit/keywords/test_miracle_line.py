"""702.94a: a printed "Miracle {cost}" is the card-level `miracle` field.

    Metamorphosis Fanatic — "Lifelink … Miracle {1}{B} (You may cast this card
    for its miracle cost when you draw it if it's the first card you drew this
    turn.)"

The engine already offers the miracle cast as a draw replacement
(`replacements._miracle`), and the loader parses the cost onto
`CardDef.miracle`. What was missing was the residual gate's claimant: no ability
can honestly carry the line, so a printed miracle card could never be authored.
The claim is strict, like warp's: the printed cost has to be the card's own.
"""

from __future__ import annotations

from commanderblitz.cards.authoring.verify import _covered
from commanderblitz.engine.carddef import CardDef
from commanderblitz.engine.mana import ManaCost

LINE = (
    "Miracle {1}{B} (You may cast this card for its miracle cost when you draw "
    "it if it's the first card you drew this turn.)"
)


def _creature(miracle: str | None) -> CardDef:
    return CardDef(
        id="metamorphosis_fanatic",
        name="Metamorphosis Fanatic",
        oracle_text=LINE,
        types=["Creature"],
        miracle=None if miracle is None else ManaCost.parse(miracle),
    )


class TestTheResidualGate:
    def test_the_line_is_claimed_by_the_matching_cost(self):
        assert _covered(_creature("{1}{B}"), LINE)

    def test_the_bare_line_without_reminder_text_is_claimed_too(self):
        assert _covered(_creature("{1}{B}"), "Miracle {1}{B}")

    def test_a_cheaper_cost_is_not_claimed(self):
        assert not _covered(_creature("{0}"), LINE)

    def test_a_card_without_miracle_cannot_claim_it(self):
        assert not _covered(_creature(None), LINE)
