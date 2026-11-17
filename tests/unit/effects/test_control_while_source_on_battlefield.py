"""A control change that lasts "for as long as" its source "remains on the battlefield".

"When this creature enters, gain control of target creature **for as long as
this creature remains on the battlefield**." Sower of Temptation is the printed
shape (`t_wsb_tempter` below is the trigger on its own). Rule 611.2b: an effect
that lasts "for as long as" something is true ends the moment it stops being
true, and does nothing at all if it is already false when the effect would
begin. Here the one thing that must stay true is that the source is on the
battlefield, so the steal ends when the source leaves -- and only then. Ending a
control effect is the handback, so the creature goes home through
`change_control` the other way, as Yuffie's does.

The near misses all load and all make a different card:

- **`as_long_as_you_control_source`** (Yuffie, Materia Hunter's wording) also
  ends when the source changes controller. Steal the Sower and the creature it
  took goes home -- a weaker card than the printed one.
- **`permanent`** outlives the Sower: kill it and the creature stays stolen.
- **`until_end_of_turn`** hands it back at the first cleanup.

Opportunistic Dragon prints the same duration on a loss of all abilities, so
`lose_all_abilities` takes it too and ends the same way.

And three things the duration must not do: come back when the oid does (a
blinked source is a new object, 400.7), fall back to a permanent steal when the
source is already gone as the trigger resolves, and end because the source
merely changed hands.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import (
    change_control,
    clear_until_eot,
    clear_until_next_turn,
    end_effects_of_leaving_player,
)
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy, exile, move_object
from tests.conftest import action_for_card, keywords, only_oid, settle

WHILE_PRESENT = "while_source_on_battlefield"
TEMPTER = "t_wsb_tempter"
FLIER = "t_wsb_flier"


def a_tempter_and_a_flier(builder, players: int = 2):
    """Player 0 controls the tempter, player 1 the flier; nothing is taken yet."""
    game = builder(players=players).battlefield(0, [TEMPTER]).battlefield(1, [FLIER]).build()
    return game, only_oid(game, TEMPTER), only_oid(game, FLIER)


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


def steal(duration: str = WHILE_PRESENT) -> dict:
    return {"op": "gain_control", "objects": {"target": "t1"}, "duration": duration}


def strip(duration: str = WHILE_PRESENT) -> dict:
    return {"op": "lose_all_abilities", "objects": {"target": "t1"}, "duration": duration}


def stolen(builder, players: int = 2):
    """`a_tempter_and_a_flier` with the steal already made."""
    game, tempter, flier = a_tempter_and_a_flier(builder, players)
    run_op(game, steal(), source=tempter, target=flier)
    assert game.state.objects[flier].controller == 0
    return game, tempter, flier


def controller(game, oid: int) -> int:
    return game.state.objects[oid].controller


class TestThroughTheCard:
    def test_the_enters_trigger_takes_the_creature(self, builder):
        game = builder(players=2).battlefield(1, [FLIER]).hand(0, [TEMPTER]).build()
        flier = only_oid(game, FLIER)
        game.apply(action_for_card(game, ActionKind.CAST, TEMPTER))
        settle(game)

        assert only_oid(game, TEMPTER) in game.state.battlefield
        assert controller(game, flier) == 0

    def test_killing_the_tempter_gives_it_back(self, builder):
        game = builder(players=2).battlefield(1, [FLIER]).hand(0, [TEMPTER]).build()
        flier = only_oid(game, FLIER)
        game.apply(action_for_card(game, ActionKind.CAST, TEMPTER))
        settle(game)
        destroy(game.state, only_oid(game, TEMPTER))

        assert controller(game, flier) == 1


class TestItHasNoClock:
    def test_it_survives_cleanup(self, builder):
        game, _, flier = stolen(builder)
        clear_until_eot(game.state)
        assert controller(game, flier) == 0

    def test_it_survives_every_untap_step(self, builder):
        game, _, flier = stolen(builder)
        for seat in (0, 1):
            clear_until_next_turn(game.state, seat)
        assert controller(game, flier) == 0


class TestOnlyLeavingEndsIt:
    def test_the_tempter_dying_ends_it(self, builder):
        game, tempter, flier = stolen(builder)
        destroy(game.state, tempter)
        assert controller(game, flier) == 1
        assert not game.state.objects[flier].until_eot

    def test_the_tempter_exiled_ends_it(self, builder):
        game, tempter, flier = stolen(builder)
        exile(game.state, tempter)
        assert controller(game, flier) == 1

    def test_the_tempter_changing_hands_does_not_end_it(self, builder):
        """"…remains on the battlefield" says nothing about who controls it: a
        stolen Sower still holds the creature for the player who cast it."""
        game, tempter, flier = stolen(builder)
        change_control(game.state, tempter, 1)

        assert controller(game, tempter) == 1
        assert controller(game, flier) == 0

    def test_a_stolen_tempter_leaving_still_ends_it(self, builder):
        game, tempter, flier = stolen(builder)
        change_control(game.state, tempter, 1)
        destroy(game.state, tempter)
        assert controller(game, flier) == 1

    def test_the_controlling_near_miss_does_end_on_a_change_of_hands(self, builder):
        """Yuffie's duration on the same board: the weaker card."""
        game, tempter, flier = a_tempter_and_a_flier(builder)
        run_op(game, steal("as_long_as_you_control_source"), source=tempter, target=flier)
        change_control(game.state, tempter, 1)
        assert controller(game, flier) == 1

    def test_a_blinked_tempter_does_not_take_it_again(self, builder):
        """The oid survives the round trip; 400.7 says the object does not."""
        game, tempter, flier = stolen(builder)
        exile(game.state, tempter)
        move_object(game.state, tempter, Zone.BATTLEFIELD)

        assert controller(game, tempter) == 0
        assert controller(game, flier) == 1

    def test_the_thief_leaving_the_game_ends_it(self, builder):
        """800.4a: the effect giving the departed seat control ends, and the
        creature goes back to the seat it came from rather than out with them."""
        game, _, flier = stolen(builder, players=3)
        end_effects_of_leaving_player(game.state, 0)
        assert controller(game, flier) == 1


