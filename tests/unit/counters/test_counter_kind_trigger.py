"""Naming the counter a ``counter_placed`` trigger cares about.

    Fathom Mage — "Whenever a +1/+1 counter is put on this creature, you may
    draw a card."

`primitives.add_counters` has always put the kind on the event, and nothing
read it. So the only trigger the DSL could write was the unfiltered one, which
fires on *every* kind — and the shipped pool already places `charge` counters
and `slumber` counters. A Fathom Mage written that way draws off a Slumbering
Isle waking up, which is not the card.

That is the whole rule here: the printed line names a counter, so the trigger
must too, and a kind it does not name must leave it silent.

The other half is that the filter must not be silently accepted where it can
never apply. `not_cause` next door already sets that precedent — a guard that
looks like a guard and never fires is worse than no guard, so `counter` on any
event but `counter_placed` is a load error.

One event per placement is deliberate and already correct: `add_counters` fires
once for the whole batch with `amount` on the event, so "a +1/+1 counter" and
Sharktocrab's "one or more +1/+1 counters" are the same single trigger.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters
from tests.conftest import only_oid

#: The same 1/1 draw trigger twice: `t_counter_watcher` names `+1/+1`,
#: `t_any_counter_watcher` names nothing. The pair is the test.
FILTERED = "t_counter_watcher"
UNFILTERED = "t_any_counter_watcher"


def watcher(counter: str | None) -> dict:
    """The filtered card as raw JSON, for the load-time guards below."""
    trigger: dict = {"event": "counter_placed", "source": "self"}
    if counter is not None:
        trigger["counter"] = counter
    return {
        "id": "t_counter_watcher",
        "name": "Test Counter Watcher",
        "oracle_text": "Whenever a +1/+1 counter is put on this creature, draw a card.",
        "mana_cost": "{1}{U}",
        "types": ["Creature"],
        "subtypes": ["Wizard"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever a +1/+1 counter is put on this creature, draw a card.",
                "trigger": trigger,
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        ],
    }


def position(builder, card_id: str):
    """``(game, oid)`` for the watcher, on a board that can pay for anything."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + ["island"] * 3 + [card_id])
        .library(0, ["forest"] * 20)
        .build()
    )
    return game, only_oid(game, card_id)


def queued(game) -> int:
    return len(game.state.pending_triggers)


class TestItFiresOnlyOnTheKindItNames:
    def test_the_named_counter_fires_it(self, builder):
        game, oid = position(builder, FILTERED)
        add_counters(game.state, oid, "+1/+1", 1)
        assert queued(game) == 1

    def test_another_kind_leaves_it_silent(self, builder):
        """`charge` and `slumber` are not hypothetical -- `data/cards/` places
        both today, so the unfiltered trigger is observably wrong in the
        shipped pool rather than only in principle."""
        game, oid = position(builder, FILTERED)
        add_counters(game.state, oid, "charge", 1)
        assert queued(game) == 0
        add_counters(game.state, oid, "slumber", 1)
        assert queued(game) == 0
        add_counters(game.state, oid, "-1/-1", 1)
        assert queued(game) == 0

    def test_unfiltered_still_fires_on_everything(self, builder):
        """The old behaviour, kept and pinned: omitting `counter` is a real
        choice ("whenever a counter is put on"), not a mistake."""
        game, oid = position(builder, UNFILTERED)
        add_counters(game.state, oid, "charge", 1)
        assert queued(game) == 1


class TestTheBatchIsOneTrigger:
    def test_three_counters_at_once_fire_once(self, builder):
        """"a +1/+1 counter" is singular-or-more. `add_counters` fires one
        event for the batch with `amount` on it, which is the correct Magic
        behaviour and is also what Sharktocrab's "one or more" needs."""
        game, oid = position(builder, FILTERED)
        add_counters(game.state, oid, "+1/+1", 3)
        assert queued(game) == 1
        assert game.state.pending_triggers[0].bindings["amount"] == 3

    def test_the_kind_reaches_the_effects(self, builder):
        """Copied into bindings beside `amount`, so an effect can read what
        fired it rather than assuming."""
        game, oid = position(builder, FILTERED)
        add_counters(game.state, oid, "+1/+1", 1)
        assert game.state.pending_triggers[0].bindings["counter"] == "+1/+1"


class TestItIsRefusedWhereItCannotApply:
    def test_on_another_event_it_is_a_load_error(self):
        """Only `counter_placed` carries a counter kind. Accepted anywhere else
        it would look like a filter and never apply -- the same defect this
        whole change exists to remove."""
        card = watcher("+1/+1")
        card["abilities"][0]["trigger"]["event"] = "self_enters"
        card["abilities"][0]["trigger"].pop("source", None)
        with pytest.raises(DslError, match="only means anything on a counter_placed"):
            compile_card(CardModel.model_validate(card))

    def test_the_filtered_trigger_itself_loads(self):
        compile_card(CardModel.model_validate(watcher("+1/+1")))
