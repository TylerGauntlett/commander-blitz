"""A control change that lasts "for as long as you control" its source.

"When Yuffie enters, gain control of target noncreature artifact **for as long
as you control Yuffie**." Yuffie, Materia Hunter is the printed shape
(`t_materia_thief` below is the trigger on its own). Rule 611.2b: an effect
that lasts "for as long as" a player controls an object ends the moment that
stops being true -- the source leaves the battlefield or changes controller --
and if the player doesn't control it when the effect would begin, the effect
does nothing. Ending a control effect is the handback, so the artifact goes
home through `change_control` the other way, as an Act of Treason does at
cleanup.

The near misses all load and all make a different card:

- **`duration: "permanent"`** outlives the thief. Kill it and the artifact
  stays stolen for the rest of the game -- a strictly better card.
- **`until_end_of_turn`** hands it back at the first cleanup, whatever happens
  to the thief.

And three things the duration must not do: come back when the oid does (a
blinked or stolen-and-returned thief is a new object, or a new period of
control), fall back to a permanent steal when the thief is already gone as the
trigger resolves, and undo somebody else's later steal of the artifact.
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
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import (
    change_control,
    clear_until_eot,
    clear_until_next_turn,
    end_effects_of_leaving_player,
)
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy, exile, move_object
from tests.conftest import action_for_card, only_oid, settle

SOURCE_BOUND = "as_long_as_you_control_source"
THIEF = "t_materia_thief"
RELIC = "t_cwy_relic"


def a_thief_and_a_relic(builder, players: int = 2):
    """Player 0 controls the thief, player 1 the relic; nothing is taken yet."""
    game = builder(players=players).battlefield(0, [THIEF]).battlefield(1, [RELIC]).build()
    return game, only_oid(game, THIEF), only_oid(game, RELIC)


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


def steal(duration: str = SOURCE_BOUND) -> dict:
    return {"op": "gain_control", "objects": {"target": "t1"}, "duration": duration}


def stolen(builder, players: int = 2):
    """`a_thief_and_a_relic` with the steal already made."""
    game, thief, relic = a_thief_and_a_relic(builder, players)
    run_op(game, steal(), source=thief, target=relic)
    assert game.state.objects[relic].controller == 0
    return game, thief, relic


def controller(game, oid: int) -> int:
    return game.state.objects[oid].controller


class TestThroughTheCard:
    def test_the_enters_trigger_takes_the_artifact(self, builder):
        game = builder(players=2).battlefield(1, [RELIC]).hand(0, [THIEF]).build()
        relic = only_oid(game, RELIC)
        game.apply(action_for_card(game, ActionKind.CAST, THIEF))
        settle(game)

        assert only_oid(game, THIEF) in game.state.battlefield
        assert controller(game, relic) == 0

    def test_killing_the_thief_gives_it_back(self, builder):
        game = builder(players=2).battlefield(1, [RELIC]).hand(0, [THIEF]).build()
        relic = only_oid(game, RELIC)
        game.apply(action_for_card(game, ActionKind.CAST, THIEF))
        settle(game)
        destroy(game.state, only_oid(game, THIEF))

        assert controller(game, relic) == 1


class TestItHasNoClock:
    def test_it_survives_cleanup(self, builder):
        game, _, relic = stolen(builder)
        clear_until_eot(game.state)
        assert controller(game, relic) == 0

    def test_it_survives_every_untap_step(self, builder):
        game, _, relic = stolen(builder)
        for seat in (0, 1):
            clear_until_next_turn(game.state, seat)
        assert controller(game, relic) == 0

    def test_until_end_of_turn_is_the_near_miss(self, builder):
        game, thief, relic = a_thief_and_a_relic(builder)
        run_op(game, steal("until_end_of_turn"), source=thief, target=relic)
        clear_until_eot(game.state)
        assert controller(game, relic) == 1

    def test_permanent_is_the_other_near_miss(self, builder):
        """The stronger card: the thief dies and the artifact stays."""
        game, thief, relic = a_thief_and_a_relic(builder)
        run_op(game, steal("permanent"), source=thief, target=relic)
        destroy(game.state, thief)
        assert controller(game, relic) == 0


class TestTheHandback:
    def test_the_thief_dying_ends_it(self, builder):
        game, thief, relic = stolen(builder)
        destroy(game.state, thief)
        assert controller(game, relic) == 1
        assert not game.state.objects[relic].until_eot

    def test_the_thief_exiled_ends_it(self, builder):
        game, thief, relic = stolen(builder)
        exile(game.state, thief)
        assert controller(game, relic) == 1

    def test_the_thief_changing_hands_ends_it(self, builder):
        """"…as long as **you** control": the thief stolen is the duration over,
        even though the thief is still on the battlefield."""
        game, thief, relic = stolen(builder)
        change_control(game.state, thief, 1)
        assert controller(game, relic) == 1

    def test_the_handback_is_a_control_change(self, builder):
        """302.6 and the event ride the handback, as they ride Act of Treason's."""
        game, thief, relic = stolen(builder)
        game.state.turn += 1
        before = len(game.state.events)
        destroy(game.state, thief)

        changed = [
            e
            for e in game.state.events[before:]
            if e.type is EventType.CONTROL_CHANGED and e.source == relic
        ]
        assert len(changed) == 1
        assert changed[0].data["to"] == 1
        assert game.state.objects[relic].entered_turn == game.state.turn

    def test_a_blinked_thief_does_not_take_it_again(self, builder):
        """The oid survives the round trip; 400.7 says the object does not."""
        game, thief, relic = stolen(builder)
        exile(game.state, thief)
        move_object(game.state, thief, Zone.BATTLEFIELD)

        assert controller(game, thief) == 0
        assert controller(game, relic) == 1

    def test_getting_the_thief_back_does_not_restart_it(self, builder):
        game, thief, relic = stolen(builder)
        change_control(game.state, thief, 1, duration="until_end_of_turn")
        clear_until_eot(game.state)  # the thief comes home

        assert controller(game, thief) == 0
        assert controller(game, relic) == 1

    def test_a_later_steal_of_the_artifact_is_not_undone(self, builder):
        """Seat 2 takes the relic for good afterwards: the thief leaving ends an
        effect that is no longer the reason anybody controls it."""
        game, thief, relic = stolen(builder, players=3)
        change_control(game.state, relic, 2)
        destroy(game.state, thief)
        assert controller(game, relic) == 2

    def test_the_relic_leaving_takes_the_entry(self, builder):
        game, thief, relic = stolen(builder)
        destroy(game.state, relic)
        assert game.state.objects[relic].zone is Zone.GRAVEYARD
        destroy(game.state, thief)
        assert game.state.objects[relic].zone is Zone.GRAVEYARD

    def test_another_sources_steal_is_its_own(self, builder):
        """Two relics taken by two thieves: losing one returns only its own."""
        game = builder(players=2).battlefield(0, [THIEF, THIEF]).battlefield(1, [RELIC, RELIC]).build()
        first, second = (o for o in game.state.battlefield if game.state.objects[o].def_id == THIEF)
        mine, theirs = (o for o in game.state.battlefield if game.state.objects[o].def_id == RELIC)
        run_op(game, steal(), source=first, target=mine)
        run_op(game, steal(), source=second, target=theirs)

        destroy(game.state, first)
        assert (controller(game, mine), controller(game, theirs)) == (1, 0)

    def test_the_thief_leaving_the_game_ends_it(self, builder):
        """800.4a: the effect giving the departed seat control ends, and the
        relic goes back to the seat it came from rather than out with the thief."""
        game, _, relic = stolen(builder, players=3)
        end_effects_of_leaving_player(game.state, 0)
        assert controller(game, relic) == 1


