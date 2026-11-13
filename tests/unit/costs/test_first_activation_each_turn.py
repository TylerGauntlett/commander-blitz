"""A discount for the first activated ability of an artifact you activate each turn.

    "The first activated ability of an artifact you activate each turn costs
    {2} less to activate."             -- Tezzeret, Betrayer of Flesh

`ability_cost_reduction` with `first_during_your_turn` (Professor Hojo) counts
the activator's own turn only, and picks the activation out by its *targets*.
Tezzeret's line is counted on **every** turn and picks the activation out by
its **source**: `first_each_turn` with `affects: {"types": ["Artifact"]}`. The
earlier activations' sources are asked of `TurnLedger.ability_sources`, a
snapshot filed as each is paid, because a cost may have sacrificed its source.

**A mana ability counts** (605.1a; the card's rulings): tapping Sol Ring for
mana is the first activated ability of an artifact you activate, so it spends
the turn's discount even though {T} has no mana to reduce. The payment solver
files the taps it makes, so tapping Sol Ring to pay for a spell spends it too.
A mana ability with a mana cost -- Dimir Signet's {1} -- is activated by hand
and priced through `costs.pay`, so the {2} reaches it.

Without this the card either discounts every artifact activation (a stronger
card) or none past the first of your own turn (a weaker one), and it lets a
Signet or a Treasure leave the discount for the next ability.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import activation_source_traits
from commanderblitz.engine.costs import ability_mana, pay_mana
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import ManaCost
from tests.conftest import oids_of, only_oid, settle

TEZZ = "t_fae_tezzeret"  # the first activated ability of an artifact each turn costs {2} less
ENGINE = "t_fae_engine"  # artifact, {3}: draw a card
RUNE = "t_fae_rune"  # enchantment, {3}: draw a card -- the non-artifact near miss


def position(builder, *, mine=(TEZZ, ENGINE, ENGINE), active=0, hand=()):
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 8 + list(mine))
        .battlefield(1, ["island"])
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .active(active)
        .build()
    )
    return game


def price(game, oid: int, pid: int = 0, index: int = -1) -> int:
    """The generic half of what activating ``oid``'s ability costs ``pid`` now."""
    ability = game.state.card_of(game.state.objects[oid]).abilities[index]
    return ability_mana(game.state, pid, ability.cost, 0, oid, ability=ability).generic


def activation(game, oid: int, index: int | None = None):
    for action in game.legal_actions():
        if (
            action.kind is ActionKind.ACTIVATE
            and action.source == oid
            and (index is None or action.ability_index == index)
        ):
            return action
    return None


def activate(game, oid: int, index: int | None = None) -> None:
    action = activation(game, oid, index)
    assert action is not None, "the activation is not offered"
    game.apply(action)
    settle(game)


class TestTheFirstArtifactActivation:
    def test_it_costs_two_less(self, builder):
        game = position(builder)
        assert price(game, oids_of(game, ENGINE, 0)[0]) == 1

    def test_the_second_costs_full(self, builder):
        game = position(builder)
        first, second = oids_of(game, ENGINE, 0)
        activate(game, first)
        assert price(game, second) == 3
        assert price(game, first) == 3

    def test_it_is_charged_at_the_discount(self, builder):
        game = position(builder)
        activate(game, oids_of(game, ENGINE, 0)[0])
        tapped = [o for o in oids_of(game, "island", 0) if game.state.objects[o].tapped]
        assert len(tapped) == 1

    def test_a_non_artifact_is_not_discounted_and_does_not_spend_it(self, builder):
        game = position(builder, mine=(TEZZ, RUNE, ENGINE))
        rune = only_oid(game, RUNE, 0)
        assert price(game, rune) == 3
        activate(game, rune)
        assert price(game, only_oid(game, ENGINE, 0)) == 1


class TestEachTurn:
    def test_it_applies_on_an_opponents_turn(self, builder):
        """"Each turn", not "during your turn" -- Hojo's boundary is not this one."""
        game = position(builder, active=1)
        assert price(game, oids_of(game, ENGINE, 0)[0]) == 1

    def test_it_is_fresh_the_next_turn(self, builder):
        game = position(builder)
        first, second = oids_of(game, ENGINE, 0)
        activate(game, first)
        game.state.turn_ledger.clear()
        assert price(game, second) == 1

    def test_an_activation_before_the_discount_arrived_still_counts(self, builder):
        """"The first" describes the activation, not the static (Esper Sentinel's reading)."""
        game = position(builder, mine=(ENGINE, ENGINE), hand=[TEZZ])
        first, second = oids_of(game, ENGINE, 0)
        assert price(game, first) == 3
        activate(game, first)
        tezz = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == TEZZ)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == tezz)
        )
        settle(game)
        assert game.state.objects[tezz].on_battlefield
        assert price(game, second) == 3

    def test_only_your_own_activations_count(self, builder):
        game = position(builder)
        engine = oids_of(game, ENGINE, 0)[0]
        # Seat 1 activated an artifact's ability this turn; seat 0 did not.
        game.state.turn_ledger.ability_sources[1] = [
            activation_source_traits(game.state, engine)
        ]
        assert price(game, engine) == 1


