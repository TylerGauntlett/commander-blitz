"""Exhaust -- an activated ability that may be activated once per object.

    "Exhaust — Pay six {E}: Put two +1/+1 counters on this creature. Then draw
    cards equal to the greatest power among creatures you control. (Activate
    each exhaust ability only once.)" -- Peema Trailblazer

Rule 702.177a: "Activate each exhaust ability only once." The limit is on the
*object*, not the turn. `once_each_turn` is the near miss and the wrong one: it
is cleared at cleanup, so Peema would draw a fistful every turn instead of once.
And the object is the unit, so a permanent that leaves and comes back is a new
object (400.7) whose exhaust ability has never been activated.

Counted on activation, not resolution: an exhaust ability that was countered
has still been activated. And an exhausted ability is simply absent from
`legal_actions`, which is all a human, a CPU and a policy ever see.

`t_exhaust_engine` carries an unlimited ability beside the exhaust one, so
"the second activation is not offered" cannot pass for an unrelated reason.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, pass_until, plus_one_counters, settle_completely

ENGINE = "t_exhaust_engine"
EXHAUST, UNLIMITED = 0, 1


def position(builder):
    """The engine on seat 0's battlefield, seat 0 holding priority in its main phase.

    The instant in hand is load bearing: with nothing to do, seat 0 would
    auto-pass and `legal_actions()` would be the opponent's list.
    """
    game = (
        builder(players=2)
        .battlefield(0, [ENGINE])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, ["t_plain_instant"])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    pending = game.pending()
    assert pending is not None and pending.player == 0, "seat 0 holds priority"
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == ENGINE)
    return game, oid


def activate(game, oid, index):
    game.apply(activations(game, oid, index)[0])
    settle_completely(game)


def to_my_main(game, turn):
    pass_until(
        game,
        lambda g: g.state.turn >= turn
        and g.state.step is Step.PRECOMBAT_MAIN
        and (d := g.pending()) is not None
        and d.player == 0,
    )


class TestOnlyOnce:
    def test_it_is_offered_before_it_is_used(self, builder):
        game, oid = position(builder)
        assert activations(game, oid, EXHAUST)

    def test_it_resolves(self, builder):
        game, oid = position(builder)
        activate(game, oid, EXHAUST)
        assert plus_one_counters(game, oid) == 1

    def test_the_second_activation_is_not_offered(self, builder):
        game, oid = position(builder)
        activate(game, oid, EXHAUST)
        assert not activations(game, oid, EXHAUST)

    def test_the_other_ability_is_untouched(self, builder):
        """The control: the limit is per ability, not per permanent."""
        game, oid = position(builder)
        activate(game, oid, EXHAUST)
        activate(game, oid, UNLIMITED)
        assert activations(game, oid, UNLIMITED), "the unlimited one stays offered"

    def test_it_is_spent_on_activation_not_resolution(self, builder):
        """Spent while still on the stack -- a countered activation was used."""
        game, oid = position(builder)
        game.apply(activations(game, oid, EXHAUST)[0])
        assert game.state.stack, "the ability is waiting to resolve"
        assert EXHAUST in game.state.objects[oid].exhausted


class TestNotATurnLimit:
    def test_it_stays_spent_on_later_turns(self, builder):
        """`once_each_turn` would come back at cleanup; exhaust never does."""
        game, oid = position(builder)
        activate(game, oid, EXHAUST)
        to_my_main(game, game.state.turn + 2)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert not activations(game, oid, EXHAUST)


class TestANewObject:
    def test_a_permanent_that_left_and_came_back_may_exhaust_again(self, builder):
        """400.7: the returned permanent is a new object."""
        game, oid = position(builder)
        activate(game, oid, EXHAUST)
        move_object(game.state, oid, Zone.EXILE)
        move_object(game.state, oid, Zone.BATTLEFIELD)
        assert not game.state.objects[oid].exhausted
        assert activations(game, oid, EXHAUST)

    def test_the_record_is_on_the_snapshot_only_once_used(self, builder):
        game, oid = position(builder)
        assert "exhausted" not in game.state.objects[oid].to_dict()
        activate(game, oid, EXHAUST)
        assert game.state.objects[oid].to_dict()["exhausted"] == [EXHAUST]


def _card(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_exhaust_probe",
            "name": "Exhaust Probe",
            "oracle_text": "",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "abilities": [ability],
        }
    )


class TestTheLoaderRefuses:
    def test_it_on_a_trigger(self):
        with pytest.raises(DslError, match="exhaust"):
            compile_card(
                _card(
                    {
                        "kind": "triggered",
                        "exhaust": True,
                        "trigger": {"event": "self_enters"},
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                )
            )

    def test_it_on_a_mana_ability(self):
        """The payment solver taps mana abilities itself and would never see it."""
        with pytest.raises(DslError, match="exhaust"):
            compile_card(
                _card(
                    {
                        "kind": "activated",
                        "cost": {"tap": True},
                        "is_mana_ability": True,
                        "exhaust": True,
                        "effects": [{"op": "add_mana", "mana": "{C}", "player": "you"}],
                    }
                )
            )

    def test_it_compiles_on_an_activated_ability(self):
        card = compile_card(
            _card(
                {
                    "kind": "activated",
                    "cost": {"mana": "{1}"},
                    "exhaust": True,
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            )
        )
        assert card.abilities[0].exhaust
