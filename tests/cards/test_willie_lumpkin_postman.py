"""Willie Lumpkin, Postman, past what the behaviour gate can see.

    "Whenever Willie Lumpkin deals combat damage to an opponent, you draw a
    card and that player may draw a card. If they do, that player can't attack
    you or permanents you control during their next turn."

The gate casts Willie and stops. Asserted here: the hit opponent who draws is
barred from Willie's controller and their planeswalker for exactly their next
turn, and one who declines is not barred at all.
"""

from __future__ import annotations

from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, attack_with, only_oid

WILLIE = "willie_lumpkin_postman"
BEAR = "t_bear"
WALKER = "t_walker"


def hit(builder, *, accept: bool):
    b = builder(players=3).battlefield(0, [WILLIE, WALKER]).battlefield(1, [BEAR])
    for pid in range(3):
        b.library(pid, ["forest"] * 30)
    game = b.active(0).step(Step.UNTAP).build()
    willie = only_oid(game, WILLIE, 0)
    hands = [len(p.hand) for p in game.state.players]
    attacked = False
    for _ in range(400):
        decision = game.pending()
        if decision is None or game.state.step >= Step.POSTCOMBAT_MAIN:
            break
        if decision.kind is DecisionKind.DECLARE_ATTACKERS and not attacked:
            attack_with(game, willie, 1)
            attacked = True
            continue
        if decision.kind is DecisionKind.MAY and accept:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))
            continue
        game.apply(_default_answer(game, decision))
    return game, hands


def bear_closed(game) -> tuple[bool, bool]:
    bear = only_oid(game, BEAR, 1)
    walker = only_oid(game, WALKER, 0)
    return (
        combat_mod._attack_prohibited(game.state, bear, 0),
        combat_mod._attack_prohibited(game.state, bear, 0, permanent=walker),
    )


def pass_to_turn(game, turn: int) -> None:
    for _ in range(2000):
        if game.state.turn >= turn and game.state.step >= Step.PRECOMBAT_MAIN:
            return
        game.apply(_default_answer(game, game.pending()))
    raise AssertionError("never reached the turn")


def test_both_draw_and_the_opponent_is_barred_on_their_next_turn(builder):
    game, hands = hit(builder, accept=True)
    assert len(game.state.players[1].hand) == hands[1] + 1
    assert bear_closed(game) == (False, False), "pending on Willie's turn"
    pass_to_turn(game, 2)
    assert game.state.active_player == 1
    assert bear_closed(game) == (True, True)
    pass_to_turn(game, 4)
    assert bear_closed(game) == (False, False)


def test_declining_the_draw_bars_nothing(builder):
    game, hands = hit(builder, accept=False)
    assert len(game.state.players[1].hand) == hands[1]
    assert game.state.attack_restrictions == []
