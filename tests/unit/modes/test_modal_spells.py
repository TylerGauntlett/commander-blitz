"""A modal spell has to do a *different* thing per mode.

The risk with "Choose one —" is not that it crashes; it is that every mode ends
up running the same ops, or that the mode nobody drives in a sandbox is the one
that was never wired up. Gate 5 of the authoring verifier drives the first mode
only, so the other two are pinned here, one assertion each.

Simic Charm is the case worth using: its three modes touch three different
subsystems -- a pump, a keyword grant to a whole board, and a zone change.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import action_for_card, pass_until

PUMP, HEXPROOF, BOUNCE = 0, 1, 2


def cast_with_mode(builder, mode: int):
    """Cast Simic Charm at the opponent's creature and pick one mode."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest", "island", "grizzly_bears"])
        .battlefield(1, ["grizzly_bears"])
        .hand(0, ["simic_charm"])
        .build()
    )
    theirs = next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == "grizzly_bears")

    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == "simic_charm"
        and any(ref.id == theirs for ref in a.targets)
    )
    game.apply(action)

    # Both players pass; the spell resolves and asks for its mode.
    pass_until(game, lambda g: _mode_decision(g) is not None)
    choose = next(
        a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == mode
    )
    game.apply(choose)
    return game, theirs


def _mode_decision(game):
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_MODE:
        return decision
    return None


class TestEachModeDoesItsOwnThing:
    def test_pump_gives_plus_three(self, builder):
        game, theirs = cast_with_mode(builder, PUMP)
        got = chars(game.state, theirs)
        assert (got.power, got.toughness) == (5, 5), "a 2/2 bear with +3/+3"
        assert game.state.objects[theirs].zone is Zone.BATTLEFIELD

    def test_hexproof_covers_every_permanent_you_control(self, builder):
        game, theirs = cast_with_mode(builder, HEXPROOF)
        mine = list(game.state.battlefield_objects(0))
        assert mine, "the sandbox should have given us a board"
        assert all("hexproof" in chars(game.state, o.oid).keywords for o in mine)
        # Not the opponent's -- "permanents *you* control".
        assert "hexproof" not in chars(game.state, theirs).keywords

    def test_bounce_returns_it_to_its_owners_hand(self, builder):
        game, theirs = cast_with_mode(builder, BOUNCE)
        assert game.state.objects[theirs].zone is Zone.HAND
        assert theirs in game.state.players[1].hand, "its *owner's* hand, not the caster's"


class TestTheSpellItself:
    def test_it_is_castable_with_no_creature_anywhere(self, builder):
        """Mode two needs no target, so an empty board must not make it uncastable.

        This is what `optional` on the target spec buys, and without it the card
        would silently disappear from the hand's legal actions exactly when the
        hexproof mode is the one you want.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "island"])
            .hand(0, ["simic_charm"])
            .build()
        )
        assert action_for_card(game, ActionKind.CAST, "simic_charm") is not None
