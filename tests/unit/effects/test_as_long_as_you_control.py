"""A one-shot grant that lasts "for as long as you control" its source.

"Royal Guard -- When Thancred Waters enters, another target legendary permanent
you control gains indestructible **for as long as you control Thancred
Waters**." Thancred Waters is the witness (`t_royal_guard` below is the
trigger on its own). Rule 611.2b: an effect that lasts "for as long as" a
player controls an object ends the moment that stops being true -- the source
leaves the battlefield or changes controller -- and if the player doesn't
control it when the effect would begin, the effect does nothing.

The near misses all load and all make a different card:

- **`duration: "permanent"`** outlives Thancred. Kill the monk and the legend
  stays indestructible for the rest of the game.
- **`until_end_of_turn`** ends at the first cleanup, so the guard protects
  nobody on the opponents' turns, which is when it is printed for.
- **A `grant_keyword` static** ends with its source, but its ``affects``
  filter is re-read on every recompute and has no key for "the one permanent
  the enters trigger targeted".

And two things the duration must not do: come back when the oid does (a
blinked or stolen-and-returned Thancred is a new object, or a new period of
control, and the old effect is over for good), and fall back to a shorter
clock when the source is already gone as the trigger resolves.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import (
    change_control,
    clear_until_eot,
    clear_until_next_turn,
)
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy, exile, move_object
from tests.conftest import action_for_card, keywords, only_oid, pt, settle

SOURCE_BOUND = "as_long_as_you_control_source"


def a_guard_beside_a_legend(builder):
    """Player 0 controls `t_royal_guard` and the legend `t_alc_legend`; the
    guard's trigger has not run, so nothing is granted yet."""
    game = builder(players=2).battlefield(0, ["t_royal_guard", "t_alc_legend"]).build()
    return game, only_oid(game, "t_royal_guard"), only_oid(game, "t_alc_legend")


def run_op(game, spec: dict, *, source: int, target: int, controller: int = 0) -> None:
    """Resolve one effect op from ``source`` with ``target`` bound to ``t1``."""
    ctx = EffectContext(
        state=game.state,
        controller=controller,
        source_oid=source,
        targets={"t1": (TargetRef.obj(target),)},
    )
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def guard(duration: str = SOURCE_BOUND) -> dict:
    return {
        "op": "grant_keyword",
        "keywords": ["indestructible"],
        "objects": {"target": "t1"},
        "duration": duration,
    }


def guarded(builder):
    """`a_guard_beside_a_legend` with the grant already made."""
    game, source, legend = a_guard_beside_a_legend(builder)
    run_op(game, guard(), source=source, target=legend)
    return game, source, legend


class TestThroughTheCard:
    def test_the_enters_trigger_protects_the_legend(self, builder):
        game = builder(players=2).battlefield(0, ["t_alc_legend"]).hand(0, ["t_royal_guard"]).build()
        legend = only_oid(game, "t_alc_legend")
        game.apply(action_for_card(game, ActionKind.CAST, "t_royal_guard"))
        settle(game)

        assert only_oid(game, "t_royal_guard") in game.state.battlefield
        assert "indestructible" in keywords(game, legend)

    def test_a_nonlegendary_creature_is_not_a_target(self, builder):
        """"Another target **legendary** permanent": the bear is never offered,
        and with no legal target the trigger is removed (603.3d)."""
        game = builder(players=2).battlefield(0, ["t_alc_bear"]).hand(0, ["t_royal_guard"]).build()
        bear = only_oid(game, "t_alc_bear")
        game.apply(action_for_card(game, ActionKind.CAST, "t_royal_guard"))
        settle(game)

        assert "indestructible" not in keywords(game, bear)
        assert "indestructible" not in keywords(game, only_oid(game, "t_royal_guard"))


class TestItHasNoClock:
    def test_it_survives_cleanup(self, builder):
        game, _, legend = guarded(builder)
        clear_until_eot(game.state)
        assert "indestructible" in keywords(game, legend)

    def test_it_survives_every_untap_step(self, builder):
        game, _, legend = guarded(builder)
        for seat in (0, 1):
            clear_until_next_turn(game.state, seat)
        assert "indestructible" in keywords(game, legend)

    def test_until_end_of_turn_is_the_near_miss(self, builder):
        """The same op on the ordinary clock is gone after one cleanup."""
        game, source, legend = a_guard_beside_a_legend(builder)
        run_op(game, guard("until_end_of_turn"), source=source, target=legend)
        clear_until_eot(game.state)
        assert "indestructible" not in keywords(game, legend)


