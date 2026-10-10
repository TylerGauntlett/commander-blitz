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

`targeting` is the third clause, and the one that reads the **activation**
rather than the board: "equip abilities you activate *that target enchanted
creature*". That makes the price a question about which creature is being
equipped, which is why `ability_mana` takes the chosen targets and why legality
prices each aim separately -- its first `can_pay` is a *gate*, asked before a
single target tuple exists, and reads the clause generously so an activation
that is affordable once discounted is not dropped before it can be offered.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import ability_mana
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, two_seat_board

AURA = "t_acr_aura"  # equip abilities you activate cost {3} less
BLADE = "t_acr_blade"  # equip {5}
RECONFIG = "t_acr_reconfig"  # reconfigure {5} -- an attach that is not equip
AIMED = "t_acr_aimed"  # the same discount, only for equips aimed at what it is on
BEAR = "t_acr_bear"
OTHER = "t_acr_other_bear"


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
        game = two_seat_board(builder, mine=[BLADE])
        assert price(game, BLADE) == 5

    def test_the_aura_takes_three_off(self, builder):
        game = two_seat_board(builder, mine=[AURA, BLADE])
        assert price(game, BLADE) == 2

    def test_two_auras_take_six_off(self, builder):
        """Each static is its own reduction, summed by `ability_mana`."""
        game = two_seat_board(builder, mine=[AURA, AURA, BLADE])
        assert price(game, BLADE) == 0

    def test_it_never_goes_below_zero(self, builder):
        game = two_seat_board(builder, mine=[AURA, AURA, AURA, BLADE])
        assert price(game, BLADE) == 0


class TestWhatItDoesNotDiscount:
    def test_a_reconfigure_ability_is_untouched(self, builder):
        """The near miss `Ability.is_equip` exists to keep out: an activated,
        sorcery-speed ability whose whole effect is an attach, printing no such
        word."""
        game = two_seat_board(builder, mine=[AURA, RECONFIG])
        assert price(game, RECONFIG) == 5

    def test_an_opponents_aura_does_not_discount_your_equip(self, builder):
        """"abilities **you** activate" -- and the activating player is what is
        compared, not the permanent's controller."""
        game = two_seat_board(builder, mine=[BLADE], theirs=[AURA])
        assert price(game, BLADE) == 5

    def test_your_aura_does_not_discount_an_opponents_activation(self, builder):
        game = two_seat_board(builder, mine=[AURA, BLADE])
        assert price(game, BLADE, pid=1) == 5


class TestTheTargetingClause:
    """"equip abilities you activate **that target enchanted creature**".

    The clause reads the *activation* rather than the board, so the price is a
    question about which creature is being equipped -- and that is why
    `ability_mana` takes the chosen targets and legality prices each aim
    separately.
    """

    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 6)
            .battlefield(0, [BLADE, BEAR, OTHER])
            .battlefield(0, [AIMED])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        # It is attached to the first bear. By hand, because the discount is
        # about what it is attached *to* and casting it is a different test --
        # and it is an Equipment rather than the printed Aura because an Aura
        # attached to nothing is buried by the state-based actions, while
        # `attached` means the same thing on either.
        from commanderblitz.engine.primitives import attach

        assert attach(game.state, only_oid(game, AIMED), only_oid(game, BEAR))
        game.state.bump_chars()
        return game

    def equip_price(self, game, at: str) -> int:
        """What equipping ``at`` costs, priced with that target in hand."""
        oid = only_oid(game, BLADE)
        ability = game.state.card_of(game.state.objects[oid]).abilities[-1]
        wanted = only_oid(game, at)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == oid
            and any(r.id == wanted for r in a.targets)
        )
        return ability_mana(
            game.state,
            0,
            ability.cost,
            0,
            oid,
            ability=ability,
            targets=action.targets,
        ).generic

    def test_equipping_the_attached_creature_is_discounted(self, builder):
        game = self.board(builder)
        assert self.equip_price(game, BEAR) == 2

    def test_equipping_anything_else_is_not(self, builder):
        """The clause, and the whole difference between this card and the one
        in the class above."""
        game = self.board(builder)
        assert self.equip_price(game, OTHER) == 5

    def test_both_aims_are_still_offered(self, builder):
        """The discount narrows the *price*, not the legality: equipping the
        other creature is a legal activation at the printed cost."""
        game = self.board(builder)
        oid = only_oid(game, BLADE)
        aimed_at = {
            game.state.objects[a.targets[0].id].def_id
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == oid and a.targets
        }
        assert {BEAR, OTHER} <= aimed_at


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
