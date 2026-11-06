"""A permanent's enters trigger whose target count is the X it was cast with.

    "When this artifact enters, support X. (Put a +1/+1 counter on each of up
    to X target creatures.)"                              -- Blitzball Stadium

Rule 603.3d declares a triggered ability's targets as it is put on the stack,
and 107.3m says an X on a permanent's enters trigger is the X paid to cast it.
`triggers` binds that X (``obj.cast_x``) and the stack item's resolution reads
it, so the effects always knew it -- but `targeting.target_count` evaluated
``{"x": true}`` with no bindings, read 0, and "up to X targets" offered none.
The trigger's bindings now reach the count, so the declaration and the
resolution agree on one X.

The witness is `t_sxt_stadium` in `tests/data/support_x_trigger.cards.json`.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import action_for_card, find_action, oids_of, pass_until, plus_one_counters

STADIUM = "t_sxt_stadium"
BEAR = "t_bear"


def cast_for(builder, x: int, *, bears: int = 3):
    """Cast the Stadium for X = ``x`` and take every target it offers."""
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 8 + [BEAR] * bears)
        .hand(0, [STADIUM])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    game.apply(action_for_card(game, ActionKind.CAST, STADIUM))
    ceilings: list[int] = []
    for _ in range(80):
        pending = game.pending()
        if pending is None or (pending.kind is DecisionKind.PRIORITY and not game.state.stack):
            break
        actions = game.legal_actions()
        if pending.kind is DecisionKind.PRIORITY:
            game.apply(next(a for a in actions if a.kind is ActionKind.PASS))
            continue
        choices = [a for a in actions if a.kind is ActionKind.CHOOSE]
        if pending.kind is DecisionKind.CHOOSE_X:
            game.apply(next(a for a in choices if a.choice == x))
            continue
        if pending.kind is not DecisionKind.CHOOSE_OBJECTS:
            break
        if not pending.selected:
            ceilings.append(pending.max_count)
        game.apply(choices[0] if choices else find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
    return game, ceilings


def counters_placed(game) -> int:
    return sum(plus_one_counters(game, oid) for oid in oids_of(game, BEAR, 0))


class TestTheTargetCountIsTheCastX:
    def test_x_of_two_supports_two(self, builder):
        game, ceilings = cast_for(builder, 2)
        assert ceilings == [2]
        assert counters_placed(game) == 2

    def test_x_caps_at_the_creatures_there_are(self, builder):
        game, ceilings = cast_for(builder, 5, bears=3)
        assert ceilings == [3]
        assert counters_placed(game) == 3

    def test_x_of_zero_supports_none(self, builder):
        """The boundary: up to zero targets is no targets, and nothing grows."""
        game, ceilings = cast_for(builder, 0)
        assert ceilings == []
        assert counters_placed(game) == 0
