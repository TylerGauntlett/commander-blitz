"""`target_refusal` says why an object refuses every target line, and agrees with
`can_be_targeted` -- the reason a player is shown and the rule the engine applies
are one function, so they cannot drift.
"""

from __future__ import annotations

from commanderblitz.engine.targeting import can_be_targeted, target_refusal

HEXPROOF = "t_hexproof"
SHROUD = "t_shrouded"
BEAR = "t_bear"


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, [HEXPROOF, SHROUD, BEAR])
        .library(0, ["forest"] * 5)
        .library(1, ["forest"] * 5)
        .build()
    )


def oid_of(state, card_id: str) -> int:
    return next(oid for oid in state.battlefield if state.card_of(state.objects[oid]).id == card_id)


def test_hexproof_refuses_only_an_opponent(builder):
    state = board(builder).state
    oid = oid_of(state, HEXPROOF)
    assert target_refusal(state, 1, oid) == "Hexproof"
    assert target_refusal(state, 0, oid) is None


def test_shroud_refuses_everyone(builder):
    state = board(builder).state
    oid = oid_of(state, SHROUD)
    assert target_refusal(state, 0, oid) == "Shroud"
    assert target_refusal(state, 1, oid) == "Shroud"


def test_the_reason_and_the_rule_agree(builder):
    state = board(builder).state
    for oid in state.battlefield:
        for pid in (0, 1):
            assert can_be_targeted(state, pid, oid) == (target_refusal(state, pid, oid) is None)
