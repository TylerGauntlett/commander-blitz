"""Two condition leaves Wedding Ring cannot be written without.

"When this artifact enters, **if it was cast**, target opponent creates a token
that's a copy of it. / Whenever an opponent who controls an artifact named
Wedding Ring draws a card **during their turn**, you draw a card."

Both clauses are loop guards rather than flavour, and the engine had a near miss
for each that is wrong in ordinary play rather than at an edge.

**"If it was cast" (603.6e)** is about *this* arrival on the battlefield. The
tempting reduction is `{"any": [{"cast_during": …}]}` over every phase, which
compiles and is exactly `obj.cast_step is not None` -- a stamp `stack.push_spell`
writes once and nothing ever clears, so a Ring that was cast, died and was
reanimated still answers `True` and hands an opponent a second free copy.
`TestOnlyThisArrivalCounts` puts both questions to the same object after the
reanimation and pins them apart. The other near miss, `not_cause: "token"` on the
trigger, names one cause to refuse: it stops the Ring copying its own copy and
does nothing about a blink, a reanimation, or Show and Tell.

**"During their turn"** is the turn of the player the event was about.
`is_your_turn` compares `state.active_player` to `ctx.controller`, and
`triggers._matches` evaluates a trigger's intervening-if with
`controller=obj.controller` hardcoded, so it can only ever ask about the ability's
own controller. `{"is_your_turn": false}` reads "not your turn", which coincides
with the printed clause **only in a duel**. This engine plays pods, and at three
seats it is a strictly wider card: it fires when one opponent draws during a
*third* player's turn, which Wedding Ring does not do.
`TestTheThirdPlayersTurn` is that seat, and asserts the near miss gets it wrong
in the same position.

The witness for both is Wedding Ring; `is_active_player` is wanted by every
"during that player's turn" clause, of which it has two.
"""

from __future__ import annotations

import pytest

from automtg.engine import triggers
from automtg.engine.carddef import TriggerSpec
from automtg.engine.effects.conditions import evaluate_condition, validate_condition
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.events import EventType, GameEvent
from automtg.engine.primitives import create_token
from automtg.engine.zones import destroy, move_object
from tests.conftest import action_for_card, pass_until

CREATURE = "llanowar_elves"

#: The reduction the gap record proved compiles, and what it really asks.
#: `cast_during` over every phase collapses to "was this object ever cast",
#: which is not a question about the trip the permanent is currently on.
EVER_CAST = {
    "any": [
        {"cast_during": phase}
        for phase in ("beginning", "precombat_main", "combat", "postcombat_main", "ending")
    ]
}


def a_cast_permanent(builder, players: int = 2):
    """Cast one creature for real and let it resolve. Returns ``(game, oid)``.

    Cast rather than placed with `builder.battlefield`, because the whole
    question is how the permanent got there: the builder places objects without
    a spell, without a stack and without an enters event, which is precisely the
    "it was not cast" side of the clause.
    """
    game = (
        builder(players=players)
        .battlefield(0, ["forest"])
        .hand(0, [CREATURE])
        .build()
    )
    pass_until(
        game,
        lambda g: any(
            a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == CREATURE
            for a in g.legal_actions()
        ),
    )
    action = action_for_card(game, ActionKind.CAST, CREATURE)
    oid = action.source
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)
    assert game.state.objects[oid].zone is Zone.BATTLEFIELD
    return game, oid


def asks(game, oid: int, cond) -> bool:
    """Put a condition to one object the way a trigger's intervening-if does."""
    return evaluate_condition(
        game.state, cond, controller=game.state.objects[oid].controller, source=oid
    )