class TestWearingOff:
    def test_the_source_dying_ends_it(self, builder):
        game, source, legend = guarded(builder)
        destroy(game.state, source)
        assert "indestructible" not in keywords(game, legend)

    def test_a_blinked_source_does_not_bring_it_back(self, builder):
        """The oid survives the round trip; 400.7 says the object does not."""
        game, source, legend = guarded(builder)
        exile(game.state, source)
        move_object(game.state, source, Zone.BATTLEFIELD)

        assert game.state.objects[source].controller == 0
        assert "indestructible" not in keywords(game, legend)

    def test_the_source_changing_hands_ends_it(self, builder):
        game, source, legend = guarded(builder)
        change_control(game.state, source, 1)
        assert "indestructible" not in keywords(game, legend)

    def test_getting_the_source_back_does_not_restart_it(self, builder):
        """611.2b: the duration ended when control changed, and a later
        handback is a new period of control nobody granted anything for."""
        game, source, legend = guarded(builder)
        change_control(game.state, source, 1, duration="until_end_of_turn")
        clear_until_eot(game.state)  # the steal ends and hands it back

        assert game.state.objects[source].controller == 0
        assert "indestructible" not in keywords(game, legend)

    def test_the_protected_permanent_changing_hands_does_not_end_it(self, builder):
        """The duration is about the *source*: a stolen legend stays
        indestructible for as long as player 0 keeps the guard."""
        game, _, legend = guarded(builder)
        change_control(game.state, legend, 1)
        assert "indestructible" in keywords(game, legend)

    def test_another_sources_grant_is_its_own(self, builder):
        """Two sources on one legend: losing the first leaves the second's.
        (The second is the bear, since two legendary guards would meet the
        legend rule.)"""
        game = builder(players=2).battlefield(0, ["t_royal_guard", "t_alc_bear", "t_alc_legend"]).build()
        first, second = only_oid(game, "t_royal_guard"), only_oid(game, "t_alc_bear")
        legend = only_oid(game, "t_alc_legend")
        run_op(game, guard(), source=first, target=legend)
        run_op(game, guard(), source=second, target=legend)

        destroy(game.state, first)
        assert "indestructible" in keywords(game, legend)
        destroy(game.state, second)
        assert "indestructible" not in keywords(game, legend)

    def test_the_protected_permanent_leaving_takes_the_entry(self, builder):
        game, _, legend = guarded(builder)
        exile(game.state, legend)
        assert not game.state.objects[legend].until_eot


class TestItMustBeginUnderYourControl:
    def test_a_source_already_gone_grants_nothing(self, builder):
        """Not an until-end-of-turn grant either: the effect does nothing."""
        game, source, legend = a_guard_beside_a_legend(builder)
        destroy(game.state, source)
        run_op(game, guard(), source=source, target=legend)

        assert "indestructible" not in keywords(game, legend)
        assert not game.state.objects[legend].until_eot

    def test_a_source_an_opponent_controls_grants_nothing(self, builder):
        game, source, legend = a_guard_beside_a_legend(builder)
        change_control(game.state, source, 1)
        run_op(game, guard(), source=source, target=legend)

        assert "indestructible" not in keywords(game, legend)


class TestPump:
    def pump(self) -> dict:
        return {
            "op": "pump",
            "power": 2,
            "toughness": 2,
            "objects": {"target": "t1"},
            "duration": SOURCE_BOUND,
        }

    def test_the_pump_outlives_cleanup_and_ends_with_the_source(self, builder):
        game, source, legend = a_guard_beside_a_legend(builder)
        printed = pt(game, legend)
        run_op(game, self.pump(), source=source, target=legend)
        clear_until_eot(game.state)
        assert pt(game, legend) == (printed[0] + 2, printed[1] + 2)

        destroy(game.state, source)
        assert pt(game, legend) == printed
        assert chars(game.state, legend).power == printed[0]


class TestTheLoader:
    def _card(self, effect: dict, *, types: list[str], triggered: bool) -> CardModel:
        target = {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
        data: dict = {
            "id": "t_alc_probe",
            "name": "Test ALC Probe",
            "mana_cost": "{1}{W}",
            "types": types,
            "oracle_text": "Target creature gains indestructible for as long as you control this.",
        }
        if triggered:
            data |= {"power": 1, "toughness": 1}
            data["abilities"] = [
                {
                    "kind": "triggered",
                    "text": data["oracle_text"],
                    "trigger": {"event": "self_enters"},
                    "targets": [target],
                    "effects": [effect],
                }
            ]
        else:
            data |= {"targets": [target], "spell_effects": [effect]}
        return CardModel.model_validate(data)

    @pytest.mark.parametrize(
        "effect",
        [
            {"op": "grant_keyword", "keywords": ["indestructible"], "objects": {"target": "t1"}},
            {"op": "pump", "power": 1, "toughness": 1, "objects": {"target": "t1"}},
        ],
    )
    def test_a_permanents_ability_loads(self, effect):
        compile_card(self._card({**effect, "duration": SOURCE_BOUND}, types=["Creature"], triggered=True))

    def test_a_spell_is_refused(self):
        """A spell is not a permanent anyone controls: it would do nothing."""
        effect = {**guard(), "objects": {"target": "t1"}}
        with pytest.raises(DslError, match="as_long_as_you_control_source"):
            compile_card(self._card(effect, types=["Instant"], triggered=False))

    def test_lock_abilities_does_not_take_it(self):
        effect = {"op": "lock_abilities", "objects": {"target": "t1"}, "duration": SOURCE_BOUND}
        with pytest.raises(DslError, match="unknown lock_abilities duration"):
            compile_card(self._card(effect, types=["Creature"], triggered=True))

    def test_a_misspelled_duration_is_refused(self):
        effect = {**guard("as_long_as_you_control")}
        with pytest.raises(DslError, match="unknown grant_keyword duration"):
            compile_card(self._card(effect, types=["Creature"], triggered=True))
