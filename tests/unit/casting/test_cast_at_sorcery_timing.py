"""A spell that may be cast at instant speed, and pays for it at cleanup.

    "You may cast this spell as though it had flash. If you cast it any time a
    sorcery couldn't have been cast, the controller of the permanent it becomes
    sacrifices it at the beginning of the next cleanup step."   -- Necromancy

Three pieces, each with a near miss that loads and plays a different card.

**The permission is not the keyword.** `as_though_flash` is read by
`casting._timing_ok` beside `Keyword.FLASH`, and the permanent does not have
flash -- printing the keyword would hand it to everything that asks.

**The stamp is 307.1, not the phase.** A sorcery may be cast by the active
player, holding priority, in a main phase, while the stack is empty.
`cast_during: your_main` reads only the phase, so a copy cast in response during
your own main phase would escape the sacrifice it is owed. `stack.push_spell`
stamps `cast_at_sorcery_timing` before the spell joins the stack, and only
`Game._cast` -- the one cast made with priority -- may stamp it true: a cast
made while an effect resolves is never at sorcery timing.

**The sacrifice waits for cleanup, not the end step.** An `end_step` delay would
take the permanent a step early and miss a cast made during the end step
itself. `delay` at `cleanup` runs after the cleanup's turn-based actions, and
because 514.3a gives players priority when anything triggers there, a delay
that fires in cleanup makes the step repeat with a priority window.

The witness is Necromancy; `t_casr_rider` is its first paragraph.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import stack as stack_mod
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, oids_of, pass_until

RIDER = "t_casr_rider"  # as though it had flash + the cleanup sacrifice
PLAIN = "t_casr_plain"  # the same enchantment, sorcery speed, no rider
ANCHOR = "t_plain_instant"  # {W}, gain 1 life -- something to respond to


def position(builder, *, step: Step = Step.PRECOMBAT_MAIN, caster: int = 0, cards=(RIDER,)):
    """``cards`` in ``caster``'s hand with the mana for them, frozen at ``step``.

    Turn 1 is player 0's, so ``caster=1`` is the opponent casting on somebody
    else's turn. Both seats take full control, so every priority window --
    the cleanup step's 514.3a one included -- is a stop a test can stand in.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["swamp", "swamp", "plains"])
        .battlefield(1, ["swamp", "swamp", "plains"])
        .library(0, ["swamp"] * 10)
        .library(1, ["swamp"] * 10)
        .hand(caster, list(cards))
        .hand(1 - caster, [ANCHOR])
        .step(step)
        .build(advance=False)
    )
    for player in game.state.players:
        player.full_control = True
    game._advance()
    return game


def can_cast(game, card_id: str) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
        for a in game.legal_actions()
    )


def holding_priority(game, pid: int) -> bool:
    decision = game.pending()
    return (
        decision is not None
        and decision.kind is DecisionKind.PRIORITY
        and decision.player == pid
    )


def cast(game, card_id: str, pid: int) -> int:
    """Cast ``card_id`` for ``pid`` at the first window that allows it."""
    pass_until(game, lambda g: holding_priority(g, pid) and can_cast(g, card_id))
    action = action_for_card(game, ActionKind.CAST, card_id)
    game.apply(action)
    return action.source


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def cast_and_resolve(game, pid: int = 0) -> int:
    oid = cast(game, RIDER, pid)
    resolve(game)
    return oid


def zone(game, oid: int) -> Zone:
    return game.state.objects[oid].zone


def stamped(game, oid: int, value: bool) -> bool:
    return evaluate_condition(
        game.state, {"cast_at_sorcery_timing": value}, controller=0, source=oid
    )


def to_next_turn(game) -> None:
    turn = game.state.turn
    pass_until(game, lambda g: g.state.turn > turn)