class TestWhatCountsAsCast:
    def test_a_resolved_spell_was_cast(self, builder):
        game, oid = a_cast_permanent(builder)
        assert asks(game, oid, {"was_cast": True}) is True
        assert asks(game, oid, {"was_cast": False}) is False

    def test_a_token_was_not(self, builder):
        """Wedding Ring's own copy is a token, and this is what stops the loop."""
        game, _ = a_cast_permanent(builder)
        token = create_token(game.state, CREATURE, 0)[0]
        assert asks(game, token, {"was_cast": True}) is False

    def test_a_permanent_put_onto_the_battlefield_was_not(self, builder):
        """Show and Tell, Kodama, a reanimation -- no spell, so no cast."""
        game, _ = a_cast_permanent(builder)
        dropped = _new_card_in_graveyard(game, CREATURE, 0)
        move_object(game.state, dropped, Zone.BATTLEFIELD, cause="put_onto_battlefield")
        assert asks(game, dropped, {"was_cast": True}) is False

    def test_a_permanent_placed_by_the_builder_was_not(self, builder):
        """A board read off a position was never cast, and must not claim to be."""
        game = builder(players=2).battlefield(0, [CREATURE]).build()
        assert asks(game, game.state.battlefield[0], {"was_cast": True}) is False


class TestOnlyThisArrivalCounts:
    """The claim the whole leaf exists for: a *second* arrival is not a cast."""

    def test_a_reanimated_permanent_did_not_arrive_by_being_cast(self, builder):
        game, oid = a_cast_permanent(builder)
        assert asks(game, oid, {"was_cast": True}) is True

        destroy(game.state, oid)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        move_object(game.state, oid, Zone.BATTLEFIELD, cause="put_onto_battlefield")

        assert asks(game, oid, {"was_cast": True}) is False, (
            "reanimation is not a cast -- a Wedding Ring that read otherwise "
            "would hand out a free copy every time it came back"
        )

    def test_the_cast_during_reduction_still_says_yes(self, builder):
        """The near miss, in the same position, answering the other way.

        This is not a test of `cast_during` -- it is the reason `was_cast` had
        to be its own key. The cast stamps deliberately outlive the spell so an
        enters trigger can read them, and nothing clears them on the way out.
        """
        game, oid = a_cast_permanent(builder)
        destroy(game.state, oid)
        move_object(game.state, oid, Zone.BATTLEFIELD, cause="put_onto_battlefield")

        assert game.state.objects[oid].cast_step is not None
        assert asks(game, oid, EVER_CAST) is True
        assert asks(game, oid, {"was_cast": True}) is False

    def test_casting_it_again_makes_it_true_again(self, builder):
        """The wearing-off runs both ways: the flag is stamped on every arrival."""
        game, oid = a_cast_permanent(builder)
        destroy(game.state, oid)
        move_object(game.state, oid, Zone.BATTLEFIELD, cause="put_onto_battlefield")
        assert asks(game, oid, {"was_cast": True}) is False

        # Back to the hand, and cast a second time.
        move_object(game.state, oid, Zone.HAND, cause="returned")
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.CAST and a.source == oid for a in g.legal_actions()
            ),
        )
        game.apply(action_for_card(game, ActionKind.CAST, CREATURE))
        pass_until(game, lambda g: not g.state.stack)
        assert asks(game, oid, {"was_cast": True}) is True


class TestTheEntersTriggerReadsIt:
    """`was_cast` where the printed clause lives: an intervening-if on 603.6e."""

    def test_the_trigger_matches_a_cast_arrival_and_not_a_returned_one(self, builder):
        game, oid = a_cast_permanent(builder)
        spec = TriggerSpec(
            event="self_enters", controller="you", source="self",
            condition={"was_cast": True},
        )
        assert triggers._matches(game.state, game.state.objects[oid], spec, _entered(game, oid))

        destroy(game.state, oid)
        move_object(game.state, oid, Zone.BATTLEFIELD, cause="put_onto_battlefield")
        assert not triggers._matches(
            game.state, game.state.objects[oid], spec, _entered(game, oid)
        )


