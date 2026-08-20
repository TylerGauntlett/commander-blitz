"""Goldvein Hydra: a {X} creature that must arrive already the right size.

"This creature enters with X +1/+1 counters on it."

Rule 614.1c makes this a replacement rather than a trigger, and the reason is
visible on the card: Goldvein Hydra is a printed **0/0**. Written as a
`self_enters` trigger running `add_counters`, the permanent would touch the
battlefield at its printed size and the state-based action in 704.5f would bin
it before the trigger ever resolved. A replacement means the permanent is never
*seen* at 0/0, so it is never seen dead.

The replacement existed and the value did not reach it. `stack.resolve` writes
`cast_x` before the move, and it is one of the few fields
`reset_permanent_state` deliberately leaves alone, so X really was still
readable at this point — `_enter_battlefield` simply built its `EffectContext`
without one. `{"x": true}` therefore evaluated to 0, which is the worst possible
failure for this card: silent, and fatal on arrival.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import _default_answer, action_for_card

HYDRA = "t_x_hydra"  # {X}{G}, printed 0/0, enters with X +1/+1 counters


def cast_for(builder, x: int):
    """Cast the Hydra announcing X = `x`, and let it resolve."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 12)
        .hand(0, [HYDRA])
        .build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, HYDRA))
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.CHOOSE_X:
            pick = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == x
            )
            game.apply(pick)
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return game


def hydra(game):
    return next(
        game.state.objects[oid]
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == HYDRA
    )


class TestItArrivesTheRightSize:
    def test_x_becomes_counters(self, builder):
        game = cast_for(builder, 4)
        assert hydra(game).counter("+1/+1") == 4

    def test_and_the_characteristics_agree(self, builder):
        game = cast_for(builder, 4)
        assert chars(game.state, hydra(game).oid).power == 4
        assert chars(game.state, hydra(game).oid).toughness == 4

    def test_a_bigger_x(self, builder):
        game = cast_for(builder, 7)
        assert hydra(game).counter("+1/+1") == 7


class TestItIsNeverSeenAtItsPrintedSize:
    def test_it_survives(self, builder):
        """The whole reason 614.1c wants a replacement here.

        Before this change X read as 0, so a printed 0/0 arrived as a 0/0 and
        the toughness state-based action put it straight into the graveyard.
        This assertion is the regression: the Hydra is on the battlefield.
        """
        game = cast_for(builder, 3)
        assert hydra(game).zone is Zone.BATTLEFIELD

    def test_x_of_zero_really_does_die(self, builder):
        """The boundary, and proof the counters are doing the work.

        A Hydra cast for X=0 is a genuine 0/0 and 704.5f is right to bin it --
        so this is not the engine ignoring the rule, it is the rule applying to
        the one case where the printed size is the real size.
        """
        game = cast_for(builder, 0)
        survivors = [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == HYDRA
        ]
        assert survivors == [], "a 0/0 with no counters is dead on arrival"
