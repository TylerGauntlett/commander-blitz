"""Putting counters on the source as a cost: "Put a page counter on this artifact: …"

Mazemind Tome, Devoted Druid, Bloodletter Quill, Wall of Roots. Rule 601.2h
(through 602.2b): costs are paid as the ability is activated, so the counter is
on the permanent before anyone can respond. Writing it as an `add_counters`
effect moves it to resolution, and the gap is observable -- a Tome sitting at
three counters could be activated in response to itself and both activations
would see three, which is how a fourth-counter state trigger gets dodged.

- **Paid on activation.** The counter is there while the ability is still on
  the stack.
- **It is a placement like any other** (122.6): `counter_placed` fires, with the
  payer as `put_by`, so "whenever a counter is put on this" hears a cost.
- **It is a cost, not an effect** (118.1): a "counters would be put" replacement
  applies and Doubling Season's "if an effect would put" does not -- the same
  split a planeswalker's +1 already makes.
- **Payable at any count.** Nothing limits it but the source being on the
  battlefield: Devoted Druid at 0/1 can still pay, and dies to the -1/-1 after.
- **Never paid by the mana solver.** Wall of Roots' shape is a mana ability
  whose whole price is a counter; a solver that treated it as tap-only would
  take the mana without ever putting the counter on.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.costs import can_pay, mana_sources
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.objects import MINUS_ONE
from tests.conftest import activations, oids_of, only_oid, settle

TOME = "t_pcc_tome"
LEDGER = "t_pcc_ledger"
DRUID = "t_pcc_druid"
ROOTS = "t_pcc_roots"


def board(builder, *cards: str, lands: int = 0):
    """Player 0 with ``cards`` and ``lands`` Forests, a land in hand to stop on."""
    game = (
        builder(players=2)
        .battlefield(0, [*cards, *(["forest"] * lands)])
        .hand(0, ["forest"])
        .library(0, ["forest"] * 10)
        .active(0)
        .build()
    )
    return game


class TestPaidOnActivation:
    def test_the_counter_is_on_before_the_ability_resolves(self, builder):
        game = board(builder, TOME)
        tome = only_oid(game, TOME)
        hand = len(game.state.players[0].hand)
        game.state.events.clear()
        game.apply(activations(game, tome)[0])
        settle(game)
        kinds = [e.type for e in game.state.events]
        assert kinds.index(EventType.COUNTER_PLACED) < kinds.index(EventType.ABILITY_RESOLVED)
        assert len(game.state.players[0].hand) == hand + 1
        assert game.state.objects[tome].counter("page") == 1, "the effect adds none"

    def test_amount_is_the_number_put_on(self, builder):
        game = board(builder, LEDGER, lands=1)
        ledger = only_oid(game, LEDGER)
        game.apply(activations(game, ledger, 0)[0])
        assert game.state.objects[ledger].counter("page") == 2


class TestItIsAPlacement:
    def test_counter_placed_fires_once_for_the_batch(self, builder):
        game = board(builder, LEDGER, lands=1)
        ledger = only_oid(game, LEDGER)
        game.state.events.clear()
        game.apply(activations(game, ledger, 0)[0])
        placed = [e for e in game.state.events if e.type == EventType.COUNTER_PLACED]
        assert len(placed) == 1
        assert placed[0].data["counter"] == "page"
        assert placed[0].data["amount"] == 2
        assert placed[0].data["put_by"] == 0

    def test_a_counter_placed_trigger_hears_the_cost(self, builder):
        game = board(builder, LEDGER, lands=1)
        ledger = only_oid(game, LEDGER)
        life = game.state.players[0].life
        game.apply(activations(game, ledger, 0)[0])
        settle(game)
        assert game.state.players[0].life == life + 1


class TestACostIsNotAnEffect:
    def test_doubling_season_effects_only_leaves_it_at_one(self, builder):
        game = board(builder, TOME, "t_ceo_season")
        tome = only_oid(game, TOME)
        game.apply(activations(game, tome)[0])
        assert game.state.objects[tome].counter("page") == 1

    def test_a_would_be_put_replacement_still_applies(self, builder):
        game = board(builder, TOME, "t_rc_season")
        tome = only_oid(game, TOME)
        game.apply(activations(game, tome)[0])
        assert game.state.objects[tome].counter("page") == 2


class TestPayableAtAnyCount:
    def test_the_druid_can_pay_its_last_toughness_and_dies(self, builder):
        game = board(builder, DRUID)
        druid = only_oid(game, DRUID)
        game.state.objects[druid].add_counter(MINUS_ONE, 1)
        game.state.objects[druid].tapped = True
        assert activations(game, druid)
        game.apply(activations(game, druid)[0])
        settle(game)
        assert not oids_of(game, DRUID), "0/0 after the cost; the state-based action kills it"

    def test_a_source_off_the_battlefield_cannot_pay(self, builder):
        game = board(builder, TOME)
        cost = Cost(put_counters={"counter": "page", "amount": 1})
        land_in_hand = game.state.players[0].hand[0]
        assert not can_pay(game.state, 0, cost, land_in_hand)
        assert can_pay(game.state, 0, cost, only_oid(game, TOME))


class TestTheSolver:
    def test_a_counter_priced_mana_ability_is_not_a_free_source(self, builder):
        game = board(builder, ROOTS)
        roots = only_oid(game, ROOTS)
        assert roots not in [s.oid for s in mana_sources(game.state, 0)]
        assert game.state.objects[roots].counter("charge") == 0


def probe(cost: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "Probe.",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "Probe.",
                    "cost": cost,
                    "effects": [{"op": "draw", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestTheLoader:
    @pytest.mark.parametrize(
        ("spec", "match"),
        [
            ({"amount": 1}, "'counter'"),
            ({"counter": "page"}, "'amount'"),
            ({"counter": "page", "amount": 0}, "'amount'"),
            ({"counter": "page", "amount": True}, "'amount'"),
            ({"counter": "page", "amount": 1, "objects": {"target": "t1"}}, "'counter' and 'amount' only"),
            ({"counter": "loyalty", "amount": 1}, "'loyalty' cost"),
        ],
    )
    def test_refusals(self, spec, match):
        with pytest.raises(DslError, match=match):
            compile_card(probe({"put_counters": spec}))

    def test_the_tome_compiles(self):
        card = compile_card(probe({"tap": True, "put_counters": {"counter": "page", "amount": 1}}))
        cost = card.abilities[0].cost
        assert cost.put_counters == {"counter": "page", "amount": 1}
        assert not cost.is_tap_only()
        assert "page" in cost.describe()
