"""The as-enters copy's "enters with" counters, counted by the cast's X.

    "You may have this creature enter as a copy of any creature on the
    battlefield, except it enters with X additional +1/+1 counters on it."
                                                          -- Altered Ego

Rule 707.9b puts the counters inside the copy effect, and 614.1c makes the
whole clause a replacement, so the copy is never seen without them. X is the
value announced while casting (601.2b); `stack.resolve` records it as
`cast_x` before the move, and `self_enters_as_copy`'s ``except_.enters_with``
reads it the way `self_enters_with_counters` does (Goldvein Hydra).

Two near misses are different cards. Read without X, ``{"x": true}`` is 0 and
the copy enters at its copied size. Written instead as a separate
`self_enters_with_counters`, the counters would arrive whether or not a copy
was chosen, so a declined Altered Ego would survive as a 0/0 with X counters;
printed, it is a 0/0 that dies (704.5f).
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import action_for_card, only_oid, pass_until, plus_one_counters
from tests.unit.copies.test_enters_as_copy import name_of

EGO = "t_eacxx_ego"  # {X}{G} 0/0, copy of any creature with X extra counters
BEAR = "t_bear"  # 2/2 vanilla


def cast_for(builder, x: int, *, say_yes: bool = True, theirs=(BEAR,)):
    """Cast the Ego announcing X = ``x``, copying the opponent's Bear."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8)
        .battlefield(1, list(theirs))
        .hand(0, [EGO])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    game.apply(action_for_card(game, ActionKind.CAST, EGO))
    for _ in range(60):
        pending = game.pending()
        if pending is None or (
            pending.kind is DecisionKind.PRIORITY and not game.state.stack
        ):
            break
        if pending.kind is DecisionKind.PRIORITY:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
            continue
        if pending.kind is DecisionKind.MAY:
            want = ActionKind.YES if say_yes else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        choices = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
        if pending.kind is DecisionKind.CHOOSE_X:
            game.apply(next(a for a in choices if a.choice == x))
            continue
        game.apply(
            next(
                (
                    a
                    for a in choices
                    if a.targets and game.state.objects[a.targets[0].id].def_id == BEAR
                ),
                choices[0],
            )
        )
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return game


def egos(game) -> list[int]:
    return [o for o in game.state.battlefield if game.state.objects[o].def_id == EGO]


class TestTheCopyEntersWithXCounters:
    def test_x_becomes_counters_on_the_copy(self, builder):
        game = cast_for(builder, 3)
        oid = only_oid(game, EGO, 0)
        assert name_of(game, oid) == "Test Bear"
        assert plus_one_counters(game, oid) == 3
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (5, 5)

    def test_a_different_x(self, builder):
        game = cast_for(builder, 6)
        assert plus_one_counters(game, only_oid(game, EGO, 0)) == 6

    def test_x_of_zero_is_the_plain_copy(self, builder):
        """The boundary: no additional counters, and the copy is still a 2/2."""
        game = cast_for(builder, 0)
        oid = only_oid(game, EGO, 0)
        assert plus_one_counters(game, oid) == 0
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (2, 2)


class TestTheCountersBelongToTheCopy:
    def test_declined_it_is_a_dead_0_0(self, builder):
        """The counters are the exception's, not a separate "enters with":
        no copy, no counters, and the printed 0/0 dies (704.5f)."""
        game = cast_for(builder, 4, say_yes=False)
        assert egos(game) == []

    def test_nothing_to_copy_is_a_dead_0_0(self, builder):
        game = cast_for(builder, 4, theirs=())
        assert egos(game) == []
