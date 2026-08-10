"""Kicker: one card, two things to do with it.

An additional cost is not a second card and not a mode. It is the same spell
cast for more mana, and the only record that it was paid lives on the stack item
-- by the time the spell resolves, nothing about the object says what it cost.

The properties worth pinning are that both lines are offered when both are
affordable, that the extra mana is actually taken, and that the kicked clause
fires only when it was.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import pass_until


def casts_of(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def board(builder, islands: int):
    """Into the Roil in hand, an opponent's creature to point it at."""
    return (
        builder(players=2)
        .battlefield(0, ["island"] * islands)
        .battlefield(1, ["grizzly_bears"])
        .hand(0, ["into_the_roil"])
        .library(0, ["island"] * 10)
        .build()
    )


class TestWhatIsOffered:
    def test_both_lines_when_both_are_affordable(self, builder):
        offered = casts_of(board(builder, 4), "into_the_roil")
        assert any(a.kicked for a in offered)
        assert any(not a.kicked for a in offered)

    def test_only_the_cheap_line_when_the_kicker_is_unaffordable(self, builder):
        """Two mana casts it; four kicks it. With two, kicking is not on offer."""
        offered = casts_of(board(builder, 2), "into_the_roil")
        assert offered, "the unkicked spell should still be castable"
        assert not any(a.kicked for a in offered)

    def test_the_two_lines_are_not_the_same_action(self):
        """They differ only in `kicked`, so equality has to see it.

        If it did not, the RL decoder and the server's index lookup would both
        be free to substitute one for the other.
        """
        from automtg.engine.actions import Action

        plain = Action(kind=ActionKind.CAST, source=1)
        kicked = Action(kind=ActionKind.CAST, source=1, kicked=True)
        assert plain != kicked
        assert plain.key() != kicked.key()


class TestWhatItCosts:
    def test_kicking_taps_more(self, builder):
        game = board(builder, 6)
        kicked = next(a for a in casts_of(game, "into_the_roil") if a.kicked)
        game.apply(kicked)
        tapped = sum(1 for o in game.state.battlefield_objects(0) if o.tapped)
        assert tapped == 4, "{1}{U} plus a {1}{U} kicker is four mana"


class TestWhatItDoes:
    def test_the_kicked_clause_fires_only_when_kicked(self, builder):
        """A/B on the same card: the bounce always happens, the draw does not."""

        def play(kicked: bool) -> tuple[int, int]:
            game = board(builder, 6)
            before = len(game.state.players[0].hand)
            action = next(a for a in casts_of(game, "into_the_roil") if a.kicked is kicked)
            game.apply(action)
            pass_until(game, lambda g: not g.state.stack)
            # -1 for the spell leaving hand; the rest is what the card did.
            drawn = len(game.state.players[0].hand) - (before - 1)
            return drawn, len(game.state.battlefield_objects(1))

        plain_drawn, plain_board = play(False)
        kicked_drawn, kicked_board = play(True)

        assert plain_board == kicked_board == 0, "the bounce happens either way"
        assert plain_drawn == 0
        assert kicked_drawn == 1


class TestHalfAKickerIsRejected:
    """The cost and the `if` only mean anything together.

    A card with one half loads cleanly and is wrong in a way nothing on the
    board would show: it either charges more for nothing, or has a clause that
    can never fire. Load time is the only place to catch it.
    """

    base = {
        "id": "half_kicker",
        "name": "Half Kicker",
        "types": ["Instant"],
        "spell_effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
    }

    def test_a_cost_nothing_reads(self):
        with pytest.raises(DslError, match="no effect reads"):
            compile_card(CardModel.model_validate({**self.base, "kicker": "{1}{U}"}))

    def test_a_clause_with_no_cost(self):
        payload = {
            **self.base,
            "spell_effects": [
                {
                    "op": "if",
                    "condition": {"kicked": True},
                    "then": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
        with pytest.raises(DslError, match="no 'kicker' cost"):
            compile_card(CardModel.model_validate(payload))

    def test_a_kicker_that_costs_nothing(self):
        payload = {
            **self.base,
            "kicker": "{0}",
            "spell_effects": [
                {
                    "op": "if",
                    "condition": {"kicked": True},
                    "then": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
        with pytest.raises(DslError, match="costs nothing"):
            compile_card(CardModel.model_validate(payload))
