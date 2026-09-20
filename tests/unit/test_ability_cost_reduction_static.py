"""A static that discounts *another* permanent's activated ability.

    "**Equip abilities you activate** … cost {3} less to activate."
                                                    -- Strong Back

`spell_cost_reduction` was the only cost-lowering static, and it prices spells:
`player_statics.spell_cost_reduction` is handed a `CardDef` being cast. The one
reduction that reached an activated ability was `Cost.mana_reduction`, and it is
a different sentence -- it lives *inside the ability's own cost node*, so only
the card printing the ability could discount it. Strong Back is an Aura
discounting somebody else's Equipment, and nothing could say that.

So this is `spell_cost_reduction`'s mirror: that one picks a **spell** out by
its printed face, this one picks an **activated ability** out by what class of
ability it is and whose permanent prints it.

Read in `costs.ability_mana`, which is the one function `can_pay` and `pay` both
reach -- an ability offered at the reduced price and charged the printed one
would strand the payment, which is the care `life_cost` and `mana_produced`
already take. Added to the ability's own `mana_reduction` rather than replacing
it: two cards may both be talking about the same activation, and the printed
answer is that both apply.

`affects_abilities` names the class, which is what `Ability.is_equip` exists
for -- the reconfigure permanent in the pool is the near miss, an activated,
sorcery-speed ability whose whole effect is an attach, and it is not discounted.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import ability_mana
from automtg.engine.enums import Step
from automtg.engine.errors import DslError
from tests.conftest import only_oid

AURA = "t_acr_aura"  # equip abilities you activate cost {3} less
BLADE = "t_acr_blade"  # equip {5}
RECONFIG = "t_acr_reconfig"  # reconfigure {5} -- an attach that is not equip
BEAR = "t_acr_bear"


def board(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def price(game, card_id: str, index: int = -1, pid: int = 0) -> int:
    """The generic half of what this ability costs ``pid`` right now."""
    oid = only_oid(game, card_id)
    card = game.state.card_of(game.state.objects[oid])
    ability = card.abilities[index]
    return ability_mana(
        game.state, pid, ability.cost, 0, oid, ability=ability
    ).generic


class TestThePriceFollowsTheBoard:
    def test_without_the_aura_it_is_the_printed_cost(self, builder):
        game = board(builder, mine=[BLADE])
        assert price(game, BLADE) == 5

    def test_the_aura_takes_three_off(self, builder):
        game = board(builder, mine=[AURA, BLADE])
        assert price(game, BLADE) == 2

    def test_two_auras_take_six_off(self, builder):
        """Each static is its own reduction, summed by `ability_mana`."""
        game = board(builder, mine=[AURA, AURA, BLADE])
        assert price(game, BLADE) == 0

    def test_it_never_goes_below_zero(self, builder):
        game = board(builder, mine=[AURA, AURA, AURA, BLADE])
        assert price(game, BLADE) == 0


class TestWhatItDoesNotDiscount:
    def test_a_reconfigure_ability_is_untouched(self, builder):
        """The near miss `Ability.is_equip` exists to keep out: an activated,
        sorcery-speed ability whose whole effect is an attach, printing no such
        word."""
        game = board(builder, mine=[AURA, RECONFIG])
        assert price(game, RECONFIG) == 5

    def test_an_opponents_aura_does_not_discount_your_equip(self, builder):
        """"abilities **you** activate" -- and the activating player is what is
        compared, not the permanent's controller."""
        game = board(builder, mine=[BLADE], theirs=[AURA])
        assert price(game, BLADE) == 5

    def test_your_aura_does_not_discount_an_opponents_activation(self, builder):
        game = board(builder, mine=[AURA, BLADE])
        assert price(game, BLADE, pid=1) == 5


class TestTheLoaderPlacesIt:
    def _card(self, ability):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Equip abilities you activate cost {3} less to activate.",
                "mana_cost": "{G}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def _static(self, **extra):
        base = {
            "kind": "static",
            "text": "Equip abilities you activate cost {3} less to activate.",
            "effect": "ability_cost_reduction",
            "affects_abilities": {"equip": True},
            "amount": {"const": 3},
        }
        base.update(extra)
        return base

    def test_a_well_formed_static_loads(self):
        compile_card(self._card(self._static()))

    def test_without_a_class_it_is_refused(self):
        """A discount naming no class reaches every activated ability on the
        table, which is a card nobody printed."""
        with pytest.raises(DslError, match="needs 'affects_abilities'"):
            compile_card(self._card(self._static(affects_abilities=None)))

    def test_an_unknown_class_is_refused(self):
        """A class with no marker behind it loads and matches nothing -- the
        printed line silently not happening."""
        with pytest.raises(DslError, match="unknown ability classes"):
            compile_card(self._card(self._static(affects_abilities={"cycling": True})))

    def test_without_an_amount_it_is_refused(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(self._card(self._static(amount=None)))

    def test_an_unknown_activator_is_refused(self):
        with pytest.raises(DslError, match="must be 'you', 'opponent' or 'any'"):
            compile_card(self._card(self._static(activated_by="everyone")))

    def test_the_fields_are_refused_on_another_static(self):
        with pytest.raises(DslError, match="only mean anything on an"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "text": "Creatures you control get +1/+1.",
                        "effect": "buff",
                        "affects": {"controller": "you"},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "affects_abilities": {"equip": True},
                    }
                )
            )
