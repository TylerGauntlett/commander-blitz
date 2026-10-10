"""Returning a permanent to hand as a *cost*, not as an effect.

    Meloku the Clouded Mirror — "{1}, Return a land you control to its owner's
    hand: Create a 1/1 blue Illusion creature token with flying."

    Trench Behemoth — "Return a land you control to its owner's hand: Untap
    this creature."

`sacrifice` is the near miss and it is a different cost, in the one way that
matters for both of these cards: it graveyards the land. Meloku and Trench
Behemoth are built on replaying what they return — every bounce is another land
drop, and in this deck another landfall trigger. A sacrifice version is not a
worse card or a better one, it is a different engine, and nothing on screen
would say so.

Everything else about it is `sacrifice`'s shape, which is the point: the pool is
a selector over the battlefield, `can_pay` refuses when nothing matches, and the
player is asked which one goes. So the tests here are about the two things that
are genuinely new — that the permanent lands in **hand** rather than the
graveyard, and that an empty pool makes the ability unavailable rather than free.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.costs import can_pay
from commanderblitz.engine.enums import ActionKind
from tests.conftest import only_oid

BOUNCER = {
    "id": "t_bouncer",
    "name": "Test Bouncer",
    "oracle_text": "{1}, Return a land you control to its owner's hand: Draw a card.",
    "mana_cost": "{4}{U}",
    "types": ["Creature"],
    "subtypes": ["Wizard"],
    "power": 2,
    "toughness": 4,
    "abilities": [
        {
            "kind": "activated",
            "text": "{1}, Return a land you control to its owner's hand: Draw a card.",
            "cost": {"mana": "{1}", "return_to_hand": {"types": ["Land"]}},
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
    ],
}


def board(builder, *, lands: int):
    game = (
        builder(players=2)
        .battlefield(0, ["t_bouncer"] + ["forest"] * lands)
        .library(0, ["island"] * 20)
        .build()
    )
    return game, only_oid(game, "t_bouncer")


def activate(game) -> bool:
    action = next(
        (a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE), None
    )
    if action is None:
        return False
    game.apply(action)
    return True


def settle(game) -> None:
    for _ in range(60):
        decision = game.pending()
        if decision is not None:
            choose = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
            )
            if choose is None:
                return
            game.apply(choose)
            continue
        if not game.state.stack:
            return
        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if action is None:
            return
        game.apply(action)


class TestTheLandComesBack:
    def test_it_goes_to_hand_not_the_graveyard(self, builder):
        """The whole difference from `sacrifice`, and the reason Meloku and
        Trench Behemoth cannot be written with one."""
        game, _ = board(builder, lands=4)
        before = len(game.state.players[0].hand)
        assert activate(game)
        settle(game)
        hand = game.state.players[0].hand
        returned = [
            oid for oid in hand if game.state.objects[oid].def_id == "forest"
        ]
        assert returned, "no Forest reached hand; the cost is not a bounce"
        assert len(hand) >= before + 1
        assert not [
            oid
            for oid in game.state.players[0].graveyard
            if game.state.objects[oid].def_id == "forest"
        ], "a Forest was graveyarded; this is sacrifice, not return to hand"

    def test_the_battlefield_shrinks_by_one(self, builder):
        game, _ = board(builder, lands=4)
        before = len(game.state.battlefield)
        assert activate(game)
        settle(game)
        assert len(game.state.battlefield) == before - 1


class TestAnEmptyPoolMakesItUnavailable:
    def test_with_no_land_the_ability_is_not_offered(self, builder):
        """Not offered-and-free. A bounce cost with nothing to bounce would make
        the ability cost only its mana, which is a strictly cheaper card."""
        game, _ = board(builder, lands=0)
        assert not any(a.kind is ActionKind.ACTIVATE for a in game.legal_actions())

    def test_can_pay_agrees(self, builder):
        game, source = board(builder, lands=0)
        cost = Cost.from_spec({"mana": "{1}", "return_to_hand": {"types": ["Land"]}})
        assert not can_pay(game.state, 0, cost, source)

    def test_with_a_land_it_is_payable(self, builder):
        game, source = board(builder, lands=4)
        cost = Cost.from_spec({"mana": "{1}", "return_to_hand": {"types": ["Land"]}})
        assert can_pay(game.state, 0, cost, source)


class TestTheSelectorNarrowsIt:
    def test_a_nonland_permanent_does_not_pay_a_land_cost(self, builder):
        """The selector is the printed clause: "return a **land** you control"."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_bouncer", "sol_ring"])
            .library(0, ["island"] * 20)
            .build()
        )
        source = only_oid(game, "t_bouncer")
        cost = Cost.from_spec({"return_to_hand": {"types": ["Land"]}})
        assert not can_pay(game.state, 0, cost, source)

    def test_it_does_not_reach_an_opponents_permanent(self, builder):
        """`controller` defaults to "you", as it does for `sacrifice` -- you may
        not pay a cost with something you do not control."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_bouncer"])
            .battlefield(1, ["forest"] * 3)
            .build()
        )
        source = only_oid(game, "t_bouncer")
        cost = Cost.from_spec({"return_to_hand": {"types": ["Land"]}})
        assert not can_pay(game.state, 0, cost, source)


class TestItIsNotATapOnlyCost:
    def test_a_mana_source_is_not_confused_by_it(self):
        """`is_tap_only` decides what the payment solver may treat as a mana
        source. A bounce cost left out of that check would let the solver tap a
        permanent for mana without paying the bounce."""
        assert not Cost.from_spec(
            {"tap": True, "return_to_hand": {"types": ["Land"]}}
        ).is_tap_only()
        assert Cost.from_spec({"tap": True}).is_tap_only()


class TestLoadTimeGuards:
    def test_a_bad_selector_key_is_refused(self):
        import copy

        card = copy.deepcopy(BOUNCER)
        card["abilities"][0]["cost"]["return_to_hand"] = {"typs": ["Land"]}
        with pytest.raises(Exception, match="unknown selector keys"):
            compile_card(CardModel.model_validate(card))

    def test_the_card_itself_loads(self):
        card = compile_card(CardModel.model_validate(BOUNCER))
        assert "Return to hand" in card.abilities[0].cost.describe()
