"""A targeted action says why the permanents it skips cannot be chosen.

While a spell is choosing a target the client lets you click only what the
action list names, and a hexproof creature it skips used to be focusable and
silent. `LegalActionDTO.untargetable` carries the engine's reason, from the same
`target_refusal` that `can_be_targeted` is answered by.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Step
from commanderblitz.server.sessions import GameSession

PUMP = "t_pump_spell"  # "Target creature gets +3/+3 until end of turn."
BEAR = "t_bear"
HEXPROOF = "t_hexproof"


def session_for(builder) -> GameSession:
    game = (
        builder(players=2)
        .battlefield(0, ["forest", BEAR])
        .battlefield(1, [HEXPROOF])
        .hand(0, [PUMP])
        .library(0, ["forest"] * 5)
        .library(1, ["forest"] * 5)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    session = GameSession(game_id="g", seats=[], seed=0, data=None, game=game)
    session._refresh_actions()
    return session


def oid_of(session: GameSession, card_id: str) -> int:
    state = session.game.state
    return next(oid for oid in state.battlefield if state.card_of(state.objects[oid]).id == card_id)


def test_an_opponents_hexproof_creature_is_named_with_its_reason(builder):
    session = session_for(builder)
    hexproof = oid_of(session, HEXPROOF)
    casts = [a for a in session.actions_for(0) if a.kind == "cast" and a.targets]
    assert casts, "the pump spell should be castable at the bear"
    for dto in casts:
        assert dto.untargetable == {str(hexproof): "Hexproof"}


def test_an_untargeted_action_carries_no_reasons(builder):
    session = session_for(builder)
    assert all(dto.untargetable == {} for dto in session.actions_for(0) if not dto.targets)
