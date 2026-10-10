"""Cycling: the first ability the engine offers from a zone that is not the battlefield.

"Cycling {2} ({2}, Discard this card: Draw a card.)" — rule 702.29a. Two things
had to be true at once and neither was, which is why they arrived together.

*It is activated from your hand.* `loader._compile_ability` pinned every
activated ability to `(Zone.BATTLEFIELD,)` and threw away the schema's own
"hand" value, and `legality._activate_actions` walked only `state.battlefield`.
A land sitting in hand was never offered anything.

*The discard is not a choice.* `Cost.discard` is the near-miss and is a
different cost: `_discard_pool` offers the whole hand and `ask_objects` lets the
player pick, so a Krosan Tusker could be "cycled" by pitching a spare land and
staying in hand — a strictly better card than the one printed. `discard_self`
names *this* card and asks nothing.

The pairing is also the safety property: an ability activated from hand whose
cost did not remove it from hand could be activated forever, so the loader
refuses that combination outright.

The witnesses are Savai Triome and Reconnaissance Mission. `t_cycler` stands in
here so the test does not depend on which real cards happen to be authored.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _activate_actions
from tests.conftest import pass_until


def board(builder, *, mana: int = 4, hand=("t_cycler",)):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * mana)
        .hand(0, list(hand))
        .library(0, ["island"] * 20)
        .build()
    )


def cycle_action(game, card_id: str = "t_cycler"):
    """The offered cycling activation, or ``None`` if the engine is not offering it."""
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and game.state.objects[a.source].def_id == card_id
        ),
        None,
    )


def cycler_oid(game, card_id: str = "t_cycler") -> int:
    return next(
        oid
        for oid in game.state.players[0].hand
        if game.state.objects[oid].def_id == card_id
    )


class TestOfferedFromHand:
    def test_a_card_in_hand_offers_its_cycling_ability(self, builder):
        game = board(builder)
        assert cycle_action(game) is not None

    def test_it_is_not_offered_without_the_mana(self, builder):
        game = board(builder, mana=1)
        assert cycle_action(game) is None

    def test_the_creature_itself_is_still_uncastable_at_four_mana(self, builder):
        """Cycling is cheap precisely when the card is not: {2} against {4}{G}."""
        game = board(builder)
        casts = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "t_cycler"
        ]
        assert casts == []

    def test_only_your_own_hand_is_walked(self, builder):
        """The hand is hidden, so offering from an opponent's would leak it.

        Asked of `_activate_actions` directly rather than through
        `legal_actions`, because that answers whoever currently holds priority
        and the question here is about a specific player being offered a
        specific other player's card.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4)
            .battlefield(1, ["forest"] * 4)
            .hand(1, ["t_cycler"])
            .library(0, ["island"] * 20)
            .build()
        )

        def cyclers(pid: int):
            return [
                a
                for a in _activate_actions(game.state, pid, False)
                if game.state.objects[a.source].def_id == "t_cycler"
            ]

        assert cyclers(0) == []
        assert len(cyclers(1)) == 1


class TestTheCostIsThisCard:
    def test_cycling_draws_and_bins_the_cycled_card(self, builder):
        game = board(builder)
        oid = cycler_oid(game)
        before = len(game.state.players[0].hand)

        game.apply(cycle_action(game))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        # One card left hand as the cost and one arrived from the draw, so the
        # hand is where it started -- the observable that separates "discarded
        # itself" from "discarded nothing".
        assert len(game.state.players[0].hand) == before
        assert oid not in game.state.players[0].hand

    def test_it_discards_itself_rather_than_asking(self, builder):
        """The whole difference from `Cost.discard`.

        With a spare card in hand, a cost that merely discarded *one* card would
        let the player keep the cycler and pitch the other. Nothing is asked and
        the cycler is what goes.
        """
        game = board(builder, hand=("t_cycler", "t_bear"))
        oid = cycler_oid(game)
        spare = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == "t_bear"
        )

        game.apply(cycle_action(game))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert spare in game.state.players[0].hand

    def test_cycling_twice_is_impossible(self, builder):
        """It paid for itself by leaving, so there is nothing left to activate."""
        game = board(builder, mana=8)
        game.apply(cycle_action(game))
        pass_until(game, lambda g: not g.state.stack)
        assert cycle_action(game) is None


class TestTheLoaderRefusesAnInfiniteEngine:
    def _payload(self, cost: dict) -> dict:
        return {
            "id": "bad_cycler",
            "name": "Bad Cycler",
            "oracle_text": "{2}: Draw a card.",
            "mana_cost": "{1}{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "activated",
                    "text": "{2}: Draw a card.",
                    "active_zones": ["hand"],
                    "cost": cost,
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_activating_from_hand_without_leaving_hand_is_rejected(self):
        with pytest.raises(DslError, match="removes its source from that zone"):
            compile_card(CardModel.model_validate(self._payload({"mana": "{2}"})))

    def test_a_generic_discard_does_not_count(self):
        """`discard: 1` can throw away somebody else, so it does not end the loop."""
        with pytest.raises(DslError, match="removes its source from that zone"):
            compile_card(
                CardModel.model_validate(self._payload({"mana": "{2}", "discard": 1}))
            )

    def test_discard_self_is_accepted(self):
        card = compile_card(
            CardModel.model_validate(self._payload({"mana": "{2}", "discard_self": True}))
        )
        assert card.abilities[0].active_zones == (Zone.HAND,)

    def test_a_battlefield_ability_needs_no_such_cost(self):
        payload = self._payload({"mana": "{2}"})
        payload["abilities"][0]["active_zones"] = ["battlefield"]
        card = compile_card(CardModel.model_validate(payload))
        assert card.abilities[0].active_zones == (Zone.BATTLEFIELD,)


class TestItIsNotAManaSource:
    def test_discard_self_is_not_tap_only(self):
        """`is_tap_only` decides what the payment solver may tap for mana.

        A cycling cost that answered yes would let the solver "tap" a card in
        hand to pay for something else.
        """
        card = compile_card(
            CardModel.model_validate(
                {
                    "id": "tap_cycler",
                    "name": "Tap Cycler",
                    "oracle_text": "{T}, Discard this card: Add {G}.",
                    "mana_cost": "{1}",
                    "types": ["Artifact"],
                    "abilities": [
                        {
                            "kind": "activated",
                            "text": "{T}, Discard this card: Add {G}.",
                            "active_zones": ["hand"],
                            "cost": {"tap": True, "discard_self": True},
                            "effects": [{"op": "add_mana", "mana": "{G}"}],
                        }
                    ],
                }
            )
        )
        assert not card.abilities[0].cost.is_tap_only()
