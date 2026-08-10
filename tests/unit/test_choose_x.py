"""Choosing X, rather than always spending everything.

`legality._cast_variant` used to compute `mana.max_affordable_x` and stamp it
onto the action, so a Hydra was always cast for the largest X the board could
pay for and the player was never asked. X is now a `DecisionKind.CHOOSE_X`
raised by `game._cast` *before* the cost is paid; legality keeps calling
`max_affordable_x`, but only as a gate on whether the spell appears at all.

The ordering that catches people out: the decision is pending before the spell
is on the stack, so "wait until the stack is empty" is already true the moment
`apply(cast)` returns. Every test here waits on the permanent instead.
"""

from __future__ import annotations

import pytest

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind
from tests.conftest import action_for_card, oids_of, only_oid, pass_until

PLUS_ONE = "+1/+1"

#: "{X}{G}", a 0/1 that enters with X +1/+1 counters. Four Forests is X <= 3.
HYDRA = "t_x_spell"


def cast_hydra(builder, forests: int = 4):
    game = builder().hand(0, [HYDRA]).battlefield(0, ["forest"] * forests).build()
    game.apply(action_for_card(game, ActionKind.CAST, HYDRA))
    return game


def choose(game, x: int):
    """Answer the pending CHOOSE_X with a specific value."""
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x
    )
    game.apply(action)


class TestTheQuestionIsAsked:
    def test_casting_an_x_spell_raises_choose_x(self, builder):
        game = cast_hydra(builder)
        assert game.pending().kind is DecisionKind.CHOOSE_X

    def test_it_is_asked_before_the_spell_is_on_the_stack(self, builder):
        # Rule 601.2b order, and the reason a `not stack` predicate is a trap.
        game = cast_hydra(builder)
        assert game.state.stack == []

    def test_the_action_itself_carries_no_x(self, builder):
        game = builder().hand(0, [HYDRA]).battlefield(0, ["forest"] * 4).build()
        assert action_for_card(game, ActionKind.CAST, HYDRA).x == 0

    def test_the_ceiling_is_what_the_board_can_pay(self, builder):
        # {X}{G} with four Forests: one pays the {G}, three are left for X.
        game = cast_hydra(builder, forests=4)
        assert game.pending().context["max_x"] == 3
        assert [o.value for o in game.pending().options] == [0, 1, 2, 3]

    def test_it_says_how_much_a_point_costs(self, builder):
        game = cast_hydra(builder)
        assert game.pending().context["per_point"] == 1

    def test_the_ordinal_is_the_value(self, builder):
        # What lets the RL encoder read a choice slot as X without a lookup.
        game = cast_hydra(builder)
        for i, option in enumerate(game.pending().options):
            assert option.value == i


class TestTheAnswerIsWhatGetsPaid:
    @pytest.mark.parametrize("x", [0, 1, 2, 3])
    def test_the_hydra_arrives_at_the_chosen_size(self, builder, x):
        game = cast_hydra(builder)
        choose(game, x)
        pass_until(game, lambda g: oids_of(g, HYDRA, 0))
        hydra = only_oid(game, HYDRA, 0)
        assert game.state.objects[hydra].counter(PLUS_ONE) == x
        assert chars(game.state, hydra).power == x

    def test_x_zero_still_resolves(self, builder):
        # Not a no-op and not a cancel: a 0/1 Hydra is a legal thing to do, and
        # it is the value the old code could never produce.
        game = cast_hydra(builder)
        choose(game, 0)
        pass_until(game, lambda g: oids_of(g, HYDRA, 0))
        assert chars(game.state, only_oid(game, HYDRA, 0)).power == 0

    def test_choosing_less_than_the_maximum_leaves_mana_untapped(self, builder):
        game = cast_hydra(builder, forests=4)
        choose(game, 1)
        # {G} for the pip, {1} for X: two Forests, not four.
        tapped = [o for o in game.state.battlefield_objects(0) if o.tapped]
        assert len(tapped) == 2


class TestTheGateStillHolds:
    def test_an_unaffordable_spell_is_not_offered(self, builder):
        # No lands at all: not even X = 0 is payable, so it must not appear.
        game = builder().hand(0, [HYDRA]).build()
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == HYDRA
        ]

    def test_the_floor_is_enough_to_be_offered(self, builder):
        # Exactly one Forest pays {G} and nothing else. X = 0 is the only legal
        # size, and the spell is still castable -- pinning X to the maximum
        # would have offered the same thing, but this is the boundary that
        # decides whether "gate" and "value" agree.
        game = builder().hand(0, [HYDRA]).battlefield(0, ["forest"]).build()
        assert action_for_card(game, ActionKind.CAST, HYDRA) is not None

    def test_a_forced_x_is_not_asked(self, builder):
        # `ask_x` declines to ask a question with one answer, the way `ask_mode`
        # does. With one Forest the only X is 0, so the spell should resolve
        # without stopping.
        game = builder().hand(0, [HYDRA]).battlefield(0, ["forest"]).build()
        game.apply(action_for_card(game, ActionKind.CAST, HYDRA))
        assert game.pending().kind is not DecisionKind.CHOOSE_X


class TestTheAgentsAnswerIt:
    def test_the_passive_test_answerer_takes_the_maximum(self, builder):
        # `tests.conftest._default_answer` has no "decline" for X, and X = 0
        # would silently rewrite every existing test that casts an X spell by
        # passing priority. Maximum is what legality used to pin.
        game = cast_hydra(builder, forests=4)
        pass_until(game, lambda g: oids_of(g, HYDRA, 0))
        assert chars(game.state, only_oid(game, HYDRA, 0)).power == 3

    def test_the_heuristic_agent_takes_the_maximum(self, builder):
        from automtg.ai.agents.heuristic_agent import HeuristicAgent

        game = cast_hydra(builder, forests=4)
        decision = game.pending()
        chosen = HeuristicAgent(seed=0).act(game, decision.player, game.legal_actions())
        assert chosen.choice == 3
