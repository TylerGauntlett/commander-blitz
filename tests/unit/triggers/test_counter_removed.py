"""Whenever a counter is removed -- the `counter_removed` trigger.

Watcher of Hours is the witness: "Whenever you remove a time counter from this
card while it's exiled, surveil 1. Suspend 6—{1}{U}". Three things make the
sentence, and each is a way to get it quietly wrong:

- **Every tick, the last included.** `last_counter_removed` is the near miss
  and hears only the removal that leaves none, so a Watcher built on it would
  surveil once in six upkeeps. Suspend's tick has to be a removal the trigger
  bus hears at all, which is why `suspend.tick` goes through
  `primitives.remove_counters` like every other road a counter comes off by.
- **One firing per counter** (603.2c): "a time counter" is singular, so one
  removal of two is two occurrences and two surveils.
- **"You" is the remover** (`removed_by`), not the card's controller: an
  opponent's effect taking a time counter off your exiled Watcher is not you
  removing it.

On the last tick the free cast and the trigger both come off the same removal.
The trigger is queued first and stacked above the spell, so the surveil
resolves before the Watcher does.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import suspend
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.objects import TIME_COUNTER
from commanderblitz.engine.primitives import remove_counters
from tests.conftest import pass_until

WATCHER = "watcher_of_hours"


def suspended(builder, *, counters: int | None = None):
    """Suspend the Watcher off two Islands; return ``(game, oid)``.

    Suspending hands the turn over, since player 0 has nothing else to do, so
    the game stands in the opponent's turn with six counters on the card --
    or ``counters``, rewritten after the fact to reach the last tick sooner.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 2)
        .hand(0, [WATCHER])
        .library(0, ["island"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.SUSPEND and game.state.objects[a.source].def_id == WATCHER
    )
    oid = action.source
    game.apply(action)
    obj = game.state.objects[oid]
    assert obj.zone is Zone.EXILE and obj.counter(TIME_COUNTER) == 6
    if counters is not None:
        obj.counters[TIME_COUNTER] = counters
    return game, oid


def surveils(game, pid: int = 0) -> list:
    return [e for e in game.state.events if e.type == EventType.SURVEILLED and e.player == pid]


def queued(game, oid: int) -> int:
    return sum(1 for p in game.state.pending_triggers if p.source_oid == oid)


def past_the_next_upkeep_of(game, pid: int) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn > turn
        and g.state.active_player == pid
        and g.state.step > Step.UPKEEP
        and not g.state.stack,
    )


class TestEveryTick:
    def test_suspending_it_removes_nothing_and_surveils_nothing(self, builder):
        game, _ = suspended(builder)
        assert surveils(game) == []

    def test_the_opponents_upkeep_is_no_tick(self, builder):
        game, oid = suspended(builder)
        pass_until(game, lambda g: g.state.active_player == 1 and g.state.step > Step.UPKEEP)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 6
        assert surveils(game) == []

    def test_each_of_your_upkeeps_surveils_once(self, builder):
        game, oid = suspended(builder)
        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 5
        assert len(surveils(game)) == 1
        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].counter(TIME_COUNTER) == 4
        assert len(surveils(game)) == 2


class TestTheLastTick:
    def test_the_last_counter_surveils_too_and_before_the_watcher_resolves(self, builder):
        game, oid = suspended(builder, counters=1)
        past_the_next_upkeep_of(game, 0)
        obj = game.state.objects[oid]
        assert obj.zone is Zone.BATTLEFIELD, "the free cast resolved"
        (surveil,) = surveils(game)
        arrival = next(
            e
            for e in game.state.events
            if e.type == EventType.ZONE_CHANGE
            and e.data.get("oid") == oid
            and e.data.get("to") == Zone.BATTLEFIELD.value
        )
        events = game.state.events
        assert events.index(surveil) < events.index(arrival), (
            "the trigger was stacked above the spell, so it resolved first"
        )

    def test_the_trigger_is_heard_from_exile_as_the_spell_is_cast(self, builder):
        """Queued off the removal while the card was still in exile; the cast
        that follows put the Watcher on the stack beneath it."""
        game, oid = suspended(builder, counters=1)
        suspend.tick(game.state, 0)
        assert game.state.objects[oid].zone is Zone.STACK
        assert queued(game, oid) == 1


class TestWhoAndHowMany:
    def test_your_removal_of_two_is_two_triggers(self, builder):
        game, oid = suspended(builder)
        assert remove_counters(game.state, oid, TIME_COUNTER, 2, by=0) == 2
        assert queued(game, oid) == 2

    def test_an_opponents_removal_is_not_you_removing(self, builder):
        game, oid = suspended(builder)
        assert remove_counters(game.state, oid, TIME_COUNTER, 1, by=1) == 1
        assert queued(game, oid) == 0

    def test_another_kind_is_not_a_time_counter(self, builder):
        game, oid = suspended(builder)
        game.state.objects[oid].add_counter("+1/+1", 1)
        remove_counters(game.state, oid, "+1/+1", 1, by=0)
        assert queued(game, oid) == 0

    def test_it_listens_only_from_exile(self, builder):
        game, oid = suspended(builder, counters=1)
        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        game.state.objects[oid].add_counter(TIME_COUNTER, 1)
        remove_counters(game.state, oid, TIME_COUNTER, 1, by=0)
        assert queued(game, oid) == 0


def _model(trigger: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_counter_removed_probe",
            "name": "Probe",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "mana_cost": "{1}",
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": trigger,
                    "effects": [{"op": "draw", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_counter_and_removed_by_load_on_counter_removed(self):
        card = compile_card(
            _model(
                {"event": "counter_removed", "source": "self", "counter": "time",
                 "removed_by": "you"}
            )
        )
        spec = card.abilities[0].trigger
        assert (spec.counter, spec.removed_by) == ("time", "you")

    @pytest.mark.parametrize("event", ["counter_placed", "last_counter_removed", "upkeep"])
    def test_removed_by_elsewhere_is_refused(self, event):
        trigger = {"event": event, "source": "self", "removed_by": "you"}
        if event == "last_counter_removed":
            trigger["counter"] = "time"
        with pytest.raises(DslError, match="removed_by"):
            compile_card(_model(trigger))


class TestThePrintedSuspendLineIsClaimed:
    """Gate 3: the card-level `suspend` field claims a permanent's suspend line,
    and only with the printed count and price."""

    LINE = (
        "Suspend 6—{1}{U} (Rather than cast this card from your hand, you may pay "
        "{1}{U} and exile it with six time counters on it. At the beginning of your "
        "upkeep, remove a time counter. When the last is removed, you may cast it "
        "without paying its mana cost. It has haste.)"
    )

    def residual(self, suspend):
        from commanderblitz.cards.authoring.verify import residual_text

        payload = {
            "id": "t_suspend_probe",
            "name": "Probe",
            "oracle_text": self.LINE,
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "mana_cost": "{5}{U}",
        }
        if suspend is not None:
            payload["suspend"] = suspend
        card = compile_card(CardModel.model_validate(payload))
        return residual_text(card, card.oracle_text)

    def test_the_printed_line_is_claimed(self):
        assert self.residual({"cost": "{1}{U}", "counters": 6}) == ""

    def test_a_card_without_the_field_leaves_it_residual(self):
        assert "Suspend 6" in self.residual(None)

    def test_a_different_count_cannot_claim_it(self):
        assert "Suspend 6" in self.residual({"cost": "{1}{U}", "counters": 5})

    def test_a_different_price_cannot_claim_it(self):
        assert "Suspend 6" in self.residual({"cost": "{U}", "counters": 6})