class TestManaAbilitiesCount:
    def test_tapping_sol_ring_by_the_solver_spends_it(self, builder):
        """Sol Ring pays for something; it was the first artifact ability activated.

        `costs.pay_mana` is the solver's whole path -- every spell and every
        ability pays its mana through it -- so it is asked directly, with the
        lands tapped so the plan must use the Ring.
        """
        game = position(builder, mine=(TEZZ, ENGINE, "sol_ring"))
        for o in oids_of(game, "island", 0):
            game.state.objects[o].tapped = True
        assert pay_mana(game.state, 0, ManaCost.parse("{1}").with_x(0))
        assert game.state.objects[only_oid(game, "sol_ring", 0)].tapped
        assert price(game, only_oid(game, ENGINE, 0)) == 3

    def test_tapping_a_land_does_not(self, builder):
        game = position(builder)
        assert pay_mana(game.state, 0, ManaCost.parse("{1}").with_x(0))
        assert price(game, oids_of(game, ENGINE, 0)[0]) == 1

    def test_a_signets_mana_cost_is_discounted(self, builder):
        game = position(builder, mine=(TEZZ, ENGINE, "dimir_signet"))
        signet = only_oid(game, "dimir_signet", 0)
        mana = next(
            i for i, a in enumerate(game.state.card_of(game.state.objects[signet]).abilities)
            if a.is_mana_ability
        )
        assert price(game, signet, index=mana) == 0

    def test_a_signet_with_no_mana_left_is_still_offered(self, builder):
        """{1} less {2} is nothing: the offer and the charge agree at zero."""
        # A land in hand keeps the priority with seat 0: a mana ability alone
        # is no reason to stop, and the engine would pass the turn away.
        game = position(builder, mine=(TEZZ, "dimir_signet"), hand=["forest"])
        for o in oids_of(game, "island", 0):
            game.state.objects[o].tapped = True
        signet = only_oid(game, "dimir_signet", 0)
        activate(game, signet)
        assert game.state.objects[signet].tapped
        assert game.state.players[0].mana_pool.total() == 2

    def test_the_signet_then_spends_it(self, builder):
        game = position(builder, mine=(TEZZ, ENGINE, "dimir_signet"))
        activate(game, only_oid(game, "dimir_signet", 0))
        assert price(game, only_oid(game, ENGINE, 0)) == 3


class TestASacrificedSourceStillCounts:
    def test_mind_stones_sacrifice_spends_it(self, builder):
        """The cost moves the source; the snapshot was taken before it."""
        game = position(builder, mine=(TEZZ, ENGINE, "mind_stone"))
        stone = only_oid(game, "mind_stone", 0)
        draw = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == stone
        )
        game.apply(draw)
        settle(game)
        assert not game.state.objects[stone].on_battlefield
        assert price(game, only_oid(game, ENGINE, 0)) == 3


class TestTheLoader:
    def _static(self, **over):
        static = {
            "kind": "static",
            "text": "The first activated ability of an artifact you activate each turn costs {2} less to activate.",
            "effect": "ability_cost_reduction",
            "affects_abilities": {"any": True},
            "activated_by": "you",
            "affects": {"types": ["Artifact"], "controller": "any"},
            "first_each_turn": True,
            "amount": {"const": 2},
        }
        static.update(over)
        return {k: v for k, v in static.items() if v is not None}

    def compile(self, static):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe_fae",
                    "name": "Probe First Each Turn",
                    "mana_cost": "{0}",
                    "types": ["Enchantment"],
                    "abilities": [static],
                }
            )
        )

    def test_tezzerets_line_loads(self):
        self.compile(self._static())

    def test_it_needs_affects(self):
        with pytest.raises(DslError, match="needs 'affects'"):
            self.compile(self._static(affects=None))

    def test_affects_reads_only_the_snapshot(self):
        with pytest.raises(DslError, match="snapshot"):
            self.compile(self._static(affects={"types": ["Artifact"], "tapped": True}))

    def test_it_needs_every_ability(self):
        with pytest.raises(DslError, match="'any': true"):
            self.compile(self._static(affects_abilities={"equip": True}))

    def test_it_counts_only_your_activations(self):
        with pytest.raises(DslError, match="activated_by"):
            self.compile(self._static(activated_by="any"))

    def test_hojos_keys_are_refused_beside_it(self):
        with pytest.raises(DslError, match="first_each_turn picks"):
            self.compile(self._static(targeting={"types": ["Creature"]}))

    def test_on_another_static_it_is_refused(self):
        with pytest.raises(DslError, match="'first_each_turn' only means"):
            self.compile(
                {
                    "kind": "static",
                    "text": "Creatures you control get +1/+1.",
                    "effect": "buff",
                    "affects": {"controller": "you"},
                    "power": {"const": 1},
                    "toughness": {"const": 1},
                    "first_each_turn": True,
                }
            )
