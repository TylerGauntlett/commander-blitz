"""Channel: a row that needed no engine work.

**Channel** is bloodrush's shape with a different effect on the end: an
activated ability offered from hand whose cost is `discard_self`. Nothing new,
and it is here because the census listed it separately from bloodrush as though
the two were different problems.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.conftest import _default_answer

CHANNELER = "t_channeler"  # {3}{G} 3/3; from hand: {1}{G}, discard it -> gain 3


def settle(game, limit: int = 30) -> None:
    for _ in range(limit):
        decision = game.pending()
        if decision is not None and decision.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, decision))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return
        if decision is None:
            game._advance()
        else:
            game.apply(_default_answer(game, decision))
    raise AssertionError("nothing settled")


class TestChannel:
    def position(self, builder, lands=2):
        return (
            builder(players=2)
            .hand(0, [CHANNELER])
            .battlefield(0, ["forest"] * lands)
            .build()
        )

    def lines(self, game) -> list:
        return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE]

    def test_it_is_activatable_from_hand(self, builder):
        game = self.position(builder)
        assert self.lines(game)

    def test_it_does_what_it_says(self, builder):
        game = self.position(builder)
        before = game.state.players[0].life
        game.apply(self.lines(game)[0])
        settle(game)
        assert game.state.players[0].life == before + 3

    def test_without_the_mana_it_is_not_offered(self, builder):
        game = self.position(builder, lands=0)
        assert self.lines(game) == []

    def test_the_card_is_gone_afterwards(self, builder):
        """`discard_self` is the cost, and it is also what satisfies the
        loader's guard on abilities offered from hand."""
        game = self.position(builder)
        assert len(game.state.players[0].hand) == 1
        game.apply(self.lines(game)[0])
        settle(game)
        assert game.state.players[0].hand == []
