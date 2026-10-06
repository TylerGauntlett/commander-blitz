"""Nezahal, Primal Tide -- the card the delayed-trigger work was for.

Its blink ability is the only thing in the pool that exiles a permanent and
brings it back later, and the interesting part is the gap: between the two
halves, the object is in exile with nothing on the battlefield pointing at it.
The delayed trigger holds its own `source_oid`, which is what makes the return
possible at all -- so that is what these assertions are really about.
"""

from __future__ import annotations

import pytest

from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import only_oid, pass_until


def settle(game):
    """Answer everything until priority comes back with an empty stack.

    The blink ability's cost is a discard, which raises a decision *before* the
    ability is even on the stack -- so "has it finished" is not "is the stack
    empty" until priority is the thing being asked for.
    """
    pass_until(
        game,
        lambda g: (
            not g.state.stack
            and (d := g.pending()) is not None
            and d.kind is DecisionKind.PRIORITY
        ),
    )


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 4 + ["nezahal_primal_tide"])
        .hand(0, ["island", "island", "island", "island"])
        .library(0, ["island"] * 20)
        .build()
    )


def blink(game):
    nezahal = only_oid(game, "nezahal_primal_tide")
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == nezahal
    )
    game.apply(action)
    return nezahal


class TestTheBlink:
    def test_it_leaves_immediately_and_comes_back_tapped(self, builder):
        game = board(builder)
        nezahal = blink(game)
        settle(game)
        assert game.state.objects[nezahal].zone is Zone.EXILE, "gone the moment it resolves"

        # Stop the moment it is back *or* the turn rolls over, so the assertion
        # below pins the timing too: "the next end step" is this turn's, and a
        # card that came back a turn late would fail here rather than pass.
        start = game.state.turn
        pass_until(
            game,
            lambda g: g.state.objects[nezahal].zone is Zone.BATTLEFIELD
            or g.state.turn > start,
        )
        obj = game.state.objects[nezahal]
        assert obj.zone is Zone.BATTLEFIELD, "back at this turn's end step"
        assert obj.tapped, "'return it to the battlefield tapped'"
        assert obj.controller == obj.owner, "'under its owner's control'"

    def test_it_costs_three_cards(self, builder):
        game = board(builder)
        before = len(game.state.players[0].hand)
        blink(game)
        settle(game)
        assert len(game.state.players[0].hand) == before - 3

    def test_it_is_not_offered_with_two_cards_in_hand(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 4 + ["nezahal_primal_tide"])
            .hand(0, ["island", "island"])
            .build()
        )
        nezahal = only_oid(game, "nezahal_primal_tide")
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == nezahal
        ]


class TestTheDrawTrigger:
    def test_an_opponents_noncreature_spell_draws(self, registry, builder):
        """And an opponent's *creature* spell does not -- the filter is the card."""
        if "divination" not in registry or "grizzly_bears" not in registry:
            pytest.skip("the pool has no pair of spells to tell apart")

        def opponent_casts(card_id: str) -> int:
            game = (
                builder(players=2)
                .battlefield(0, ["island"] * 4 + ["nezahal_primal_tide"])
                .battlefield(1, ["island"] * 4 + ["forest"] * 4)
                .hand(1, [card_id])
                .library(0, ["island"] * 20)
                .library(1, ["island"] * 20)
                .build()
            )
            before = len(game.state.players[0].hand)
            pass_until(
                game,
                lambda g: any(
                    a.kind is ActionKind.CAST
                    and g.state.objects[a.source].def_id == card_id
                    for a in g.legal_actions()
                ),
            )
            cast = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == card_id
            )
            game.apply(cast)
            pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
            return len(game.state.players[0].hand) - before

        # Divination draws its caster two cards; it is the *opponent's* hand
        # that grows there, so the count below is Nezahal's trigger alone.
        assert opponent_casts("grizzly_bears") == 0
        assert opponent_casts("divination") == 1


class TestNoMaximumHandSize:
    def test_it_does_not_discard_at_cleanup(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 4 + ["nezahal_primal_tide"])
            .hand(0, ["island"] * 12)
            .library(0, ["island"] * 20)
            .build()
        )
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert len(game.state.players[0].hand) >= 12, "seven is not a limit here"
