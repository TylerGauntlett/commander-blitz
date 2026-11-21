""""Discard your hand" as an activated-ability cost (601.2h).

    Slate of Ancestry: "{4}, {T}, Discard your hand: Draw a card for each
    creature you control."

A cost is paid in full as the ability is activated (601.2h, applied to
abilities by 602.2b), so the hand is gone before the ability is on the stack
and before anyone can respond. "Your hand" is every card in it, whatever the
count, with no choice about which go; and an empty hand is still a hand, so
discarding no cards pays the cost and the ability stays on offer.

What was wrong without this: `cost.discard` is a number the card fixes and
refuses a hand smaller than it, so no constant is right -- seven is unpayable
holding six, and zero charges nothing. `discard_x` lets the player choose how
many go. The `discard` op's `whole_hand` empties the hand only on resolution,
leaving it intact while the ability waits on the stack.

Witness: Slate of Ancestry. `t_dh_slate` is its cost on a cheap body.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, only_oid, settle

SLATE = "t_dh_slate"


def position(builder, *, hand=("grizzly_bears", "swamp", "lightning_bolt")):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 2 + [SLATE])
        .hand(0, list(hand))
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, SLATE, 0)


def hand(game) -> list[int]:
    return list(game.state.players[0].hand)


class TestTheWholeHandGoes:
    def test_every_card_is_discarded_with_no_choice(self, builder):
        game, slate = position(builder)
        cards = hand(game)
        game.apply(activations(game, slate)[0])
        pending = game.pending()
        assert pending is None or pending.kind is not DecisionKind.CHOOSE_OBJECTS
        assert not set(cards) & set(hand(game))
        assert all(game.state.objects[oid].zone is Zone.GRAVEYARD for oid in cards)

    def test_it_is_paid_before_the_effect(self, builder):
        """601.2h: paid as it is activated, so the card the effect draws is the
        one card left -- a discard on resolution would have taken it too."""
        game, slate = position(builder)
        before = set(hand(game))
        life = game.state.players[0].life
        game.apply(activations(game, slate)[0])
        settle(game)
        assert game.state.players[0].life == life + 1
        assert len(hand(game)) == 1 and not before & set(hand(game))

    def test_the_rest_of_the_cost_is_still_paid(self, builder):
        game, slate = position(builder)
        game.apply(activations(game, slate)[0])
        assert game.state.objects[slate].tapped
        tapped = [
            o for o in game.state.battlefield_objects(0) if o.def_id == "swamp" and o.tapped
        ]
        assert len(tapped) == 1


class TestAnEmptyHandStillPays:
    def test_it_is_offered_with_nothing_in_hand(self, builder):
        game, slate = position(builder, hand=())
        assert activations(game, slate)

    def test_it_resolves_with_nothing_in_hand(self, builder):
        game, slate = position(builder, hand=())
        life = game.state.players[0].life
        game.apply(activations(game, slate)[0])
        settle(game)
        assert game.state.players[0].life == life + 1


class TestItReads:
    def test_it_reads_as_discard_your_hand(self, registry):
        cost = registry.get(SLATE).abilities[0].cost
        assert cost.describe() == "{1}, {T}, Discard your hand"

    def test_it_is_not_a_tap_for_mana_shape(self, registry):
        """The payment solver must never empty a hand nobody asked about."""
        assert not registry.get(SLATE).abilities[0].cost.is_tap_only()


class TestTheLoaderChecksIt:
    def _card(self, cost: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_dh_bad",
                "name": "Test Bad Discard Hand",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": "Discard your hand: You gain 1 life.",
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Discard your hand: You gain 1 life.",
                        "cost": cost,
                        "effects": [{"op": "gain_life", "player": "you", "amount": 1}],
                    }
                ],
            }
        )

    def test_the_flag_alone_is_the_form(self):
        compile_card(self._card({"discard_hand": True}))

    @pytest.mark.parametrize(
        "extra",
        [
            {"discard": 1},
            {"discard_x": True},
            {"discard_self": True},
        ],
    )
    def test_not_beside_another_answer_to_which_cards_go(self, extra):
        with pytest.raises(DslError, match="discard_hand"):
            compile_card(self._card({"discard_hand": True, **extra}))
