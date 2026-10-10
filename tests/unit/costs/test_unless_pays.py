"""Rhystic Study: "unless that player pays" -- a cost somebody else may pay.

"Whenever an opponent casts a spell, you may draw a card unless that player
pays {1}." Rule 118.5 is the general shape: an effect can offer a player the
chance to pay a cost, and unless they do, something happens to them. The payer
gets *nothing* for the money -- what they are buying is the absence of the other
branch -- which is the whole reason this needed saying out loud.

It needed no new vocabulary. `op_may` already asks an arbitrary `player`
(`select_players` has taken `{"controller_of": ...}` all along), already carries
a `pay` cost paid mid-resolution by whoever is asked, and already branches to
`else` when they decline or cannot afford it. The one thing in the way was a
loader guard reading "'pay' needs 'effects' -- paying for nothing is not a
card", which is right when there is no `else` and precisely backwards when there
is. It now asks for `effects` **or** `else`, so a cost that buys nothing at all
is still refused.

What is worth pinning is every way this could look right and be a different
card:

- Asking the *wrong player*. A Rhystic Study that let its controller decide
  whether the opponent paid would be unbeatable, and would look completely
  normal on screen. This is the same property `test_two_piles.py` pins for Fact
  or Fiction, and the same helper makes it free.
- Charging and drawing anyway, or drawing when they paid. Either turns a tax
  into a draw engine.
- Offering a payment the opponent cannot afford. Rule 118.4: they simply do not
  pay, and the draw happens without a pointless prompt.
- Triggering on your own spells, which `controller: "opponent"` is the only
  thing preventing.

The turn cap matters and is not decoration: with nothing left to do the engine
runs on to the next turn, and player 0's draw *step* would otherwise be counted
as the trigger's card. `max_turns(1)` is what makes these absolute numbers
honest.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError

# A creature spell for the opponent to cast. {3}, generic-only, so the board
# never fails to make the mana for a reason unrelated to the test.
SPELL = "darksteel_myr"


def study(builder, *, lands: int = 5, caster: int = 1):
    """Rhystic Study for player 0; `caster` holds the spell and the mana."""
    other = 1 - caster
    return (
        builder(players=2)
        .battlefield(0, ["rhystic_study"] + (["island"] * lands if caster == 0 else []))
        .battlefield(1, ["island"] * lands if caster == 1 else [])
        .hand(caster, [SPELL])
        .hand(other, [])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(caster)
        .max_turns(1)
        .build()
    )


def cast_the_spell(game) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == SPELL
        )
    )


def answer_the_prompts(game, answers: list[bool]) -> list[int]:
    """Answer each `may` in turn; returns which player each was put to."""
    asked: list[int] = []
    pending = list(answers)
    for _ in range(20):
        decision = game.pending()
        if decision is None or decision.kind is not DecisionKind.MAY:
            break
        asked.append(decision.player)
        say_yes = pending.pop(0) if pending else False
        want = ActionKind.YES if say_yes else ActionKind.NO
        game.apply(next(a for a in game.legal_actions() if a.kind is want))
    return asked


def cards_drawn(game, before: int) -> int:
    return len(game.state.players[0].hand) - before


class TestWhoIsAsked:
    def test_the_caster_is_the_one_offered_the_cost(self, builder):
        game = study(builder)
        cast_the_spell(game)
        asked = answer_the_prompts(game, [True])
        assert asked[0] == 1, (
            "the opponent who cast the spell pays, not Rhystic Study's controller"
        )

    def test_the_controller_is_the_one_offered_the_draw(self, builder):
        game = study(builder)
        cast_the_spell(game)
        asked = answer_the_prompts(game, [False, True])
        assert asked == [1, 0], "they decline, then you decide whether to draw"


class TestPaying:
    def test_paying_stops_the_draw(self, builder):
        game = study(builder)
        before = len(game.state.players[0].hand)
        cast_the_spell(game)
        answer_the_prompts(game, [True])
        assert cards_drawn(game, before) == 0, "they paid, so there is no card"

    def test_declining_lets_the_draw_happen(self, builder):
        game = study(builder)
        before = len(game.state.players[0].hand)
        cast_the_spell(game)
        answer_the_prompts(game, [False, True])
        assert cards_drawn(game, before) == 1

    def test_the_draw_is_still_optional(self, builder):
        # "you *may* draw a card" -- declining the payment does not force it.
        game = study(builder)
        before = len(game.state.players[0].hand)
        cast_the_spell(game)
        answer_the_prompts(game, [False, False])
        assert cards_drawn(game, before) == 0


class TestWhenTheyCannotPay:
    def test_no_pointless_prompt(self, builder):
        # Three lands, and the spell costs {3}: casting it taps them all, so
        # there is no mana left for the {1}.
        game = study(builder, lands=3)
        cast_the_spell(game)
        asked = answer_the_prompts(game, [True])
        assert asked == [0], (
            "a cost the player cannot afford is not offered at all -- only the "
            "controller's own 'may draw' is"
        )

    def test_the_draw_happens_anyway(self, builder):
        game = study(builder, lands=3)
        before = len(game.state.players[0].hand)
        cast_the_spell(game)
        answer_the_prompts(game, [True])
        assert cards_drawn(game, before) == 1


class TestItIsOnlyOpponents:
    def test_your_own_spells_do_not_trigger_it(self, builder):
        game = study(builder, caster=0)
        cast_the_spell(game)
        assert answer_the_prompts(game, [True]) == [], (
            "'whenever an opponent casts a spell' -- your own cost you nothing "
            "and draw you nothing"
        )


def card_with(may_spec: dict) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Whenever an opponent casts a spell, probe.",
        "mana_cost": "{U}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever an opponent casts a spell, probe.",
                "trigger": {"event": "spell_cast", "controller": "opponent"},
                "effects": [may_spec],
            }
        ],
    }


class TestTheGuardStillBites:
    """The guard was narrowed, not removed."""

    def test_a_payment_that_buys_nothing_at_all_is_still_refused(self):
        payload = card_with({"op": "may", "player": "you", "pay": {"mana": "{1}"}})
        with pytest.raises(DslError, match="paying for nothing is not a card"):
            compile_card(CardModel.model_validate(payload))

    def test_effects_alone_still_loads(self):
        # "You may pay {2}. If you do, draw a card" -- the shape the guard was
        # written for, unchanged.
        payload = card_with(
            {
                "op": "may",
                "player": "you",
                "pay": {"mana": "{2}"},
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        )
        compile_card(CardModel.model_validate(payload))

    def test_else_alone_now_loads(self):
        # Rhystic Study's shape: the payer buys the absence of the else branch.
        payload = card_with(
            {
                "op": "may",
                "player": {"controller_of": "subject"},
                "pay": {"mana": "{1}"},
                "else": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        )
        compile_card(CardModel.model_validate(payload))
