""""Whenever you lose life for the first time each turn" -- `nth` on `life_lost`.

    Intermediate Chirography, level 2 -- "Whenever you lose life for the first
    time each turn, put a +1/+1 counter on target creature you control."

The ordinal is the life-gain one turned over: `LIFE_LOST` carries ``nth``,
folded off `TurnLedger.life_losses` (a count of loss *events*, not of life) in
the same ledger pass that stamps a gain's. Every way of losing life counts,
because they are all one event: damage to a player causes that much life loss
(119.3, 120.3), and paying life is losing it (119.4). A loss of 0 is no loss --
`lose_life` and `damage_player` fire nothing for it -- so it spends no ordinal,
and neither does infect damage, which costs no life at all (120.3b).

The ordinal is per losing player, so "each opponent loses life for the first
time" has a first loss for every opponent.

The near miss fails a test below: `max_per_turn: 1` is counted per permanent
from when the ability appeared, so a Class reaching level 2 after its
controller's first loss would trigger on the second.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_player, lose_life
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until, settle

WATCHER = "t_fll_watcher"
SPY = "t_fll_spy"


def board(builder, mine=(WATCHER,), players: int = 2):
    return builder(players=players).battlefield(0, list(mine)).library(0, ["swamp"] * 20).build()


def drawn(game, *amounts: int, pid: int = 0) -> int:
    """Cards seat 0 draws while ``pid`` loses each of ``amounts`` in turn."""
    before = len(game.state.players[0].hand)
    for amount in amounts:
        lose_life(game.state, pid, amount)
        settle(game)
    return len(game.state.players[0].hand) - before


def hand_size(game) -> int:
    return len(game.state.players[0].hand)


class TestTheFirstLossOnly:
    def test_the_first_loss_triggers_it(self, builder):
        game = board(builder)
        assert drawn(game, 3) == 1

    def test_later_losses_the_same_turn_do_not(self, builder):
        game = board(builder)
        assert drawn(game, 1, 1, 1) == 1

    def test_an_opponents_loss_does_not(self, builder):
        game = board(builder)
        assert drawn(game, 3, pid=1) == 0

    def test_it_resets_on_the_next_turn(self, builder):
        game = board(builder)
        assert drawn(game, 1) == 1
        pass_until(game, lambda g: g.state.active_player == 1)
        assert drawn(game, 1) == 1


class TestEveryLossIsALoss:
    def test_damage_is_a_loss(self, builder):
        """119.3: damage dealt to a player causes that much life loss."""
        game = board(builder, mine=(WATCHER, "grizzly_bears"))
        before = hand_size(game)
        damage_player(game.state, 0, 2, only_oid(game, "grizzly_bears"))
        settle(game)
        assert hand_size(game) - before == 1

    def test_damage_after_a_drain_is_the_second_loss(self, builder):
        game = board(builder, mine=(WATCHER, "grizzly_bears"))
        assert drawn(game, 1) == 1
        before = hand_size(game)
        damage_player(game.state, 0, 2, only_oid(game, "grizzly_bears"))
        settle(game)
        assert hand_size(game) == before

    def test_paying_life_is_a_loss(self, builder):
        """119.4: Adanto Vanguard's "Pay 4 life" loses 4 life."""
        game = board(builder, mine=(WATCHER, "adanto_vanguard"))
        vanguard = only_oid(game, "adanto_vanguard")
        before = hand_size(game)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == vanguard)
        )
        settle(game)
        assert game.state.players[0].life == 36
        assert hand_size(game) - before == 1


class TestANonLossSpendsNothing:
    def test_a_loss_of_zero_is_no_first_loss(self, builder):
        game = board(builder)
        assert drawn(game, 0) == 0
        assert drawn(game, 1) == 1

    def test_infect_damage_is_no_loss(self, builder):
        """120.3b: infect damage gives poison counters and costs no life."""
        game = board(builder, mine=(WATCHER, "t_infecter"))
        before = hand_size(game)
        damage_player(game.state, 0, 1, only_oid(game, "t_infecter"))
        settle(game)
        assert hand_size(game) == before
        assert drawn(game, 1) == 1


class TestEachOpponentHasAFirstLoss:
    def test_each_opponents_first_loss_fires_once(self, builder):
        game = board(builder, mine=(SPY,), players=3)
        assert drawn(game, 1, 1, pid=1) == 1
        assert drawn(game, 1, 1, pid=2) == 1

    def test_your_own_loss_does_not(self, builder):
        game = board(builder, mine=(SPY,), players=3)
        assert drawn(game, 1, pid=0) == 0


class TestTheFirstLossIsTheTurnsNotThePermanents:
    def test_a_watcher_arriving_after_the_first_loss_waits_for_next_turn(self, builder):
        """The case `max_per_turn: 1` gets wrong: the turn's first loss has gone."""
        game = builder(players=2).hand(0, [WATCHER]).library(0, ["swamp"] * 20).build()
        lose_life(game.state, 0, 2)
        settle(game)
        watcher = next(oid for oid in game.state.players[0].hand if game.state.objects[oid].def_id == WATCHER)
        move_object(game.state, watcher, Zone.BATTLEFIELD)
        settle(game)
        assert drawn(game, 2) == 0


class TestTheLoader:
    def _card(self, event: str) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {"kind": "triggered", "text": "probe", "trigger": {"event": event, "nth": 1},
                     "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}]}
                ],
            }
        )

    def test_nth_loads_on_life_lost(self):
        compile_card(self._card("life_lost"))

    def test_nth_is_still_refused_on_an_event_with_no_ordinal(self):
        with pytest.raises(DslError, match="nth"):
            compile_card(self._card("upkeep"))
