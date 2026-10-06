"""Propaganda: an attack that can be bought, not one that is forbidden.

"Creatures can't attack you unless their controller pays {2} for each creature
they control that's attacking you."

The two nearest things in the engine are both absolute. The `cant_attack`
static (read by `combat.can_attack`) matches a creature by printed
characteristics and forbids it outright; the `cant_attack_player` op writes an
`AttackRestriction` over a pair of players for a duration. Neither has a price,
so a Propaganda built on either is a *lock* — strictly stronger than what is
printed, and it would look entirely normal on screen. `ward` is the only other
cost-parameterised static and it prices targeting, paying out as a triggered
counter that never reaches the declare-attackers step.

Where the tax is charged is the design. 508.1g settles the whole declaration's
costs at once; charging {2} as each attacker is declared reaches the same total,
because the printed price is per attacking creature — and it means a third
attacker nobody can afford cannot strand a declaration the first two paid for.
An unpayable tax is a prohibition, so the action is withheld rather than offered
and rewound.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step
from automtg.engine.errors import DslError
from tests.conftest import advance_to_step, only_oid

BEAR = "grizzly_bears"  # a plain 2/2
FORT = "t_propaganda"


def board(builder, *, lands: int, bears: int = 1, forts: int = 1):
    """Player 0 attacks; player 1 sits behind `forts` Propagandas."""
    b = (
        builder(players=2)
        .battlefield(0, [BEAR] * bears)
        .battlefield(0, ["forest"] * lands)
    )
    if forts:
        b = b.battlefield(1, [FORT] * forts)
    game = b.build()
    advance_to_step(game, Step.DECLARE_ATTACKERS)
    return game


def attack_actions(game):
    return [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]


def untapped_forests(game, pid: int = 0) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == "forest"
        and game.state.objects[oid].controller == pid
        and not game.state.objects[oid].tapped
    )


class TestTheAttackIsPricedNotForbidden:
    def test_it_is_offered_when_the_tax_can_be_paid(self, builder):
        game = board(builder, lands=2)
        assert attack_actions(game), "two Forests pay {2}: the attack is legal"

    def test_the_price_is_on_the_label(self, builder):
        """A player choosing between defenders is choosing between prices."""
        game = board(builder, lands=2)
        assert any("pay {2}" in (a.label or "") for a in attack_actions(game))

    def test_it_is_withheld_when_the_tax_cannot_be_paid(self, builder):
        """An unpayable tax is a prohibition (508.1g), not a rewound attack."""
        game = board(builder, lands=1)
        assert attack_actions(game) == []

    def test_without_the_enchantment_the_attack_is_free(self, builder):
        game = board(builder, lands=0, forts=0)
        assert attack_actions(game), "no tax, no lands needed"
        assert not any("pay" in (a.label or "") for a in attack_actions(game))


class TestPayingIt:
    def test_declaring_charges_the_mana(self, builder):
        game = board(builder, lands=2)
        assert untapped_forests(game) == 2
        game.apply(attack_actions(game)[0])
        assert untapped_forests(game) == 0, "the {2} really was paid"

    def test_the_creature_is_attacking_afterwards(self, builder):
        game = board(builder, lands=2)
        game.apply(attack_actions(game)[0])
        bear = only_oid(game, BEAR, 0)
        assert game.state.combat is not None
        assert bear in game.state.combat.attackers


class TestItIsPerAttackingCreature:
    def test_a_second_attacker_costs_another_two(self, builder):
        """Four Forests fund exactly two bears; the third attack is unaffordable."""
        game = board(builder, lands=4, bears=3)
        game.apply(attack_actions(game)[0])
        assert untapped_forests(game) == 2
        game.apply(attack_actions(game)[0])
        assert untapped_forests(game) == 0
        assert attack_actions(game) == [], (
            "the third bear cannot be paid for -- and the two already declared "
            "must not be stranded by that"
        )
        assert len(game.state.combat.attackers) == 2

    def test_two_enchantments_double_the_price(self, builder):
        """Two Propagandas are {4}, not an unpayable '{2}{2}'."""
        game = board(builder, lands=3, forts=2)
        assert attack_actions(game) == [], "three Forests cannot pay {4}"
        richer = board(builder, lands=4, forts=2)
        assert any("pay {4}" in (a.label or "") for a in attack_actions(richer))


class TestItOnlyProtectsItsController:
    def test_attacking_a_different_player_is_untaxed(self, builder):
        """"Creatures can't attack **you**" -- the seat the permanent is under."""
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .battlefield(0, ["forest"] * 2)
            .battlefield(1, [FORT])
            .build()
        )
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        by_defender = {a.targets[0].id: (a.label or "") for a in attack_actions(game)}
        assert "pay {2}" in by_defender[1], "player 1 is behind the enchantment"
        assert "pay" not in by_defender[2], "player 2 is not"


class TestTheLoaderRefusesAToothlessTax:
    def _card(self, static):
        return CardModel.model_validate(
            {
                "id": "t_bad_tax",
                "name": "Bad Tax",
                "oracle_text": "Bad.",
                "mana_cost": "{U}",
                "types": ["Enchantment"],
                "colors": ["U"],
                "color_identity": ["U"],
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

    def test_a_tax_with_no_cost_is_a_load_error(self):
        """Without a price it is `cant_attack` wearing a costume."""
        with pytest.raises(DslError, match="attack_tax needs a 'cost'"):
            compile_card(self._card({"effect": "attack_tax"}))

    def test_a_non_mana_tax_is_a_load_error(self):
        """It would have to ask a question inside the attack declaration."""
        with pytest.raises(DslError, match="mana only"):
            compile_card(
                self._card(
                    {
                        "effect": "attack_tax",
                        "cost": {"mana": "{2}", "pay_life": 2},
                    }
                )
            )
