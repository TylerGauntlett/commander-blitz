"""Taking a creature off the other side of the board, and keeping it.

"Gain control of target creature." Captivating Vampire, and the reason the
Edgar Markov precon shipped with a substitution in that slot for as long as it
did. The object never moves zones, so almost all of this is about the three
rules that hang off `controller` and would each be silently wrong if the op
only assigned the field:

- **Rule 302.6.** The creature has not been under its new controller since
  their most recent turn began, so it is summoning sick for them. Without this
  a stolen creature attacks the turn it is stolen, which is Act of Treason for
  free on top of a permanent steal.
- **Rule 506.4.** Changing control removes a permanent from combat. Without
  this a creature stolen mid-combat goes on dealing damage on behalf of the
  player who no longer controls it.
- **Zone destinations follow the owner, not the controller.** A stolen creature
  that dies belongs in its owner's graveyard (rule 400.3); getting this wrong
  hands somebody a permanent card advantage every time they steal something.

This module is the **permanent** steal, which is what `gain_control` means with
no `duration` on it and what every card written before Act of Treason meant. The
until-end-of-turn form and its cleanup-step handback live in
`test_temporary_control.py`; what stays here is the guard that made it safe to
add one — a `duration` the engine does not recognise is still a load error, so a
misspelling cannot quietly become the permanent steal that is a strictly better
card than the one it is pretending to be.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.primitives import change_control
from automtg.engine.structs import TargetRef
from automtg.engine.zones import destroy
from tests.conftest import event_types, find_action, pass_until


def a_stolen_bear(builder, *, sick: bool = False):
    """A Test Bear owned by player 1, and the oid, before anything is taken."""
    game = (
        builder(players=2)
        .battlefield(0, ["t_anthem"])
        .battlefield(1, ["t_bear"], sick=sick)
        .build()
    )
    bear = next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == "t_bear"
    )
    return game, bear


class TestWhoControlsIt:
    def test_control_moves_and_ownership_does_not(self, builder):
        game, bear = a_stolen_bear(builder)
        assert change_control(game.state, bear, 0) is True

        obj = game.state.objects[bear]
        assert obj.controller == 0
        assert obj.owner == 1, "ownership is not what a control effect changes"
        assert obj.zone is Zone.BATTLEFIELD, "the object never moves"

    def test_taking_something_you_already_control_does_nothing(self, builder):
        """No event, and no re-dating: an idempotent steal must not re-sicken it."""
        game, bear = a_stolen_bear(builder)
        change_control(game.state, bear, 0)
        before = len(game.state.events)

        assert change_control(game.state, bear, 0) is False
        assert len(game.state.events) == before

    def test_it_is_announced(self, builder):
        """Nothing else in the log would say a creature swapped sides."""
        game, bear = a_stolen_bear(builder)
        before = len(game.state.events)
        change_control(game.state, bear, 0)

        new = list(game.state.events)[before:]
        assert EventType.CONTROL_CHANGED in event_types(new)
        event = next(e for e in new if e.type == EventType.CONTROL_CHANGED)
        assert event.data["from"] == 1
        assert event.data["to"] == 0

    def test_a_card_that_is_not_on_the_battlefield_cannot_be_taken(self, builder):
        game = builder(players=2).hand(1, ["t_bear"]).build()
        card = game.state.players[1].hand[0]
        assert change_control(game.state, card, 0) is False


class TestWhatChangesWithIt:
    def test_your_anthem_now_reaches_it(self, builder):
        """The point of the whole thing: a controller-filtered static re-reads."""
        game, bear = a_stolen_bear(builder)
        printed = chars(game.state, bear).power

        change_control(game.state, bear, 0)
        assert chars(game.state, bear).power == printed + 1

    def test_it_is_summoning_sick_for_its_new_controller(self, builder):
        """Rule 302.6 -- it has not been yours since your turn began."""
        game, bear = a_stolen_bear(builder)
        assert not game.state.objects[bear].summoning_sick(game.state.turn)

        change_control(game.state, bear, 0)
        assert game.state.objects[bear].summoning_sick(game.state.turn)

    def test_it_stops_being_sick_once_a_turn_has_passed(self, builder):
        game, bear = a_stolen_bear(builder)
        change_control(game.state, bear, 0)
        assert game.state.objects[bear].summoning_sick(game.state.turn + 1) is False

    def test_it_dies_to_its_owner(self, builder):
        """Rule 400.3 -- a stolen creature is not a card you get to keep."""
        game, bear = a_stolen_bear(builder)
        change_control(game.state, bear, 0)
        destroy(game.state, bear)

        assert bear in game.state.players[1].graveyard
        assert bear not in game.state.players[0].graveyard


class TestCombat:
    def test_stealing_an_attacker_removes_it_from_combat(self, builder):
        """Rule 506.4. The attack does not survive the creature changing sides.

        Player 0 is the one attacking here, because only the active player has
        attackers to steal -- the direction is the opposite of the rest of this
        file and the rule is the same either way.
        """
        game = builder(players=2).battlefield(0, ["t_bear"]).build()
        bear = game.state.battlefield[0]
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=bear, targets=(TargetRef.player(1),)
            )
        )
        assert game.state.combat.attacking(bear)

        change_control(game.state, bear, 1)
        assert not game.state.combat.attacking(bear)


class TestTheLoaderRefuses:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_thief",
                "name": "Test Thief",
                "mana_cost": "{2}{R}",
                "types": ["Sorcery"],
                "oracle_text": "Gain control of target creature.",
                "targets": [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ],
                "spell_effects": [effect],
            }
        )

    def test_it_takes_the_ordinary_form(self):
        compile_card(self._card({"op": "gain_control", "objects": {"target": "t1"}}))

    def test_gaining_control_of_nothing_is_not_a_card(self):
        with pytest.raises(DslError, match="nothing to take"):
            compile_card(self._card({"op": "gain_control"}))

    def test_an_unknown_duration_is_refused_rather_than_ignored(self):
        """Two spellings are implemented and everything else is a load error.
        A `duration` the engine does not read would be understood as "until end
        of turn" by whoever wrote it and silently keep the creature, which is a
        strictly better card than the one it is pretending to be."""
        with pytest.raises(DslError, match="unknown gain_control duration"):
            compile_card(
                self._card(
                    {
                        "op": "gain_control",
                        "objects": {"target": "t1"},
                        "duration": "end_of_turn",
                    }
                )
            )

    def test_no_duration_still_means_permanent(self):
        """The default did not move, so no shipped card did either."""
        card = compile_card(self._card({"op": "gain_control", "objects": {"target": "t1"}}))
        assert "duration" not in card.spell_effects[0]
