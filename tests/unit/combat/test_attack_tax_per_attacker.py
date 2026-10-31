"""Nils, Discipline Enforcer: an attack tax whose price is read off the attacker.

"Each creature with one or more counters on it can't attack you or
planeswalkers you control unless its controller pays {X}, where X is the number
of counters on that creature."

Rule 508.1g-h: the costs to attack are determined as attackers are declared,
then paid. Propaganda's {2} is the same for every creature; Nils' {X} is a
number each creature carries, so a three-counter creature pays {3} and a
one-counter creature beside it pays {1}. A fixed `attack_tax` cannot say that
-- any fixed price is a different card -- and `cant_attack` would be a lock
rather than a toll.

So `x_per_attacker` sizes the {X} against the creature being declared, through
the one `player_statics.attack_tax` that the action label, the payability check
in `legality` and the charge in `Game._dispatch_attackers` all read. A creature
with no counters is outside the filter and attacks free; X is the live count, so
a counter that leaves before declaration leaves the price too.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import attack_tax
from commanderblitz.engine.primitives import remove_counters
from tests.conftest import advance_to_step, only_oid

BEAR = "grizzly_bears"  # a plain 2/2
GIANT = "t_bear"  # another 2/2, so two attackers are told apart by id
TOLL = "t_counter_toll"  # Nils' second sentence on an enchantment
PROPAGANDA = "t_propaganda"  # attack_tax {2}, the player only
WALKER = "t_walker"


def position(builder, *, counters=None, lands=0, extra=(), players=2, giant=None):
    """Player 0 attacks with a bear wearing ``counters``; player 1 holds ``TOLL``.

    Returns ``(game, bear_oid)`` at declare-attackers.
    """
    b = builder(players=players).battlefield(0, [BEAR], counters=counters)
    if giant is not None:
        b = b.battlefield(0, [GIANT], counters=giant)
    if lands:
        b = b.battlefield(0, ["forest"] * lands)
    b = b.battlefield(1, [TOLL, *extra])
    game = b.build()
    advance_to_step(game, Step.DECLARE_ATTACKERS)
    return game, only_oid(game, BEAR, 0)


def attacks_by(game, oid):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
    ]


def untapped_forests(game) -> int:
    return sum(
        1
        for obj in game.state.battlefield_objects(0)
        if obj.def_id == "forest" and not obj.tapped
    )


class TestXIsReadOffTheAttacker:
    def test_three_counters_cost_three(self, builder):
        game, bear = position(builder, counters={"+1/+1": 3}, lands=3)
        assert attack_tax(game.state, bear, 1) == "{3}"
        (offered,) = attacks_by(game, bear)
        assert "(pay {3})" in (offered.label or "")

    def test_every_kind_of_counter_counts(self, builder):
        """"The number of counters on that creature" -- of any kind."""
        game, bear = position(builder, counters={"+1/+1": 1, "oil": 2}, lands=3)
        assert attack_tax(game.state, bear, 1) == "{3}"

    def test_each_creature_pays_its_own_x(self, builder):
        game, bear = position(
            builder, counters={"+1/+1": 1}, giant={"+1/+1": 3}, lands=4
        )
        giant = only_oid(game, GIANT, 0)
        assert attack_tax(game.state, bear, 1) == "{1}"
        assert attack_tax(game.state, giant, 1) == "{3}"

    def test_a_creature_without_counters_attacks_free(self, builder):
        """Outside the filter: no price at all, not a {0} on the label."""
        game, bear = position(builder, lands=0)
        (offered,) = attacks_by(game, bear)
        assert "pay" not in (offered.label or "")


class TestTheLegalActionsAndTheCharge:
    def test_unaffordable_x_is_withheld(self, builder):
        """An unpayable tax is a prohibition (508.1g), so nothing is offered."""
        game, bear = position(builder, counters={"+1/+1": 3}, lands=2)
        assert attacks_by(game, bear) == []

    def test_declaring_charges_exactly_x(self, builder):
        game, bear = position(builder, counters={"+1/+1": 2}, lands=3)
        game.apply(attacks_by(game, bear)[0])
        assert untapped_forests(game) == 1
        assert bear in game.state.combat.attackers

    def test_two_attackers_pay_their_two_prices(self, builder):
        """{1} then {3}: four Forests fund both, and nothing is left over."""
        game, bear = position(
            builder, counters={"+1/+1": 1}, giant={"+1/+1": 3}, lands=4
        )
        giant = only_oid(game, GIANT, 0)
        game.apply(attacks_by(game, bear)[0])
        assert untapped_forests(game) == 3
        game.apply(attacks_by(game, giant)[0])
        assert untapped_forests(game) == 0
        assert set(game.state.combat.attackers) == {bear, giant}

    def test_it_adds_to_a_fixed_tax(self, builder):
        """Nils' {2} beside Propaganda's {2} is {4}, one summed price."""
        game, bear = position(
            builder, counters={"+1/+1": 2}, lands=4, extra=(PROPAGANDA,)
        )
        (offered,) = attacks_by(game, bear)
        assert "(pay {4})" in (offered.label or "")


class TestTheCountIsLive:
    def test_removing_the_counters_lifts_the_tax(self, builder):
        """508.1g determines the price at declaration, not when it was placed."""
        game, bear = position(builder, counters={"+1/+1": 2}, lands=0)
        assert attacks_by(game, bear) == []
        remove_counters(game.state, bear, "+1/+1", 2)
        (offered,) = attacks_by(game, bear)
        assert "pay" not in (offered.label or "")

    def test_one_counter_fewer_is_one_cheaper(self, builder):
        game, bear = position(builder, counters={"+1/+1": 3}, lands=0)
        remove_counters(game.state, bear, "+1/+1", 1)
        assert attack_tax(game.state, bear, 1) == "{2}"


class TestWhoItProtects:
    def test_attacking_a_different_player_is_untaxed(self, builder):
        """"Can't attack **you**" -- the seat the permanent is under."""
        game, bear = position(builder, counters={"+1/+1": 2}, lands=2, players=3)
        by_defender = {a.targets[0].id: (a.label or "") for a in attacks_by(game, bear)}
        assert "(pay {2})" in by_defender[1]
        assert "pay" not in by_defender[2]

    def test_its_controllers_planeswalker_is_taxed_too(self, builder):
        """"...or planeswalkers you control": `or_planeswalkers` prices the walker."""
        game, bear = position(builder, counters={"+1/+1": 2}, lands=2, extra=(WALKER,))
        walker = only_oid(game, WALKER, 1)
        on_walker = [
            a for a in attacks_by(game, bear) if a.targets[0].kind == "object"
            and a.targets[0].id == walker
        ]
        assert len(on_walker) == 1 and "(pay {2})" in (on_walker[0].label or "")
        assert attack_tax(game.state, bear, 1, planeswalker=True) == "{2}"


class TestTheLoader:
    def _card(self, static):
        return CardModel.model_validate(
            {
                "id": "t_bad_x_tax",
                "name": "Bad X Tax",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "colors": ["W"],
                "color_identity": ["W"],
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Bad.",
                        "affects": {"controller": "any", "types": ["Creature"]},
                        **static,
                    }
                ],
            }
        )

    def test_the_witness_shape_loads(self):
        compile_card(
            self._card(
                {
                    "effect": "attack_tax",
                    "cost": {"mana": "{X}"},
                    "x_per_attacker": {"counters": "any"},
                }
            )
        )

    def test_an_x_with_nothing_to_size_it_is_refused(self):
        """It would be charged as 0 -- a tax that prices nothing."""
        with pytest.raises(DslError, match="needs an 'x_per_attacker'"):
            compile_card(self._card({"effect": "attack_tax", "cost": {"mana": "{X}"}}))

    def test_x_per_attacker_beside_a_fixed_price_is_refused(self):
        with pytest.raises(DslError, match=r"costs \{X\} and nothing else"):
            compile_card(
                self._card(
                    {
                        "effect": "attack_tax",
                        "cost": {"mana": "{2}"},
                        "x_per_attacker": {"counters": "any"},
                    }
                )
            )

    def test_an_unknown_leaf_is_refused(self):
        with pytest.raises(DslError, match="one leaf, 'counters'"):
            compile_card(
                self._card(
                    {
                        "effect": "attack_tax",
                        "cost": {"mana": "{X}"},
                        "x_per_attacker": {"power": True},
                    }
                )
            )

    def test_a_counter_near_miss_is_refused(self):
        """"Shield" is an inert tally; the kind goes through the shared check."""
        with pytest.raises(DslError, match="shield counter"):
            compile_card(
                self._card(
                    {
                        "effect": "attack_tax",
                        "cost": {"mana": "{X}"},
                        "x_per_attacker": {"counters": "Shield"},
                    }
                )
            )

    def test_it_belongs_to_the_attack_tax_only(self):
        with pytest.raises(DslError, match="'x_per_attacker' only means"):
            compile_card(
                self._card(
                    {
                        "effect": "block_tax",
                        "cost": {"mana": "{X}"},
                        "x_per_attacker": {"counters": "any"},
                    }
                )
            )

    def test_a_block_tax_x_is_refused(self):
        with pytest.raises(DslError, match="fixed mana cost"):
            compile_card(self._card({"effect": "block_tax", "cost": {"mana": "{X}"}}))