class TestTheThirdPlayersTurn:
    """"During their turn" at a pod, where `{"is_your_turn": false}` is wider."""

    def drawing_opponent(self, builder):
        """P0 holds the trigger; P1 draws; the seats are three."""
        game = builder(players=3).battlefield(0, ["forest"]).build()
        return game, game.state.battlefield[0]

    def test_false_on_a_third_players_turn(self, builder):
        game, source = self.drawing_opponent(builder)
        game.state.active_idx = 2

        assert (
            _their_turn(game, source, event_player=1) is False
        ), "P1 drew during P2's turn, which is not P1's turn"

    def test_the_near_miss_gets_that_seat_wrong(self, builder):
        """`{"is_your_turn": false}` is the whole of the gap, and this is it."""
        game, source = self.drawing_opponent(builder)
        game.state.active_idx = 2

        assert (
            evaluate_condition(
                game.state, {"is_your_turn": False}, controller=0, source=source
            )
            is True
        ), "the near miss reads 'not my turn', which at three seats is two turns"

    def test_true_on_the_drawing_players_own_turn(self, builder):
        game, source = self.drawing_opponent(builder)
        game.state.active_idx = 1
        assert _their_turn(game, source, event_player=1) is True

    def test_false_on_the_trigger_controllers_turn(self, builder):
        """The boundary the near miss does get right, kept honest."""
        game, source = self.drawing_opponent(builder)
        game.state.active_idx = 0
        assert _their_turn(game, source, event_player=1) is False
        assert (
            evaluate_condition(
                game.state, {"is_your_turn": False}, controller=0, source=source
            )
            is False
        )

    def test_the_trigger_agrees_with_the_condition(self, builder):
        """Through `_matches`, which is where the hardcoded controller lives."""
        game, source = self.drawing_opponent(builder)
        spec = TriggerSpec(
            event="draw",
            controller="opponent",
            condition={"is_active_player": {"binding": "event_player"}},
        )
        obj = game.state.objects[source]

        game.state.active_idx = 1
        assert triggers._matches(game.state, obj, spec, _drew(game, 1))
        game.state.active_idx = 2
        assert not triggers._matches(game.state, obj, spec, _drew(game, 1))

    def test_a_named_spec_still_works(self, builder):
        """It takes the full player spec, the way `is_monarch` does."""
        game, source = self.drawing_opponent(builder)
        game.state.active_idx = 0
        assert evaluate_condition(
            game.state, {"is_active_player": "you"}, controller=0, source=source
        )
        assert not evaluate_condition(
            game.state, {"is_active_player": "each_opponent"}, controller=0, source=source
        )

    def test_a_binding_the_event_never_carried_is_false(self, builder):
        """An unanswerable "during their turn" must not fire."""
        game, source = self.drawing_opponent(builder)
        assert (
            evaluate_condition(
                game.state,
                {"is_active_player": {"binding": "nobody"}},
                controller=0,
                source=source,
                bindings={},
            )
            is False
        )


class TestTheLoaderRefusesTheSilentMistakes:
    def test_was_cast_must_be_a_boolean(self):
        with pytest.raises(DslError, match="true or false"):
            validate_condition({"was_cast": "false"}, "c")

    def test_is_active_player_needs_a_player_spec(self):
        with pytest.raises(DslError, match="needs a player spec"):
            validate_condition({"is_active_player": True}, "c")

    def test_is_active_player_refuses_the_tautology(self):
        with pytest.raises(DslError, match="always true"):
            validate_condition({"is_active_player": "active_player"}, "c")

    def test_is_active_player_refuses_a_misspelled_seat(self):
        with pytest.raises(DslError, match="must name one of"):
            validate_condition({"is_active_player": "each_oponent"}, "c")

    def test_both_keys_load(self):
        validate_condition({"was_cast": True}, "c")
        validate_condition({"is_active_player": {"binding": "event_player"}}, "c")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _their_turn(game, source: int, *, event_player: int) -> bool:
    """The condition as a trigger asks it, with the event's player bound."""
    return evaluate_condition(
        game.state,
        {"is_active_player": {"binding": "event_player"}},
        controller=game.state.objects[source].controller,
        source=source,
        bindings={"event_player": event_player},
    )


def _entered(game, oid: int) -> GameEvent:
    return GameEvent(
        type=EventType.ENTERS_BATTLEFIELD,
        turn=game.state.turn,
        step=game.state.step,
        player=game.state.objects[oid].controller,
        source=oid,
        data={"oid": oid},
    )


def _drew(game, pid: int) -> GameEvent:
    return GameEvent(
        type=EventType.DRAW,
        turn=game.state.turn,
        step=game.state.step,
        player=pid,
        data={},
    )


def _new_card_in_graveyard(game, card_id: str, pid: int) -> int:
    from automtg.engine.state import new_object

    obj = new_object(game.state, card_id, owner=pid, zone=Zone.GRAVEYARD)
    game.state.players[pid].graveyard.append(obj.oid)
    return obj.oid
