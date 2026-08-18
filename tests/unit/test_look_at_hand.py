""""{T}: Look at target player's hand." — Glasses of Urza.

Looking is not revealing, and the engine had only the second. `reveal` emits a
public event: every seat at the table learns what it named. At a four-player
pod that is a materially different card — Glasses of Urza tells *you* what one
opponent is holding, and a reveal would tell that opponent's other two
opponents as well, which changes who is ahead.

So the effect needed a channel the engine did not have: information one seat is
entitled to and the others are not. It is recorded on the card as
`GameObject.revealed_to` rather than emitted, because `player_view` is rebuilt
from scratch on every request and has to answer "may this seat see this card?"
long after the ability resolved — an event that scrolled off the log cannot.

The tests that matter here are the negative ones. A leak is silent: it looks
like a working card to the player who benefits, and nothing fails.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.errors import DslError
from automtg.engine.serialize import player_view
from automtg.engine.structs import TargetRef

BEAR = "t_bear"
FOREST = "forest"


def look(game, controller: int, target: int) -> None:
    """Resolve "look at target player's hand", targeting ``target``."""
    ctx = EffectContext(
        state=game.state,
        controller=controller,
        targets={"t1": (TargetRef.player(target),)},
    )
    result = OPS["look_at_hand"](ctx, {"op": "look_at_hand", "player": {"target": "t1"}})
    if result is not None:
        list(result)


def revealed_names(game, seat: int, pid: int) -> list[str]:
    view = player_view(game.state, seat)
    return [c["name"] for c in view["players"][pid]["hand_revealed"]]


def board(builder, players: int = 3):
    game = builder(players=players)
    game.hand(1, [BEAR, FOREST])
    return game.build(advance=False)


class TestWhatTheLookerSees:
    def test_the_cards_arrive_in_hand_revealed(self, builder):
        game = board(builder)
        look(game, 0, 1)
        assert len(revealed_names(game, 0, 1)) == 2

    def test_nothing_moves_zone(self, builder):
        """"Look at" leaves the hand exactly as it was."""
        game = board(builder)
        before = list(game.state.players[1].hand)
        look(game, 0, 1)
        assert game.state.players[1].hand == before

    def test_a_card_drawn_afterwards_is_not_shown(self, builder):
        """You looked at the hand you looked at. The boundary that would be
        wrong if the entitlement were stored on the player instead of the card."""
        game = board(builder)
        look(game, 0, 1)
        from automtg.engine.primitives import draw_cards

        draw_cards(game.state, 1, 1)
        assert len(game.state.players[1].hand) == 3, "they drew"
        assert len(revealed_names(game, 0, 1)) == 2, "the new card was never seen"


class TestWhatEverybodyElseSees:
    def test_a_third_player_learns_nothing(self, builder):
        """The whole difference from `reveal`, and the test that would fail if
        somebody 'simplified' this back into a public event."""
        game = board(builder)
        look(game, 0, 1)
        assert revealed_names(game, 2, 1) == []

    def test_the_victim_sees_no_change(self, builder):
        game = board(builder)
        look(game, 0, 1)
        view = player_view(game.state, 1)
        assert view["players"][1]["hand_revealed"] == [], "your own hand is in `hand`"
        assert len(view["players"][1]["hand"]) == 2

    def test_an_opponents_hand_is_still_hidden_without_a_look(self, builder):
        game = board(builder)
        view = player_view(game.state, 0)
        assert view["players"][1]["hand"] is None
        assert view["players"][1]["hand_revealed"] == []

    def test_looking_at_one_player_does_not_show_another(self, builder):
        game = builder(players=3)
        game.hand(1, [BEAR])
        game.hand(2, [FOREST])
        g = game.build(advance=False)
        look(g, 0, 1)
        assert len(revealed_names(g, 0, 1)) == 1
        assert revealed_names(g, 0, 2) == []


class TestTheEntitlementEndsWithTheObject:
    def test_it_clears_when_the_card_changes_zones(self, builder):
        """A card that left and came back is a new object (400.7), and having
        seen it in hand once does not entitle you to see it forever."""
        game = board(builder)
        look(game, 0, 1)
        oid = game.state.players[1].hand[0]
        assert 0 in game.state.objects[oid].revealed_to
        game.state.objects[oid].reset_permanent_state()
        assert game.state.objects[oid].revealed_to == set()


class TestTheLoaderGuard:
    def test_a_well_formed_effect_loads(self):
        _validate_effect(
            {"op": "look_at_hand", "player": {"target": "t1"}}, "test", {"t1": "player"}
        )

    def test_a_missing_player_is_refused(self):
        """Whose hand is the whole ability; defaulting it picks a victim."""
        with pytest.raises(DslError, match="player"):
            _validate_effect({"op": "look_at_hand"}, "test", {})
