"""Paying life as a cost, at the boundary.

Rule 118.4: a player may pay life down to exactly 0. Losing is a state-based
action that happens afterwards, not a reason the cost was illegal. The engine
used to require *strictly* more life than the cost, which quietly forbade the
one activation somebody at 4 life most wants -- and, once fetchlands are
authored, forbade cracking a fetch at 1 life.

Adanto Vanguard is the shipped card with a bare `pay_life` cost, so it is the
one asserted against here.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind
from tests.conftest import only_oid


def vanguard_at(builder, life: int):
    game = (
        builder(players=2)
        .battlefield(0, ["adanto_vanguard"])
        .life(0, life)
        .build()
    )
    return game, only_oid(game, "adanto_vanguard")


def can_activate(game, oid: int) -> bool:
    return any(
        a.kind is ActionKind.ACTIVATE and a.source == oid for a in game.legal_actions()
    )


class TestTheBoundary:
    def test_paying_exactly_all_your_life_is_legal(self, builder):
        game, oid = vanguard_at(builder, 4)
        assert can_activate(game, oid)

    def test_one_life_short_is_not(self, builder):
        game, oid = vanguard_at(builder, 3)
        assert not can_activate(game, oid)

    def test_comfortably_above_is_legal(self, builder):
        game, oid = vanguard_at(builder, 40)
        assert can_activate(game, oid)
