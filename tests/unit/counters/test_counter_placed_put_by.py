"""A ``counter_placed`` trigger keyed on who put the counters.

    "Whenever **you** put one or more +1/+1 counters on this creature, draw a
    card. This ability triggers only once each turn."  -- Exemplar of Light

Rule 122.6a makes the putter a player of its own: the controller of the spell
or ability putting the counters, or, for a cost, an arrival or a Saga tick, the
permanent's controller. `primitives.add_counters` already worked that player out
(`_putter`) for Innkeeper's Talent's ``put_by`` replacement, and then dropped it:
COUNTER_PLACED carried only ``player``, the *recipient's* controller. So the
trigger's ``controller`` clause read "a +1/+1 counter was put on your creature",
and an opponent's Graft on my Exemplar drew me a card -- a strictly better card
than the printed one.

Now the event carries ``put_by`` and the trigger takes ``put_by: "you"``, the
same key and the same one value the static has. Without it the line is
unwritable exactly; with it:

- my placement on it fires, an opponent's does not, whichever way the putter is
  arrived at (an explicit ``by``, or the placing source's controller);
- "one or more" is one trigger per placement, not per counter -- `add_counters`
  fires one event per batch, pinned here for three at once;
- an opponent's placement does not spend the once-each-turn cap, because the
  match fails before the ability ever queues;
- the clause is refused on any event but ``counter_placed``, the only one that
  records a putter -- accepted elsewhere it would never fire.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import add_counters
from tests.conftest import action_for_card, only_oid, pass_until

WATCHER = "t_cpp_watcher"  # the draw line, uncapped
EXEMPLAR = "t_cpp_exemplar"  # the draw line, once each turn
GRAFT = "t_pb_graft"  # sorcery: a +1/+1 counter on target creature
BEAR = "t_rc_bear"


def position(builder, card_id: str = WATCHER, theirs=(), hand=()):
    """``(game, oid)`` for the watcher under player 0, at a main phase."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + [card_id])
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, card_id, 0)


def queued(game) -> int:
    return len(game.state.pending_triggers)


class TestKeyedOnThePutter:
    def test_my_counter_fires_it(self, builder):
        game, oid = position(builder)
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        assert queued(game) == 1

    def test_an_opponents_counter_does_not(self, builder):
        """The near miss: still a +1/+1 counter, still on my creature, but they
        put it. `controller: "you"` alone passes this."""
        game, oid = position(builder)
        add_counters(game.state, oid, "+1/+1", 1, by=1)
        assert queued(game) == 0

    def test_the_putter_is_the_placing_sources_controller(self, builder):
        """No explicit ``by``: their permanent's ability is them putting it,
        mine is me."""
        game, oid = position(builder, theirs=[BEAR])
        theirs = only_oid(game, BEAR, 1)
        add_counters(game.state, oid, "+1/+1", 1, source=theirs)
        assert queued(game) == 0
        add_counters(game.state, oid, "+1/+1", 1, source=oid)
        assert queued(game) == 1

    def test_the_event_carries_both_players(self, builder):
        """``player`` is the recipient's controller and ``put_by`` the putter --
        two answers to two questions."""
        game, oid = position(builder)
        mark = len(game.state.events)
        add_counters(game.state, oid, "+1/+1", 1, by=1)
        placed = [e for e in game.state.events[mark:] if e.type == EventType.COUNTER_PLACED]
        assert [(e.player, e.data["put_by"]) for e in placed] == [(0, 1)]

    def test_my_spell_on_it_draws_a_card(self, builder):
        """End to end: the `add_counters` op's source is the spell, whose
        controller is me."""
        game, oid = position(builder, hand=[GRAFT])
        hand = len(game.state.players[0].hand)
        game.apply(action_for_card(game, ActionKind.CAST, GRAFT))
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.objects[oid].counter("+1/+1") == 1
        # Graft left the hand (-1) and the trigger drew one (+1).
        assert len(game.state.players[0].hand) == hand


class TestOneOrMore:
    def test_three_at_once_fire_once(self, builder):
        game, oid = position(builder)
        add_counters(game.state, oid, "+1/+1", 3, by=0)
        assert queued(game) == 1

    def test_another_kind_leaves_it_silent(self, builder):
        game, oid = position(builder)
        add_counters(game.state, oid, "charge", 1, by=0)
        assert queued(game) == 0


class TestOnceEachTurn:
    def test_the_second_placement_this_turn_does_not_fire(self, builder):
        game, oid = position(builder, EXEMPLAR)
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        assert queued(game) == 1

    def test_an_opponents_placement_does_not_spend_it(self, builder):
        """The match fails before the ability queues, so the cap is untouched
        and my own placement afterwards still draws."""
        game, oid = position(builder, EXEMPLAR)
        add_counters(game.state, oid, "+1/+1", 1, by=1)
        assert queued(game) == 0
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        assert queued(game) == 1

    def test_it_comes_back_next_turn(self, builder):
        game, oid = position(builder, EXEMPLAR)
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        game.state.pending_triggers.clear()
        game.state.triggers_this_turn.clear()  # what the untap step does
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        assert queued(game) == 1


class TestTheLoader:
    def _card(self, **trigger):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Whenever you put…",
                "mana_cost": "{W}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "Whenever you put…",
                        "trigger": trigger,
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ],
            }
        )

    def test_it_loads_on_counter_placed(self):
        compiled = compile_card(
            self._card(event="counter_placed", source="self", put_by="you")
        )
        assert compiled.abilities[0].trigger.put_by == "you"

    def test_it_is_refused_on_another_event(self):
        with pytest.raises(DslError, match="put_by"):
            compile_card(self._card(event="self_enters", put_by="you"))

    def test_only_you_is_a_value(self):
        with pytest.raises(ValueError):
            self._card(event="counter_placed", source="self", put_by="opponent")
