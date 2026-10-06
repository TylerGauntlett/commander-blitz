"""Retrace: the graveyard as a third place to cast a card from.

"You may cast this card from your graveyard by discarding a land card in
addition to paying its other costs."

Three things have to hold, and each is a different way to get the card wrong.
The discard has to be a *land* — any card would make it far better than printed.
It has to be an addition to the mana cost, not a replacement. And because a
Sorcery returns to the graveyard on resolution, the card is *repeatable*, which
is the whole reason anyone plays it.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import _default_answer


def board(builder, hand: list[str], *, lands: int = 6):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .battlefield(1, ["grizzly_bears"])
        .hand(0, hand)
        .graveyard(0, ["spitting_image"])
        .library(0, ["island"] * 20)
        .build()
    )
    return game


def retrace_action(game):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "spitting_image"
        ),
        None,
    )


def settle(game):
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            return
        game.apply(_default_answer(game, decision))


class TestWhenItIsOffered:
    def test_with_a_land_in_hand_it_can_be_cast_from_the_graveyard(self, builder):
        assert retrace_action(board(builder, ["forest"])) is not None

    def test_with_no_land_in_hand_it_cannot(self, builder):
        """An empty hand is the case that separates retrace from flashback."""
        assert retrace_action(board(builder, [])) is None

    def test_a_nonland_card_will_not_do(self, builder):
        """'discarding a **land** card' -- any card would be a better spell."""
        assert retrace_action(board(builder, ["grizzly_bears"])) is None

    def test_without_the_mana_it_cannot_either(self, builder):
        """An addition to the cost, not a replacement for it."""
        assert retrace_action(board(builder, ["forest"], lands=2)) is None


class TestWhatItCosts:
    def test_it_takes_the_land_and_the_mana(self, builder):
        game = board(builder, ["forest", "grizzly_bears"])
        game.apply(retrace_action(game))
        settle(game)

        assert not [
            oid for oid in game.state.players[0].hand
            if game.state.card(oid).id == "forest"
        ], "the land was discarded"
        assert len(game.state.players[0].hand) == 1, "and only the land"
        assert sum(1 for o in game.state.battlefield_objects(0) if o.tapped) == 6

    def test_the_discarded_land_ends_up_in_the_graveyard(self, builder):
        game = board(builder, ["forest"])
        game.apply(retrace_action(game))
        settle(game)
        assert [
            oid
            for oid in game.state.players[0].graveyard
            if game.state.card(oid).id == "forest"
        ]


class TestWhatItDoes:
    def test_it_copies_the_creature_and_returns_to_the_graveyard(self, builder):
        game = board(builder, ["forest"])
        spell = retrace_action(game).source
        game.apply(retrace_action(game))
        settle(game)

        copies = [
            o
            for o in game.state.battlefield_objects(0)
            if o.def_id == "grizzly_bears" and o.is_token
        ]
        assert len(copies) == 1, "a token copy of the targeted creature"
        assert game.state.objects[spell].zone is Zone.GRAVEYARD, "ready to do it again"

    def test_it_can_be_cast_again_next_turn(self, builder):
        """The point of the mechanic: a Sorcery that returns is repeatable."""
        game = board(builder, ["forest", "forest"], lands=12)
        game.apply(retrace_action(game))
        settle(game)
        assert retrace_action(game) is not None, "still castable, still in the graveyard"
