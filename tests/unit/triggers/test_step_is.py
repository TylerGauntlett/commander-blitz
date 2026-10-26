"""`step_is`: "when this enters **during the declare attackers step**".

Misleading Signpost and Portal Mage print the clause, and it is not flavour: the
reselection that follows it means something only while attackers have been
declared and no blocker has. Outside that step the trigger must not exist at all,
or a flashed-in Signpost in an opponent's end step would ask a question about a
combat that is over.

No condition could say it. `cast_during` is the near miss and reads the wrong
moment and the wrong object: it is the step stamped on a *spell* as it was cast
(addendum), false for anything that was never cast, and a phase rather than a
step -- "combat" is five steps, and the declare blockers step is one where a
reselection would move an attacker that has already been blocked. `is_your_turn`
is whose turn, not which step. `step_is` reads `state.step`, the step the game is
in now, by the `Step` enum's lower-cased names (the spelling `cast_before_step`
already takes).

The trigger's condition is an intervening-if, asked as it triggers and again as
it resolves (603.4). Both answers agree for a step condition, because a step does
not end while the stack is non-empty (500.2): a trigger that went on the stack in
the declare attackers step resolves in it. The witness is Misleading Signpost.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.conditions import (
    STEP_NAMES,
    evaluate_condition,
    validate_condition,
)
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import action_for_card, attack_with, find_action, pass_until, settle

BEACON = "t_step_beacon"  # {0} flash artifact: enters during declare attackers -> charge counter
BEAR = "t_bear"


def position(builder):
    """Player 0 attacks with a bear; player 1 holds the beacon. ``(game, bear)``."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR])
        .hand(1, [BEACON])
        .active(0)
        .step(Step.UNTAP)
        .build()
    )
    bear = next(o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR)
    return game, bear


def can_flash_beacon(game) -> bool:
    decision = game.pending()
    return (
        decision is not None
        and decision.kind is DecisionKind.PRIORITY
        and decision.player == 1
        and any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BEACON
            for a in game.legal_actions()
        )
    )


def flash_in_at(game, step: Step) -> int:
    """Pass until player 1 may cast the beacon in ``step``, cast it, and resolve
    everything. Returns the charge counters the beacon ended with."""
    pass_until(game, lambda g: g.state.step is step and can_flash_beacon(g))
    action = action_for_card(game, ActionKind.CAST, BEACON)
    game.apply(action)
    settle(game)
    return game.state.objects[action.source].counters.get("charge", 0)


def declare(game, bear: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, bear, defender=1)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


class TestTheStepTheGameIsIn:
    @pytest.mark.parametrize("step", list(Step))
    def test_it_is_true_in_its_own_step_and_no_other(self, builder, step):
        game = builder(players=2).step(step).build(advance=False)
        cond = {"step_is": "declare_attackers"}
        assert evaluate_condition(game.state, cond, controller=0) is (
            step is Step.DECLARE_ATTACKERS
        )

    def test_a_list_is_any_of_them(self, builder):
        game = builder(players=2).step(Step.COMBAT_DAMAGE).build(advance=False)
        both = {"step_is": ["first_strike_damage", "combat_damage"]}
        assert evaluate_condition(game.state, both, controller=0) is True
        assert evaluate_condition(
            game.state, {"step_is": ["declare_blockers"]}, controller=0
        ) is False

    def test_every_step_has_a_name(self):
        assert {s.name.lower() for s in Step} == STEP_NAMES


class TestTheEntersTrigger:
    def test_entering_during_declare_attackers_triggers(self, builder):
        game, bear = position(builder)
        declare(game, bear)
        assert flash_in_at(game, Step.DECLARE_ATTACKERS) == 1

    def test_entering_in_the_beginning_of_combat_does_not(self, builder):
        """One step early: the combat has begun and nothing is attacking yet."""
        game, _ = position(builder)
        assert flash_in_at(game, Step.BEGIN_COMBAT) == 0

    def test_entering_during_declare_blockers_does_not(self, builder):
        """One step late, and the case `cast_during: "combat"` would get wrong."""
        game, bear = position(builder)
        declare(game, bear)
        assert flash_in_at(game, Step.DECLARE_BLOCKERS) == 0


class TestLoadTime:
    @pytest.mark.parametrize(
        "bad", ["declare_attackers_step", "combat", "attackers", [], ["declare_attackers", "x"], 5]
    )
    def test_a_step_the_turn_does_not_have_is_refused(self, bad):
        with pytest.raises(DslError, match="step_is"):
            validate_condition({"step_is": bad}, "card")

    def test_the_real_names_load(self):
        validate_condition({"step_is": "declare_attackers"}, "card")
        validate_condition({"step_is": ["upkeep", "end_step"]}, "card")
