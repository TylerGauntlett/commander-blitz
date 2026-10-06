"""Poisonous (702.70): poison counters, and losing to them.

The census had this as "poison counters are not a loss condition the engine
checks", which is exactly right and is the whole of the work. A poison counter
that never kills anybody is a number on a player sheet, and a card that gave
them out would look implemented while doing nothing at all.

Three deliberate choices:

**Poison is a counter on the player, not a second life total.** It has its own
field and its own `LossReason`, because a player eliminated at 40 life did not
run out of life — a log that said `life` would be lying about how the game
ended, and the frontend prints that reason to the loser.

**Ten is the threshold** (704.5c), checked in the same state-based pass as life
and commander damage, so it applies continuously rather than at some convenient
moment.

**There is no `remove_poison`.** Nothing in the pool removes poison, and adding
the op speculatively would be a vocabulary item with no card behind it — the
thing this repo's load-time checks exist to keep out.

Infect is *not* here. It needs damage to be replaced — to players as poison, to
creatures as -1/-1 counters — and the replacement whitelist is a deliberate
four-entry list with an ADR behind it. The census still says so.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, DecisionKind, LossReason, Step
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.sba import POISON_THRESHOLD
from automtg.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, only_oid, pass_until

POISONOUS = "t_poisonous"  # 2/2; combat damage to a player gives 2 poison


def give_poison(game, pid: int, amount: int) -> None:
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, [{"op": "add_poison", "player": pid, "amount": {"const": amount}}])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def swing(game, oid: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    start = game.state.turn
    for _ in range(60):
        if game.over:
            return
        if game.state.turn != start or int(game.state.step) > int(Step.COMBAT_DAMAGE):
            break
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    for _ in range(15):
        if not game.state.stack and not game.state.pending_triggers:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))


class TestPoisonous:
    def test_connecting_gives_poison(self, builder):
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        swing(game, only_oid(game, POISONOUS, 0))
        assert game.state.players[1].poison == 2

    def test_it_goes_to_the_player_who_was_hit(self, builder):
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        swing(game, only_oid(game, POISONOUS, 0))
        assert game.state.players[0].poison == 0

    def test_the_damage_still_happens(self, builder):
        """Poisonous adds counters, it does not replace the damage."""
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        swing(game, only_oid(game, POISONOUS, 0))
        assert game.state.players[1].life == 38

    def test_not_connecting_gives_none(self, builder):
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.players[1].poison == 0


class TestTheLossCondition:
    def test_ten_poison_loses(self, builder):
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        give_poison(game, 1, POISON_THRESHOLD)
        sba.run(game.state)
        assert game.state.players[1].has_lost

    def test_nine_does_not(self, builder):
        """The boundary. Ten, not more than ten."""
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        give_poison(game, 1, POISON_THRESHOLD - 1)
        sba.run(game.state)
        assert not game.state.players[1].has_lost

    def test_it_kills_at_full_life(self, builder):
        """The whole point of poison being its own track."""
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        assert game.state.players[1].life == 40
        give_poison(game, 1, POISON_THRESHOLD)
        sba.run(game.state)
        assert game.state.players[1].has_lost
        assert game.state.players[1].life == 40, "not a life total in disguise"

    def test_the_reason_is_poison(self, builder):
        """A player eliminated at 40 life did not run out of life, and the
        frontend prints this reason to them."""
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        give_poison(game, 1, POISON_THRESHOLD)
        sba.run(game.state)
        assert game.state.players[1].loss_reason is LossReason.POISON


class TestTheOp:
    def test_it_emits_its_own_event(self, builder):
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        give_poison(game, 1, 3)
        (fired,) = [e for e in game.state.events if e.type == EventType.POISON_ADDED]
        assert fired.player == 1
        assert fired.data["amount"] == 3
        assert fired.data["total"] == 3

    def test_poison_accumulates(self, builder):
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        give_poison(game, 1, 3)
        give_poison(game, 1, 4)
        assert game.state.players[1].poison == 7

    def test_zero_does_nothing(self, builder):
        game = builder(players=2).battlefield(0, [POISONOUS]).build()
        give_poison(game, 1, 0)
        assert game.state.players[1].poison == 0
        assert not [e for e in game.state.events if e.type == EventType.POISON_ADDED]


class TestTheLoaderGuardsIt:
    def test_a_malformed_amount_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "x",
                        "mana_cost": "{G}",
                        "types": ["Sorcery"],
                        "spell_effects": [
                            {"op": "add_poison", "amount": {"nonsense": 1}}
                        ],
                    }
                )
            )

    def test_the_poisonous_card_compiles(self, registry):
        card = registry.get(POISONOUS)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger.event == "deals_combat_damage_to_player"
        assert [e["op"] for e in ability.effects] == ["add_poison"]
