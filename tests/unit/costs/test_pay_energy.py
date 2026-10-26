"""Paying energy as a cost: "Pay {E}{E}: …" (107.14).

Energy is a counter on a player, and a cost that spends it is the other half of
the subsystem `add_energy` began. Nissa, Worldsoul Speaker's alternative cost
pays eight of them; the claims about the cost itself are pinned here, on an
activated ability, because that is the simplest place a cost is paid.

- **Payable only with enough.** A player with one fewer than the price is not
  offered the line at all (601.2h): offering it and failing the payment would
  show a price the player can never pay.
- **Paying takes exactly that many**, through `primitives.pay_energy`, which
  reports what is left -- the number the client draws.
- **The payment solver never spends energy on its own.** Aether Hub's shape --
  a tap and an energy for mana -- is not a tap-only source, so `mana_sources`
  leaves it out rather than draining their energy to pay a {1}.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.costs import can_pay, mana_sources
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import only_oid, settle

CELL = "t_energy_cell"
HUB = "t_energy_hub"


def with_energy(b, energy: int):
    """Give player 0 energy *before* the build advances.

    Set afterwards, the auto-pass has already rolled past a position in which
    player 0 had nothing to do.
    """
    b.state.players[0].energy = energy
    return b.build()


def cell_with(builder, energy: int):
    b = builder(players=2).battlefield(0, [CELL]).library(0, ["forest"] * 5).active(0)
    game = with_energy(b, energy)
    return game, only_oid(game, CELL)


def activations(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid]


class TestTheBoundary:
    def test_exactly_enough_is_payable(self, builder):
        game, oid = cell_with(builder, 2)
        assert activations(game, oid)

    def test_one_short_is_not_offered(self, builder):
        game, oid = cell_with(builder, 1)
        assert not activations(game, oid)

    def test_none_at_all_is_not_offered(self, builder):
        game, oid = cell_with(builder, 0)
        assert not activations(game, oid)

    def test_can_pay_reads_the_payer_not_the_table(self, builder):
        game, _ = cell_with(builder, 0)
        game.state.players[1].energy = 9
        assert not can_pay(game.state, 0, Cost(pay_energy=2), None)
        assert can_pay(game.state, 1, Cost(pay_energy=2), None)


class TestPaying:
    def test_it_takes_exactly_the_price(self, builder):
        game, oid = cell_with(builder, 5)
        hand = len(game.state.players[0].hand)
        game.apply(activations(game, oid)[0])
        assert game.state.players[0].energy == 3, "paid as it is activated, before it resolves"
        settle(game)
        assert len(game.state.players[0].hand) == hand + 1

    def test_the_event_says_what_is_left(self, builder):
        game, oid = cell_with(builder, 5)
        game.state.events.clear()
        game.apply(activations(game, oid)[0])
        (paid,) = [e for e in game.state.events if e.type is EventType.ENERGY_PAID]
        assert paid.player == 0
        assert paid.data["amount"] == 2
        assert paid.data["total"] == 3

    def test_the_cost_describes_itself_in_symbols(self):
        assert Cost(pay_energy=2).describe() == "Pay {E}{E}"


class TestTheSolver:
    def test_a_tap_and_energy_source_is_not_tapped_for_free(self, builder):
        game = with_energy(builder(players=2).battlefield(0, [HUB]).active(0), 3)
        hub = only_oid(game, HUB)
        assert hub not in [s.oid for s in mana_sources(game.state, 0)]


class TestTheLoader:
    def test_a_negative_payment_is_refused(self):
        model = CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Pay {E}: Draw a card.",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Pay {E}: Draw a card.",
                        "cost": {"pay_energy": -1},
                        "effects": [{"op": "draw", "amount": {"const": 1}}],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="pay_energy"):
            compile_card(model)
