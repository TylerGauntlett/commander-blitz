""""Choose up to five {P} worth of modes. You may choose the same mode more than once."

Season of Weaving. A **budget**, not a count: each mode has a price in paws, the
selection is a multiset, and repeats are explicitly allowed.

`choose_mode` counted modes and could not price them. Its near miss is not merely
inexact but far stronger than the card — `{"up_to": true, "count": 5}` permits
five copies of the three-paw mode, which for Season of Weaving is bouncing every
nonland permanent five times over for six mana.

Asked one mode at a time, because what is *affordable* shrinks as the budget is
spent: after three paws of five, only the one- and two-paw modes may still be
taken, and offering the three-paw one would offer a choice that cannot be paid
for. `TestTheOfferShrinks` is that claim.

A budgeted modal is declined by `cast_time_modes` and asked at resolution, for
the reason `asks_another_player` is: the repeated question has no shape at
601.2b. Season of Weaving owns no mode-targets so nothing is lost; a budgeted
card that did would need this revisited, and the docstring on `is_budgeted` says
so.

The test card prices its modes 1/2/3 and pays 1, 4 and 9 life, so every distinct
multiset within five paws reaches a **different** life total — which is what
lets the tests read the chosen multiset off the board rather than trusting the
prompt.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import pass_until

SPELL = "t_budget"


def position(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 8)
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 10)
        .hand(0, [SPELL])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_and_pick(game, picks: list[str]) -> int:
    """Cast the spell, answer the mode prompts with ``picks``, return life gained.

    Each entry is a label to choose; the run stops by declining once the list is
    exhausted, which is the "up to" half of the printed line.
    """
    game._advance()
    before = game.state.players[0].life
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SPELL
    )
    game.apply(action)

    for want in picks:
        pass_until(
            game,
            lambda g: (g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE)
            or not g.state.stack,
        )
        pending = game.pending()
        assert pending is not None and pending.kind is DecisionKind.CHOOSE_MODE, pending
        labels = [o.label for o in pending.options]
        assert want in labels, f"{want!r} not offered; got {labels}"
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == labels.index(want)
            )
        )

    # Decline the rest: `pass_until` answers a zero-floor choice by taking
    # nothing, which is exactly "stop here".
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return game.state.players[0].life - before


def offered_labels(game) -> list[str]:
    pending = game.pending()
    assert pending is not None and pending.kind is DecisionKind.CHOOSE_MODE
    return [o.label for o in pending.options]


class TestRepeatsAreAllowed:
    def test_the_same_mode_five_times(self, builder):
        """Five one-paw modes is exactly five paws, and five separate gains."""
        assert cast_and_pick(position(builder), ["One paw"] * 5) == 5

    def test_a_mixed_multiset(self, builder):
        """Three paws + two paws = five. 9 + 4 = 13."""
        assert cast_and_pick(position(builder), ["Three paws", "Two paws"]) == 13


class TestTheBudgetIsRespected:
    def test_two_three_paw_modes_do_not_fit(self, builder):
        """Six paws of a five-paw budget: the second is never on offer."""
        game = position(builder)
        game._advance()
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SPELL
        )
        game.apply(action)
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().kind is DecisionKind.CHOOSE_MODE,
        )
        labels = offered_labels(game)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == labels.index("Three paws")
            )
        )
        pass_until(
            game,
            lambda g: (g.pending() is not None and g.pending().kind is DecisionKind.CHOOSE_MODE)
            or not g.state.stack,
        )

        assert "Three paws" not in offered_labels(game), "two paws left, not three"


class TestTheOfferShrinks:
    def test_everything_is_offered_at_the_start(self, builder):
        game = position(builder)
        game._advance()
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SPELL
        )
        game.apply(action)
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().kind is DecisionKind.CHOOSE_MODE,
        )

        assert set(offered_labels(game)) == {"One paw", "Two paws", "Three paws"}


class TestTakingNothing:
    def test_declining_immediately_is_legal(self, builder):
        """"**up to** five paws worth" -- zero is a real answer."""
        assert cast_and_pick(position(builder), []) == 0