class TestItMustBeginUnderYourControl:
    def test_a_thief_already_gone_takes_nothing(self, builder):
        """Not a permanent steal either: the effect does nothing."""
        game, thief, relic = a_thief_and_a_relic(builder)
        destroy(game.state, thief)
        run_op(game, steal(), source=thief, target=relic)

        assert controller(game, relic) == 1
        assert not game.state.objects[relic].until_eot

    def test_a_thief_an_opponent_controls_takes_nothing(self, builder):
        game, thief, relic = a_thief_and_a_relic(builder, players=3)
        change_control(game.state, thief, 2)
        run_op(game, steal(), source=thief, target=relic)

        assert controller(game, relic) == 1


class TestTheLoader:
    def _card(self, effect: dict, *, types: list[str], triggered: bool) -> CardModel:
        target = {"id": "t1", "kind": "permanent", "selector": {"types": ["Artifact"]}}
        data: dict = {
            "id": "t_cwy_probe",
            "name": "Test CWY Probe",
            "mana_cost": "{1}{R}",
            "types": types,
            "oracle_text": "Gain control of target artifact for as long as you control this.",
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

    def test_a_permanents_ability_loads(self):
        compile_card(self._card(steal(), types=["Creature"], triggered=True))

    def test_a_spell_is_refused(self):
        """A spell is not a permanent anyone controls: it would do nothing."""
        with pytest.raises(DslError, match="as_long_as_you_control_source"):
            compile_card(self._card(steal(), types=["Sorcery"], triggered=False))

    def test_a_misspelled_duration_is_refused(self):
        with pytest.raises(DslError, match="unknown gain_control duration"):
            compile_card(self._card(steal("as_long_as_you_control"), types=["Creature"], triggered=True))
