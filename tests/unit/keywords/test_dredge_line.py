"""702.52: "Dredge N" is the card-level `dredge` field, not an ability.

    Dakmor Salvage — "This land enters tapped. {T}: Add {B}. Dredge 2 (If you
    would draw a card, you may mill two cards instead. If you do, return this
    card from your graveyard to your hand.)"

The engine already offers dredge as a draw replacement from the graveyard
(`replacements._dredge`), and the loader carries the number onto
`CardDef.dredge`. What was missing was the residual gate's claimant: no
ability can honestly carry the line, so without one a dredge card could never
be authored. The claim is strict, like toxic's and annihilator's: the printed
number has to be the card's own.
"""

from __future__ import annotations

from commanderblitz.cards.authoring.verify import _covered
from commanderblitz.engine.carddef import CardDef

LINE = (
    "Dredge 2 (If you would draw a card, you may mill two cards instead. If you "
    "do, return this card from your graveyard to your hand.)"
)


def _land(dredge: int) -> CardDef:
    return CardDef(
        id="dakmor_salvage",
        name="Dakmor Salvage",
        oracle_text=LINE,
        types=["Land"],
        dredge=dredge,
    )


class TestTheResidualGate:
    def test_the_line_is_claimed_by_the_matching_dredge(self):
        assert _covered(_land(2), LINE)

    def test_the_bare_line_without_reminder_text_is_claimed_too(self):
        assert _covered(_land(2), "Dredge 2")

    def test_a_different_number_is_not_claimed(self):
        assert not _covered(_land(5), LINE)

    def test_a_card_without_dredge_cannot_claim_it(self):
        assert not _covered(_land(0), LINE)
