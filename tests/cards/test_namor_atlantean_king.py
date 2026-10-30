"""Namor, Atlantean King, past what the behaviour gate can see.

    "Whenever Namor attacks a player who has more life than you, other
    creatures you control attacking that player get +2/+0 until end of turn."

The gate casts Namor and stops. Asserted here: only the creatures sent at
Namor's player are pumped -- not those at another opponent -- and only when
that player has more life than Namor's controller.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, attack_with, oids_of, only_oid, pt, settle

NAMOR = "namor_atlantean_king"
BEAR = "t_bear"


def swing(builder, *, their_life: int):
    b = builder(players=3).battlefield(0, [NAMOR, BEAR, BEAR])
    for pid in range(3):
        b.library(pid, ["forest"] * 20)
    game = b.active(0).step(Step.UNTAP).build()
    game.state.players[1].life = their_life
    for _ in range(80):
        decision = game.pending()
        if decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        game.apply(_default_answer(game, decision))
    namor = only_oid(game, NAMOR, 0)
    with_namor, elsewhere = oids_of(game, BEAR, 0)
    attack_with(game, namor, 1)
    attack_with(game, with_namor, 1)
    attack_with(game, elsewhere, 2)
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle(game)
    return game, namor, with_namor, elsewhere


def test_creatures_attacking_that_player_get_two_power(builder):
    game, namor, with_namor, elsewhere = swing(builder, their_life=50)
    assert pt(game, with_namor) == (4, 2)
    assert pt(game, elsewhere) == (2, 2), "attacking a different opponent"
    assert pt(game, namor) == (2, 2), "other creatures"


def test_nothing_when_that_player_has_no_more_life(builder):
    game, _, with_namor, _ = swing(builder, their_life=40)
    assert pt(game, with_namor) == (2, 2)
