"""Which *players* a creature attacked this turn -- Angel of Destiny's loss clause.

"At the beginning of your end step, if you have at least 15 life more than your
starting life total, **each player this creature attacked this turn** loses the
game." The question is about one creature and asks *whom*, and nothing in the
engine could answer it:

- `TurnLedger.creatures_attacked` is keyed by the attacking **seat** and holds
  oids, so it knows the Angel attacked and not at whom. At a pod, with the
  Angel at one opponent and a bear at another, "each opponent" would end the
  game for a player the Angel never touched.
- `state.combat.attackers` knew, and is `None` by the end step.

So `TurnLedger.players_attacked_by` (attacker oid -> seats), folded off the
per-creature `ATTACKS` event, and the player spec `{"attacked_by": "self"}`.

Two rules shape the record, and each has a test class:

- **506.2 / 508.1b** -- a creature attacking a planeswalker or a battle is
  attacking that permanent, not its controller. The event names the controller
  as `defender` either way (that seat blocks), so the ledger reads the new
  `attacked_permanent` payload key and records nothing for such an attack.
- **400.7** -- the oid survives a zone change and the object does not. An Angel
  flickered after combat is a new object that attacked nobody, so the record is
  dropped when the creature leaves the battlefield.

It wears off with the rest of the ledger at cleanup.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import select_players
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, find_action, only_oid, pass_until

ANGEL = "t_destiny_angel"  # 2/2; end step: each player it attacked loses
BEAR = "t_bear"  # {1}{G} 2/2
BOLT = "t_bolt"  # an instant, so priority stops in every step
WALKER = "t_walker"  # loyalty 4
SPEC = {"attacked_by": "self"}


def board(builder, *, players: int = 3, theirs: dict[int, list[str]] | None = None):
    b = (
        builder(players=players)
        .battlefield(0, ["mountain"] * 4 + [ANGEL, BEAR])
        .hand(0, [BOLT])
        .library(0, ["mountain"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid, cards in (theirs or {}).items():
        b.battlefield(pid, cards)
        b.library(pid, ["mountain"] * 10)
    for pid in range(1, players):
        if pid not in (theirs or {}):
            b.library(pid, ["mountain"] * 10)
    game = b.build()
    return game, only_oid(game, ANGEL, 0), only_oid(game, BEAR, 0)


def declare(game, attacks: dict[int, TargetRef]) -> None:
    """Declare each attacker at its target and lock the declaration in."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def until(game, predicate, limit: int = 300) -> None:
    """Answer every decision with its default until ``predicate`` holds."""
    for _ in range(limit):
        if predicate(game) or game.over:
            return
        decision = game.pending()
        assert decision is not None, "nothing left to pass with"
        game.apply(_default_answer(game, decision))
    raise AssertionError("did not reach the condition")


def attacked_by(game, oid: int) -> list[int]:
    return select_players(EffectContext(state=game.state, controller=0, source_oid=oid), SPEC)


class TestTheLedger:
    def test_it_records_whom_each_creature_attacked(self, builder):
        game, angel, bear = board(builder)
        declare(game, {angel: TargetRef.player(1), bear: TargetRef.player(2)})
        assert game.state.turn_ledger.players_attacked_by == {angel: {1}, bear: {2}}

    def test_it_survives_the_end_of_combat(self, builder):
        game, angel, _ = board(builder)
        declare(game, {angel: TargetRef.player(2)})
        until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert game.state.combat is None
        assert attacked_by(game, angel) == [2]

    def test_a_creature_that_did_not_attack_attacked_nobody(self, builder):
        game, angel, bear = board(builder)
        declare(game, {bear: TargetRef.player(1)})
        assert attacked_by(game, angel) == []


class TestAPermanentIsNotItsController:
    """506.2: attacking a planeswalker is not attacking the player."""

    def test_attacking_a_planeswalker_records_no_player(self, builder):
        game, angel, _ = board(builder, players=2, theirs={1: [WALKER]})
        walker = only_oid(game, WALKER, 1)
        declare(game, {angel: TargetRef.obj(walker)})
        assert game.state.combat.attackers[angel] == 1, "its controller still defends"
        assert attacked_by(game, angel) == []

    def test_the_player_beside_it_is_still_recorded(self, builder):
        game, angel, bear = board(builder, players=2, theirs={1: [WALKER]})
        walker = only_oid(game, WALKER, 1)
        declare(game, {angel: TargetRef.player(1), bear: TargetRef.obj(walker)})
        assert attacked_by(game, angel) == [1]
        assert attacked_by(game, bear) == []


class TestItWearsOff:
    def test_leaving_the_battlefield_forgets_it(self, builder):
        # 400.7: back from exile, it is a new object that attacked nobody.
        game, angel, _ = board(builder)
        declare(game, {angel: TargetRef.player(1)})
        move_object(game.state, angel, Zone.EXILE)
        move_object(game.state, angel, Zone.BATTLEFIELD)
        assert attacked_by(game, angel) == []

    def test_it_is_cleared_with_the_ledger(self, builder):
        game, angel, _ = board(builder)
        declare(game, {angel: TargetRef.player(1)})
        game.state.turn_ledger.clear()
        assert attacked_by(game, angel) == []


class TestTheCard:
    def test_only_the_player_it_attacked_loses(self, builder):
        game, angel, bear = board(builder)
        declare(game, {angel: TargetRef.player(1), bear: TargetRef.player(2)})
        until(game, lambda g: g.state.players[1].has_lost or g.state.turn > 1)
        assert game.state.players[1].has_lost
        assert not game.state.players[2].has_lost, "the bear's defender was not the Angel's"
        assert not game.state.players[0].has_lost

    def test_no_attack_no_loss(self, builder):
        game, _, bear = board(builder)
        declare(game, {bear: TargetRef.player(1)})
        until(game, lambda g: g.state.step is Step.CLEANUP or g.state.turn > 1)
        assert not any(p.has_lost for p in game.state.players)


class TestTheLoader:
    def probe(self, player) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{W}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "Probe.",
                        "trigger": {"event": "end_step", "controller": "you"},
                        "effects": [{"op": "lose_game", "player": player}],
                    }
                ],
            }
        )

    def test_self_loads(self):
        compile_card(self.probe(SPEC))

    @pytest.mark.parametrize("bad", [{"attacked_by": "subject"}, {**SPEC, "not": "you"}])
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(DslError, match="attacked_by"):
            compile_card(self.probe(bad))