class TestThePermission:
    @pytest.mark.parametrize("step", [Step.UPKEEP, Step.BEGIN_COMBAT, Step.END_STEP])
    def test_it_can_be_cast_outside_a_main_phase(self, builder, step):
        game = position(builder, step=step, cards=(RIDER, PLAIN))
        assert can_cast(game, RIDER)
        # The control: the same enchantment without the line is refused here,
        # so "can be cast" is the permission and not the position.
        assert not can_cast(game, PLAIN)

    def test_it_can_be_cast_on_an_opponents_turn(self, builder):
        game = position(builder, caster=1, cards=(RIDER, PLAIN))
        pass_until(game, lambda g: holding_priority(g, 1))
        assert can_cast(game, RIDER)
        assert not can_cast(game, PLAIN)

    def test_the_permanent_does_not_have_flash(self, builder):
        game = position(builder)
        oid = cast_and_resolve(game)
        assert "flash" not in {str(k) for k in chars(game.state, oid).keywords}
        assert "flash" not in game.state.card(oid).keywords


class TestCastAtSorceryTiming:
    def test_the_stamp_is_true(self, builder):
        game = position(builder)
        oid = cast_and_resolve(game)
        assert stamped(game, oid, True)
        assert not stamped(game, oid, False)

    def test_it_survives_the_cleanup_step(self, builder):
        game = position(builder)
        oid = cast_and_resolve(game)
        to_next_turn(game)
        assert zone(game, oid) is Zone.BATTLEFIELD
        assert not game.state.delayed_triggers


class TestCastAnyOtherTime:
    @pytest.mark.parametrize("step", [Step.UPKEEP, Step.BEGIN_COMBAT, Step.END_STEP])
    def test_it_is_sacrificed_at_this_turns_cleanup(self, builder, step):
        game = position(builder, step=step)
        oid = cast_and_resolve(game)
        assert stamped(game, oid, False)
        # Still there for the rest of the turn: the end step is not the
        # cleanup step, and a cast *in* the end step resolves in it.
        pass_until(game, lambda g: g.state.step is Step.CLEANUP or g.state.turn > 1)
        assert game.state.turn == 1
        assert zone(game, oid) is Zone.GRAVEYARD

    def test_the_end_step_still_has_it(self, builder):
        game = position(builder, step=Step.UPKEEP)
        oid = cast_and_resolve(game)
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        assert zone(game, oid) is Zone.BATTLEFIELD

    def test_in_response_during_your_own_main_phase(self, builder):
        """The case `cast_during: your_main` gets wrong: the right phase, the
        right player, and a spell already on the stack."""
        game = position(builder, cards=(RIDER, ANCHOR))
        cast(game, ANCHOR, 0)
        assert game.state.stack
        oid = cast(game, RIDER, 0)
        resolve(game)
        assert stamped(game, oid, False)
        assert evaluate_condition(
            game.state, {"cast_during": "your_main"}, controller=0, source=oid
        )
        to_next_turn(game)
        assert zone(game, oid) is Zone.GRAVEYARD

    def test_an_opponents_cast_in_your_main_phase(self, builder):
        """Not the active player, so not sorcery timing; its controller is
        the one who sacrifices it."""
        game = position(builder, caster=1)
        oid = cast_and_resolve(game, pid=1)
        assert game.state.objects[oid].controller == 1
        assert stamped(game, oid, False)
        to_next_turn(game)
        assert zone(game, oid) is Zone.GRAVEYARD
        assert oid in game.state.players[1].graveyard

    def test_a_cast_while_an_effect_resolves_is_not_sorcery_timing(self, builder):
        """Nobody has priority mid-resolution, so 307.1 cannot be met there --
        even in your own main phase with nothing else on the stack."""
        game = position(builder)
        pass_until(game, lambda g: holding_priority(g, 0))
        oid = next(o for o in game.state.players[0].hand if game.state.card(o).id == RIDER)
        assert not game.state.stack
        stack_mod.push_spell(game.state, oid, 0)
        assert not game.state.objects[oid].cast_at_sorcery_timing