class TestItMustBeginOnTheBattlefield:
    def test_a_tempter_already_gone_takes_nothing(self, builder):
        """Not a permanent steal either: the duration ended before it began."""
        game, tempter, flier = a_tempter_and_a_flier(builder)
        destroy(game.state, tempter)
        run_op(game, steal(), source=tempter, target=flier)

        assert controller(game, flier) == 1
        assert not game.state.objects[flier].until_eot

    def test_a_tempter_an_opponent_controls_still_takes_it(self, builder):
        """The difference from Yuffie's duration at the start as well as the
        end: nothing asks who controls the source as the effect begins."""
        game, tempter, flier = a_tempter_and_a_flier(builder, players=3)
        change_control(game.state, tempter, 2)
        run_op(game, steal(), source=tempter, target=flier)

        assert controller(game, flier) == 0


class TestLosingAllAbilities:
    """Opportunistic Dragon: "…for as long as this creature remains on the
    battlefield, … it loses all abilities"."""

    def test_the_flier_loses_flying_while_the_source_stays(self, builder):
        game, tempter, flier = a_tempter_and_a_flier(builder)
        run_op(game, strip(), source=tempter, target=flier)
        clear_until_eot(game.state)
        for seat in (0, 1):
            clear_until_next_turn(game.state, seat)

        assert "flying" not in keywords(game, flier)

    def test_the_source_changing_hands_does_not_give_them_back(self, builder):
        game, tempter, flier = a_tempter_and_a_flier(builder)
        run_op(game, strip(), source=tempter, target=flier)
        change_control(game.state, tempter, 1)
        assert "flying" not in keywords(game, flier)

    def test_the_source_leaving_gives_them_back(self, builder):
        game, tempter, flier = a_tempter_and_a_flier(builder)
        run_op(game, strip(), source=tempter, target=flier)
        destroy(game.state, tempter)
        assert "flying" in keywords(game, flier)

    def test_a_source_already_gone_strips_nothing(self, builder):
        game, tempter, flier = a_tempter_and_a_flier(builder)
        destroy(game.state, tempter)
        run_op(game, strip(), source=tempter, target=flier)

        assert "flying" in keywords(game, flier)
        assert not game.state.objects[flier].until_eot


class TestTheLoader:
    def _card(self, effect: dict, *, types: list[str], triggered: bool) -> CardModel:
        target = {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
        data: dict = {
            "id": "t_wsb_probe",
            "name": "Test WSB Probe",
            "mana_cost": "{1}{U}",
            "types": types,
            "oracle_text": "Gain control of target creature for as long as this remains on the battlefield.",
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

    @pytest.mark.parametrize("effect", [steal(), strip()], ids=["gain_control", "lose_all_abilities"])
    def test_a_permanents_ability_loads(self, effect):
        compile_card(self._card(effect, types=["Creature"], triggered=True))

    @pytest.mark.parametrize("effect", [steal(), strip()], ids=["gain_control", "lose_all_abilities"])
    def test_a_spell_is_refused(self, effect):
        """A spell is on the stack as it resolves: it would do nothing."""
        with pytest.raises(DslError, match=WHILE_PRESENT):
            compile_card(self._card(effect, types=["Sorcery"], triggered=False))

    @pytest.mark.parametrize("op", ["grant_keyword", "pump"])
    def test_the_ops_that_do_not_take_it_refuse_it(self, op):
        effect = {"op": op, "objects": {"target": "t1"}, "duration": WHILE_PRESENT}
        if op == "grant_keyword":
            effect["keywords"] = ["flying"]
        with pytest.raises(DslError, match=f"unknown {op} duration"):
            compile_card(self._card(effect, types=["Creature"], triggered=True))

    def test_a_misspelled_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown gain_control duration"):
            compile_card(self._card(steal("while_on_battlefield"), types=["Creature"], triggered=True))
