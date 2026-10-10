""""At the beginning of each of your postcombat main phases…"

    Florian, Voldaren Scion — "…look at the top X cards of your library, where X
    is the total amount of life your opponents lost this turn."

`TRIGGER_EVENTS` carried phase boundaries for upkeep, the draw step, begin
combat and the end step, and nothing for either main phase. `begin_combat` is
the nearest one and is on the **wrong side of combat**: a card hung on it reads
a life-loss tally from before the damage it is meant to count, which for Florian
is nearly the whole number.

The step already existed — `Step.POSTCOMBAT_MAIN` — and simply emitted no event
of its own.

Fired per *phase* rather than per turn, because the printed word is "each" and
an extra combat gives an extra postcombat main.

Not narrated in the frontend, which is deliberate and matches its siblings:
`begin_combat` and `end_step` have no `describeEvent` case either, and a phase
boundary that says "a phase began" adds nothing to a log that already shows the
step.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step
from tests.conftest import oids_of

WATCHER = "t_postcombat"  # gains 1 life at each of your postcombat mains


def board(builder, active: int = 0):
    return (
        builder(players=2)
        .battlefield(active, [WATCHER])
        .library(0, ["swamp"] * 40)
        .library(1, ["swamp"] * 40)
        .active(active)
        .step(Step.BEGIN_COMBAT)
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


class TestItFiresAfterCombat:
    def test_reaching_the_postcombat_main_triggers_it(self, builder):
        game = board(builder)
        life = game.state.players[0].life

        run_to(game, Step.END_STEP)

        assert game.state.players[0].life == life + 1

    def test_it_has_not_fired_before_combat(self, builder):
        """The whole reason `begin_combat` is the wrong event."""
        game = board(builder)
        life = game.state.players[0].life

        run_to(game, Step.DECLARE_ATTACKERS)

        assert game.state.players[0].life == life

    def test_it_does_not_fire_on_an_opponents_turn(self, builder):
        """"…each of **your** postcombat main phases."""
        game = board(builder, active=1)
        watcher = oids_of(game, WATCHER)[0]
        assert game.state.objects[watcher].controller == 1
        life = game.state.players[0].life

        run_to(game, Step.END_STEP)

        assert game.state.players[0].life == life
