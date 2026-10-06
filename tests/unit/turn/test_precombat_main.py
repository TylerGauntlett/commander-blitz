""""At the beginning of your first main phase…"

    Black Market Connections — "At the beginning of your first main phase,
    choose one or more — …"

`TRIGGER_EVENTS` had a phase boundary for the upkeep, the draw step, begin
combat, the postcombat main and the end step, and nothing for the *precombat*
one. `Step.PRECOMBAT_MAIN` had a branch in `turn.begin_step` already — the Saga
lore counters, 714.2d — and emitted no event beside it.

`upkeep` is the near miss and it is a step too early: it is before the draw, so
a card hung there hands its controller the turn's Treasure before they have seen
the card they drew, and pays the life a step sooner than the printed one. That
is why the claim pinned here is an **ordering** one and not only "it fired".

**"First" needs no ordinal.** An extra main phase inserted after a combat is a
*postcombat* main by 505.1b — which is why `postcombat_main` is fired per phase
and reads "each" — so PRECOMBAT_MAIN can happen only once in a turn and the
printed word is already exact.

Not narrated in the frontend, deliberately and for its siblings' reason:
`begin_combat`, `postcombat_main` and `end_step` have no `describeEvent` case
either, and a phase boundary that says "a phase began" adds nothing to a log
that already shows the step.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step
from tests.conftest import oids_of

WATCHER = "t_precombat"  # gains 1 life at the beginning of your first main phase
STARTING_LIFE = 40

#: The step boundaries of one turn, in printed order.
BOUNDARIES = (
    "upkeep",
    "draw_step",
    "precombat_main",
    "begin_combat",
    "postcombat_main",
    "end_step",
)


def board(builder, active: int = 0):
    """A position that `build` walks into the first main phase and past it.

    `build(advance=True)` auto-passes until somebody has a real decision, which
    here is declaring attackers — so the first main phase is already behind us
    when the position is handed back, and that is what makes it observable.
    """
    return (
        builder(players=2)
        .battlefield(active, [WATCHER])
        .library(0, ["swamp"] * 40)
        .library(1, ["swamp"] * 40)
        .active(active)
        .step(Step.UPKEEP)
        .max_turns(6)
        .build()
    )


def run_to(game, step: Step, limit: int = 200) -> None:
    """Advance until this turn reaches ``step``, answering passively.

    The turn is pinned as well as the step: without it the walk runs to the turn
    cap and the trigger fires once on every one of the controller's turns, which
    reads as a single trigger firing three times.
    """
    turn = game.state.turn
    for _ in range(limit):
        if game.over or game.state.turn != turn or game.state.step is step:
            return
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        preferred = (
            [a for a in actions if a.kind is ActionKind.PASS]
            or [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            or [a for a in actions if a.kind is ActionKind.NO]
            or actions
        )
        game.apply(preferred[0])


def boundaries(game) -> list[str]:
    return [e.type for e in game.state.events if e.type in BOUNDARIES]


class TestWhenItFires:
    def test_reaching_the_first_main_phase_triggers_it(self, builder):
        game = board(builder)
        assert game.state.players[0].life == STARTING_LIFE + 1

    def test_it_fires_after_the_draw_step_and_before_combat(self, builder):
        """The whole reason `upkeep` is the wrong event: it is before the draw."""
        fired = boundaries(board(builder))
        assert "precombat_main" in fired
        assert fired.index("draw_step") < fired.index("precombat_main")
        assert fired.index("precombat_main") < fired.index("begin_combat")

    def test_it_does_not_fire_again_for_the_main_phase_after_combat(self, builder):
        """One main phase is "first"; a main phase after a combat is not.

        505.1b is what makes the printed word "first" need no ordinal: every
        later main phase in the turn, inserted or not, is a *postcombat* one.
        """
        game = board(builder)
        mark = len(game.state.events)

        run_to(game, Step.END_STEP)

        later = [e.type for e in game.state.events[mark:] if e.type in BOUNDARIES]
        # One `apply` can walk several steps, so the log runs on into the next
        # turn before the turn pin can stop it. Cut at that turn's upkeep: what
        # is left is the rest of *this* turn, which is the claim.
        if "upkeep" in later:
            later = later[: later.index("upkeep")]
        assert "postcombat_main" in later, "a second main phase did happen"
        assert "precombat_main" not in later, "…and it was not a first one"
        assert game.state.players[0].life == STARTING_LIFE + 1

    def test_it_does_not_fire_on_an_opponents_turn(self, builder):
        """"…**your** first main phase."""
        game = board(builder, active=1)
        watcher = oids_of(game, WATCHER)[0]
        assert game.state.objects[watcher].controller == 1

        run_to(game, Step.END_STEP)

        assert game.state.players[0].life == STARTING_LIFE
