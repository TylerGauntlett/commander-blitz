""""When you lose control of this permanent, …" -- the `lose_control` trigger.

Khârn the Betrayer is the witness: "Sigil of Corruption -- When you lose
control of Khârn the Betrayer, draw two cards."

A control change is not a zone change, so none of the leave triggers hear it;
`primitives.change_control` fires `CONTROL_CHANGED` with ``from`` and ``to``,
and this name is what subscribes to it. The rules argument is all about **who
controls the trigger**:

* 603.10a lists "abilities that trigger when a player loses control of an
  object" among the look-back triggers: they trigger based on the game as it
  was *before* the event. Before the event the permanent, and so the ability,
  was the losing player's.
* 603.3a: a triggered ability is controlled by the player who controlled its
  source when it triggered. That is the player who lost control -- ``from`` --
  even though by the time the trigger is put on the stack the permanent is
  someone else's. So "you" in "draw two cards" is the player who lost it.

Without the override the trigger would belong to the permanent's new
controller, and the player who *took* Khârn would draw two -- the printed card
inverted. The same rule makes the thief draw when control goes home: they lose
control too.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import change_control
from tests.conftest import only_oid, pass_until

BEARER = "t_sigil_bearer"  # when you lose control of this, draw two cards
BEAR = "t_bear"


def board(builder, players: int = 2):
    b = builder(players=players).battlefield(0, [BEARER, BEAR])
    for pid in range(players):
        b = b.library(pid, ["forest"] * 20)
    game = b.step(Step.PRECOMBAT_MAIN).build(advance=False)
    game._advance()
    return game


def settle(game) -> None:
    game._advance()
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def hand(game, pid: int) -> int:
    return len(game.state.players[pid].hand)


class TestTheFormerControllerDraws:
    def test_the_player_who_lost_it_draws_two(self, builder):
        game = board(builder)
        before = (hand(game, 0), hand(game, 1))
        assert change_control(game.state, only_oid(game, BEARER, 0), 1)
        settle(game)
        assert (hand(game, 0), hand(game, 1)) == (before[0] + 2, before[1])

    def test_the_trigger_is_theirs_on_the_stack(self, builder):
        """603.3a: the controller is fixed as it triggers, not read later."""
        game = board(builder)
        bearer = only_oid(game, BEARER, 0)
        change_control(game.state, bearer, 1)
        (trigger,) = game.state.pending_triggers
        assert trigger.source_oid == bearer
        assert trigger.controller == 0
        assert game.state.objects[bearer].controller == 1

    def test_the_thief_draws_when_it_goes_home(self, builder):
        """The thief loses control on the way back, and it is their ability
        then: two control changes, one draw each."""
        game = board(builder)
        bearer = only_oid(game, BEARER, 0)
        change_control(game.state, bearer, 1)
        settle(game)
        before = (hand(game, 0), hand(game, 1))
        change_control(game.state, bearer, 0)
        settle(game)
        assert (hand(game, 0), hand(game, 1)) == (before[0], before[1] + 2)

    def test_at_a_pod_only_the_loser_draws(self, builder):
        game = board(builder, players=4)
        before = [hand(game, p) for p in range(4)]
        change_control(game.state, only_oid(game, BEARER, 0), 2)
        settle(game)
        assert [hand(game, p) for p in range(4)] == [before[0] + 2, *before[1:]]


class TestItIsScopedToItself:
    def test_another_permanent_changing_hands_fires_nothing(self, builder):
        game = board(builder)
        before = hand(game, 0)
        change_control(game.state, only_oid(game, BEAR, 0), 1)
        settle(game)
        assert not game.state.pending_triggers
        assert hand(game, 0) == before

    def test_a_no_op_change_is_no_loss(self, builder):
        """Gaining control of a permanent you control changes nothing."""
        game = board(builder)
        before = hand(game, 0)
        assert not change_control(game.state, only_oid(game, BEARER, 0), 0)
        settle(game)
        assert hand(game, 0) == before


def probe(trigger: dict) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "When you lose control of Probe, draw two cards.",
        "mana_cost": "{R}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "text": "When you lose control of Probe, draw two cards.",
                "trigger": trigger,
                "effects": [{"op": "draw", "amount": {"const": 2}}],
            }
        ],
    }


class TestTheLoader:
    def test_source_self_is_supplied(self):
        card = compile_card(CardModel.model_validate(probe({"event": "lose_control"})))
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger.source == "self"

    @pytest.mark.parametrize(
        "extra", [{"controller": "opponent"}, {"filter": {"types": ["Creature"]}}]
    )
    def test_a_controller_or_filter_is_refused(self, extra):
        with pytest.raises(DslError, match="lose_control"):
            compile_card(
                CardModel.model_validate(probe({"event": "lose_control", **extra}))
            )