class TestTheCleanupStep:
    def test_the_sacrifice_gives_priority_and_cleanup_repeats(self, builder):
        """514.3a: something triggered in cleanup, so players get priority
        there, and another cleanup step follows the window."""
        game = position(builder, step=Step.END_STEP)
        oid = cast_and_resolve(game)
        pass_until(game, lambda g: g.state.step is Step.CLEANUP)
        assert zone(game, oid) is Zone.GRAVEYARD
        assert game.state.cleanup_repeat
        assert game.pending().kind is DecisionKind.PRIORITY
        assert game.state.turn == 1

    def test_a_cast_in_that_window_waits_for_the_repeated_cleanup(self, builder):
        """The next cleanup step after a 514.3a window is the one it leads
        into, so a second copy cast there is gone before the turn ends."""
        game = position(builder, step=Step.END_STEP, cards=(RIDER, RIDER))
        first = cast_and_resolve(game)
        pass_until(game, lambda g: g.state.step is Step.CLEANUP)
        assert zone(game, first) is Zone.GRAVEYARD
        second = cast(game, RIDER, 0)
        resolve(game)
        assert game.state.step is Step.CLEANUP
        assert zone(game, second) is Zone.BATTLEFIELD
        to_next_turn(game)
        assert zone(game, second) is Zone.GRAVEYARD

    def test_a_cleanup_with_nothing_due_gives_no_priority(self, builder):
        game = position(builder)
        cast_and_resolve(game)
        pass_until(game, lambda g: g.state.step is Step.CLEANUP or g.state.turn > 1)
        assert game.state.turn > 1


class TestOnlyThisLifesCast:
    def test_a_permanent_that_arrived_another_way_answers_neither(self, builder):
        """The `cast_*` stamps are never cleared, so a rider cast at instant
        speed and later put back onto the battlefield still carries one. It is
        a new object that was not cast (400.7), and neither answer is true."""
        game = position(builder, step=Step.UPKEEP)
        oid = cast_and_resolve(game)
        move_object(game.state, oid, Zone.GRAVEYARD, cause="test")
        move_object(game.state, oid, Zone.BATTLEFIELD, cause="test")
        assert game.state.objects[oid].cast_step is not None
        assert not stamped(game, oid, False)
        assert not stamped(game, oid, True)

    def test_a_card_never_cast_answers_neither(self, builder):
        game = (
            builder(players=2).battlefield(0, [PLAIN]).build(advance=False)
        )
        oid = oids_of(game, PLAIN, 0)[0]
        assert not stamped(game, oid, False)
        assert not stamped(game, oid, True)


class TestTheLoader:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "",
                "mana_cost": "{B}",
                "types": ["Enchantment"],
                **extra,
            }
        )

    def test_as_though_flash_compiles(self):
        assert compile_card(self._card(as_though_flash=True)).as_though_flash
        assert not compile_card(self._card()).as_though_flash

    def _trigger(self, condition, step="cleanup"):
        return self._card(
            abilities=[
                {
                    "kind": "triggered",
                    "trigger": {"event": "self_enters", "source": "self", "condition": condition},
                    "effects": [
                        {
                            "op": "delay",
                            "step": step,
                            "effects": [{"op": "sacrifice", "objects": {"self_only": True}}],
                        }
                    ],
                }
            ]
        )

    def test_a_cleanup_delay_loads(self):
        compile_card(self._trigger({"cast_at_sorcery_timing": False}))

    def test_a_misspelled_step_is_still_refused(self):
        with pytest.raises(DslError, match="delay step"):
            compile_card(self._trigger({"cast_at_sorcery_timing": False}, step="clean_up"))

    def test_the_condition_takes_a_bool(self):
        with pytest.raises(DslError, match="cast_at_sorcery_timing"):
            compile_card(self._trigger({"cast_at_sorcery_timing": "false"}))
