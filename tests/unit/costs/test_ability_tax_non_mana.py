"""A tax on **every non-mana activated ability** an opponent activates.

"During your turn, spells your opponents cast cost {1} more to cast and
abilities your opponents activate cost {1} more to activate unless they're mana
abilities." Tithe Taker, the witness.

602.2b runs an activation through 601.2b-h, so 601.2f's increases apply to it.
`ability_cost_increase` already taxed a class of activation (Kopala's `any`
beside a `targeting` clause, an equip toll), but refused `any` on its own: the
payment solver taps a tap-only mana ability without reaching
`player_statics.ability_mana_tax`, so a blanket tax would have priced the mana
abilities activated by hand and not the ones the solver tapped. Tithe Taker's
sentence ends "unless they're mana abilities" (605), so the class it names is
`non_mana`, which skips a mana ability by `Ability.is_mana_ability` -- the
solver's path and the hand-activated path agree because neither is taxed.

"During your turn" is the static's ordinary `is_your_turn` condition, asked by
`_battlefield_statics` for the spell half and the ability half alike, so the tax
is on for its controller's turn and off for everyone else's.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import ability_mana_tax, spell_mana_tax
from tests.conftest import activations, find_action, only_oid, pass_until, settle

TAKER = "t_atn_taker"
ROD = "t_atn_rod"  # {2}: you gain 1 life -- no targets
FILTER = "t_atn_filter"  # {2}, {T}: Add {G}{G} -- a mana ability with a mana cost
CYCLER = "t_atn_cycler"  # Cycling {1}, from a hand
BOLT = "t_atn_bolt"  # {U} instant


def board(builder, *, active: int = 0, islands: int = 2, taker: bool = True):
    """P0 holds the tax; P1 holds the mana, the rod, the filter and the cards.

    On P0's turn P0 passes once, so P1 holds priority in P0's main phase. The
    Island in P0's hand is a land drop, the decision that stops the auto-pass
    rolling the position on to P1's turn. Two Islands pay for the taxed
    Bolt, so P1 always has a decision and holds the priority it is passed.
    """
    game = (
        builder(players=2)
        .battlefield(0, [TAKER] if taker else [])
        .hand(0, ["island"])
        .battlefield(1, ["island"] * islands + [ROD, FILTER])
        .hand(1, [CYCLER, BOLT])
        .library(0, ["island"] * 5)
        .library(1, ["island"] * 5)
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    assert (game.state.active_player, game.state.step) == (active, Step.PRECOMBAT_MAIN)
    if active == 0:
        game.apply(find_action(game, ActionKind.PASS))
        assert (game.state.active_player, game.state.priority_player) == (0, 1)
    return game


def oid_of(game, card_id: str) -> int:
    """P1's one copy of ``card_id``, on the battlefield or in hand."""
    zones = list(game.state.players[1].hand) + [o.oid for o in game.state.battlefield_objects(1)]
    (oid,) = [o for o in zones if game.state.objects[o].def_id == card_id]
    return oid


def tax_on(game, card_id: str, pid: int = 1) -> int:
    oid = oid_of(game, card_id)
    ability = game.state.card_of(game.state.objects[oid]).abilities[0]
    return ability_mana_tax(game.state, pid, ability, oid, None)


def islands_tapped_since(game, mark: int) -> int:
    return sum(
        1
        for event in list(game.state.events)[mark:]
        if event.type == "tapped" and game.state.objects[event.data["oid"]].def_id == "island"
    )


class TestWhatItTaxes:
    def test_an_untargeted_ability_costs_one_more(self, builder):
        """No `targeting` clause to wait for: the gate reads the tax too."""
        assert tax_on(board(builder), ROD) == 1

    def test_an_ability_activated_from_a_hand_costs_one_more(self, builder):
        """"Abilities your opponents activate" -- cycling is one (602.1)."""
        assert tax_on(board(builder), CYCLER) == 1

    def test_a_mana_ability_activated_by_hand_is_exempt(self, builder):
        """"Unless they're mana abilities" (605.1a): {2}, {T}: Add {G}{G} is one."""
        assert tax_on(board(builder), FILTER) == 0

    def test_its_controllers_own_activation_is_not_taxed(self, builder):
        assert tax_on(board(builder), ROD, pid=0) == 0


