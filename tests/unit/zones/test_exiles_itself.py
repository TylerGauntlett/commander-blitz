""""Exile Teferi's Protection." -- a spell that exiles itself as it resolves

    Teferi's Protection -- "Until your next turn, your life total can't change
    and you gain protection from everything. All permanents you control phase
    out.
    **Exile Teferi's Protection.**"

The sixth rider on the destination `stack._place_after_resolution` picks, beside
flashback's exile, buyback's hand, rebound's exile, cipher's and adventure's --
and like all five it only ever replaces the *graveyard*.

**It could not be an `exile` op in the card's own effects.** A resolving spell's
object still says `Zone.STACK`, but it has already been popped off
`state.stack`, so a `{"zone": "stack", "self_only": true}` selector reaches
nothing: the printed line would load cleanly and do nothing at all, which is the
class of failure the whole authoring pipeline is arranged against. `exile_self`
is not it either -- that is a *cost* key, paid on activation.

The line is not decoration. A Teferi's Protection sitting in a graveyard is a
Teferi's Protection somebody can Regrowth, and the printed card cannot be.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card

SPELL = "t_exiles_itself"  # instant: gain 2 life. Exile this card.
PLAIN = "t_life_lock"  # an ordinary instant, for the control


def board(builder, card_id: str):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .hand(0, [card_id])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
        .build()
    )


def cast_and_settle(game, card_id: str) -> int:
    action = action_for_card(game, ActionKind.CAST, card_id)
    oid = action.source
    game.apply(action)
    for _ in range(100):
        decision = game.pending()
        if decision is None or not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    assert oid is not None
    return oid


class TestWhereItGoes:
    def test_it_ends_in_exile(self, builder):
        game = board(builder, SPELL)
        oid = cast_and_settle(game, SPELL)
        assert game.state.objects[oid].zone is Zone.EXILE

    def test_it_is_not_in_the_graveyard(self, builder):
        """The point of the line: a graveyard copy is one somebody can recur."""
        game = board(builder, SPELL)
        oid = cast_and_settle(game, SPELL)
        assert oid not in game.state.players[0].graveyard

    def test_it_still_did_what_it_said(self, builder):
        """Exiling itself is the *last* thing; the effects ran first."""
        game = board(builder, SPELL)
        life = game.state.players[0].life
        cast_and_settle(game, SPELL)
        assert game.state.players[0].life == life + 2

    def test_an_ordinary_instant_still_goes_to_the_graveyard(self, builder):
        """The control -- the rider and nothing else moved the card."""
        game = board(builder, PLAIN)
        oid = cast_and_settle(game, PLAIN)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestTheLoaderRefusesNonsense:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "t_bad_exiles_itself",
                "name": "Bad Exiles Itself",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "colors": ["W"],
                "color_identity": ["W"],
                "spell_effects": [{"op": "gain_life", "amount": {"const": 1}}],
                **extra,
            }
        )

    def test_a_permanent_carrying_it_is_refused(self):
        """It replaces the graveyard, and a permanent never reaches the rider."""
        with pytest.raises(DslError, match="exiles_itself"):
            compile_card(
                self._card(types=["Enchantment"], exiles_itself=True, spell_effects=[])
            )

    def test_it_cannot_be_combined_with_rebound(self):
        """Both send it to exile, and only one hands it back."""
        with pytest.raises(DslError, match="hands it back"):
            compile_card(
                self._card(types=["Instant"], exiles_itself=True, rebound=True)
            )