class TestDuringYourTurn:
    def test_off_on_the_opponents_own_turn(self, builder):
        assert tax_on(board(builder, active=1), ROD) == 0

    def test_it_wears_off_when_the_turn_passes(self, builder):
        game = board(builder, active=0)
        assert tax_on(game, ROD) == 1
        pass_until(game, lambda g: g.state.active_player == 1)
        assert tax_on(game, ROD) == 0

    def test_gone_with_its_source(self, builder):
        assert tax_on(board(builder, taker=False), ROD) == 0


class TestTheOfferAndTheCharge:
    def test_two_islands_cannot_pay_two_plus_one(self, builder):
        game = board(builder, islands=2)
        assert not activations(game, only_oid(game, ROD, 1))

    def test_three_islands_pay_and_all_three_are_charged(self, builder):
        game = board(builder, islands=3)
        (action,) = activations(game, only_oid(game, ROD, 1))
        mark = len(game.state.events)
        life = game.state.players[1].life
        game.apply(action)
        assert islands_tapped_since(game, mark) == 3
        settle(game)
        assert game.state.players[1].life == life + 1, "and the ability resolves"

    def test_the_mana_ability_is_still_offered_at_its_printed_price(self, builder):
        """Two Islands pay the filter's {2}: no surcharge on a mana ability."""
        game = board(builder, islands=2)
        assert activations(game, only_oid(game, FILTER, 1))

    def test_on_the_activators_own_turn_two_islands_are_enough(self, builder):
        game = board(builder, active=1, islands=2)
        assert activations(game, only_oid(game, ROD, 1))


class TestTheSpellHalf:
    """The other half of the sentence, `spell_cost_increase` under the same
    `is_your_turn` condition."""

    def _tax(self, game) -> int:
        oid = oid_of(game, BOLT)
        return spell_mana_tax(game.state, 1, game.state.card_of(game.state.objects[oid]))

    def test_a_spell_costs_one_more_during_its_controllers_turn(self, builder):
        assert self._tax(board(builder)) == 1

    def test_not_during_the_casters_turn(self, builder):
        assert self._tax(board(builder, active=1)) == 0


class TestTheLoader:
    def _card(self, effect="ability_cost_increase", **static) -> CardModel:
        line = {
            "kind": "static",
            "text": "Abilities your opponents activate cost {1} more to activate unless they're mana abilities.",
            "effect": effect,
            "affects_abilities": {"non_mana": True},
            "activated_by": "opponent",
            "condition": {"is_your_turn": True},
            "cost": {"mana": "{1}"},
        }
        line.update(static)
        line = {k: v for k, v in line.items() if v is not None}
        return CardModel.model_validate(
            {
                "id": "t_atn_probe",
                "name": "Test Tithe Probe",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "oracle_text": line["text"],
                "abilities": [line],
            }
        )

    def test_non_mana_loads_without_targeting(self):
        compile_card(self._card())

    def test_any_without_targeting_is_still_refused(self):
        """`any` would tax the hand-activated mana ability and not the tapped one."""
        with pytest.raises(DslError, match="non_mana"):
            compile_card(self._card(affects_abilities={"any": True}))

    def test_a_discount_may_not_name_non_mana(self):
        with pytest.raises(DslError, match="non_mana"):
            compile_card(
                self._card(
                    effect="ability_cost_reduction", cost=None, amount={"const": 1}
                )
            )

    def test_a_sized_surcharge_is_still_refused(self):
        with pytest.raises(DslError, match="amount"):
            compile_card(self._card(amount={"const": 1}))
