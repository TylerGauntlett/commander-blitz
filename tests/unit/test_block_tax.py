"""Archangel of Tithes: a block that can be bought, not one that is forbidden.

"As long as this creature is attacking, creatures can't block unless their
controller pays {1} for each of those creatures."

Rule 509.1d: the defending player checks each creature for costs it must pay
to block, and 509.1e lets them pay or not -- a block they cannot fund simply
is not declared. Every blocking near miss in the engine is absolute: the
`cant_block` static and op forbid outright, and `block_restriction` refuses a
blocker by what it *is* with no payment path at all. An Archangel built on any
of them would be a lock on blocking rather than a toll on it -- strictly
stronger than what is printed, and it would look entirely normal on screen.

So `block_tax` is `attack_tax`'s twin at declare-blockers: the price is read
from the statics, withheld from the action list when unaffordable, written on
the label when it is, and charged as each blocker is declared. One creature
blocks one attacker here, so one block is one price -- 509.1d's "for each of
those creatures".

The card's *other* half needed a widening of `attack_tax`, not a new effect:
"creatures can't attack you **or planeswalkers you control**". Propaganda's
sentence names only the player, and attacking a planeswalker is not attacking
its controller (506.2), so `or_planeswalkers` is a flag the card writes rather
than a default anything infers.

Both halves are switched by the Archangel's own combat state through the
static condition language it already had -- ``exists`` over ``self_only`` with
``tapped: false`` or ``attacking: true`` -- and both switch off the moment that
state changes, which is the wearing-off this file pins.

509.1c is the last claim: a player is never required to pay a block tax to
obey a block requirement, so a provoked creature under the toll owes nothing.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.combat import unmet_block_requirements
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.player_statics import block_tax
from automtg.engine.structs import TargetRef
from automtg.engine.zones import move_object
from tests.conftest import advance_to_step, find_action, oids_of, only_oid, pass_until

BEAR = "t_bear"  # 2/2
TOLL = "t_block_toll"  # unconditional: creatures can't block unless {1} each
ANGEL = "t_tithe_angel"  # Archangel of Tithes' shape, both statics gated
PROPAGANDA = "t_propaganda"  # attack_tax {2}, the player only
WALKER = "t_walker"  # loyalty 4


def position(builder, *, attackers=(BEAR,), defenders=(BEAR,), lands=1, extra=()):
    """Player 0 attacks with ``attackers``; player 1 holds ``defenders`` and Forests.

    ``extra`` goes onto player 1's side too -- a toll, usually.
    """
    b = builder(players=2).battlefield(0, list(attackers))
    b = b.battlefield(1, list(defenders) + list(extra))
    if lands:
        b = b.battlefield(1, ["forest"] * lands)
    return b.build()


def to_blockers(game, attackers: list[int]) -> None:
    """Declare ``attackers`` against player 1 and advance to declare-blockers."""
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    for oid in attackers:
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)


def block_actions(game) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.ADD_BLOCKER]


def untapped_forests(game, pid: int = 1) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == "forest"
        and game.state.objects[oid].controller == pid
        and not game.state.objects[oid].tapped
    )


class TestTheBlockIsPricedNotForbidden:
    def test_it_is_offered_when_the_tax_can_be_paid(self, builder):
        game = position(builder, extra=(TOLL,), lands=1)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        assert block_actions(game), "one Forest pays {1}: the block is legal"

    def test_the_price_is_on_the_label(self, builder):
        game = position(builder, extra=(TOLL,), lands=1)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        assert all("(pay {1})" in (a.label or "") for a in block_actions(game))

    def test_it_is_withheld_when_the_tax_cannot_be_paid(self, builder):
        """An unpayable tax is a prohibition (509.1e), not a rewound block."""
        game = position(builder, extra=(TOLL,), lands=0)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        assert block_actions(game) == []
        assert find_action(game, ActionKind.FINISH_DECLARATION), "not blocking is still fine"

    def test_without_the_toll_the_block_is_free(self, builder):
        game = position(builder, lands=0)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        assert block_actions(game)
        assert not any("pay" in (a.label or "") for a in block_actions(game))


class TestPayingIt:
    def test_declaring_charges_the_blockers_controller(self, builder):
        game = position(builder, extra=(TOLL,), lands=1)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        assert untapped_forests(game) == 1
        game.apply(block_actions(game)[0])
        assert untapped_forests(game) == 0, "the {1} really was paid, by player 1"

    def test_the_creature_is_blocking_afterwards(self, builder):
        game = position(builder, extra=(TOLL,), lands=1)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        blocker = only_oid(game, BEAR, 1)
        game.apply(block_actions(game)[0])
        assert blocker in game.state.combat.blockers


class TestItIsPerBlockingCreature:
    def test_two_forests_fund_exactly_two_blockers(self, builder):
        game = position(builder, attackers=(BEAR,) * 3, defenders=(BEAR,) * 3, extra=(TOLL,), lands=2)
        to_blockers(game, oids_of(game, BEAR, 0))
        game.apply(block_actions(game)[0])
        assert untapped_forests(game) == 1
        game.apply(block_actions(game)[0])
        assert untapped_forests(game) == 0
        assert block_actions(game) == [], (
            "the third blocker cannot be paid for -- and the two already "
            "declared must not be stranded by that"
        )
        assert len(game.state.combat.blockers) == 2

    def test_one_creature_offered_against_two_attackers_is_one_price(self, builder):
        """Priced per blocker, not per (blocker, attacker) pair on offer."""
        game = position(builder, attackers=(BEAR, BEAR), extra=(TOLL,), lands=1)
        to_blockers(game, oids_of(game, BEAR, 0))
        assert len(block_actions(game)) == 2
        assert all("(pay {1})" in (a.label or "") for a in block_actions(game))

    def test_two_tolls_add_up(self, builder):
        game = position(builder, extra=(TOLL, TOLL), lands=1)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        assert block_actions(game) == [], "one Forest cannot pay {2}"
        richer = position(builder, extra=(TOLL, TOLL), lands=2)
        to_blockers(richer, [only_oid(richer, BEAR, 0)])
        assert all("(pay {2})" in (a.label or "") for a in block_actions(richer))

    def test_it_taxes_every_controllers_creatures(self, builder):
        """"Creatures can't block" names no seat: the toll's own controller
        pays too, unlike an attack tax, which protects one."""
        game = position(builder, extra=(TOLL,), lands=1)
        blocker = only_oid(game, BEAR, 1)
        assert block_tax(game.state, blocker) == "{1}"
        assert block_tax(game.state, only_oid(game, BEAR, 0)) == "{1}"


class TestTheTaxWearsOff:
    def test_the_toll_leaving_frees_the_block(self, builder):
        game = position(builder, extra=(TOLL,), lands=0)
        to_blockers(game, [only_oid(game, BEAR, 0)])
        assert block_actions(game) == []
        move_object(game.state, only_oid(game, TOLL, 1), Zone.GRAVEYARD)
        game.state.bump_chars()
        assert block_actions(game), "a static read live, not a price written once"


class TestTheAngelGatesOnItsOwnCombatState:
    def angel_attacks(self, builder, *, with_angel: bool, lands: int):
        game = position(builder, attackers=(ANGEL, BEAR), defenders=(BEAR,), lands=lands)
        attackers = [only_oid(game, BEAR, 0)]
        if with_angel:
            attackers.append(only_oid(game, ANGEL, 0))
        to_blockers(game, attackers)
        return game

    def test_while_it_attacks_blocks_are_taxed(self, builder):
        game = self.angel_attacks(builder, with_angel=True, lands=0)
        assert block_actions(game) == [], "the Angel is attacking: blocking costs {1}"
        paid = self.angel_attacks(builder, with_angel=True, lands=1)
        assert all("(pay {1})" in (a.label or "") for a in block_actions(paid))
        assert block_actions(paid)

    def test_while_it_stays_home_blocks_are_free(self, builder):
        """The boundary: the Angel on the battlefield but not attacking."""
        game = self.angel_attacks(builder, with_angel=False, lands=0)
        assert block_actions(game), "no attacking Angel, no block tax"

    def test_untapped_it_taxes_attacks_on_its_controller(self, builder):
        game = builder(players=2).battlefield(0, [BEAR]).battlefield(1, [ANGEL]).build()
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]
        game = (
            builder(players=2)
            .battlefield(0, [BEAR, "forest"])
            .battlefield(1, [ANGEL])
            .build()
        )
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        attack = find_action(game, ActionKind.ADD_ATTACKER, source=only_oid(game, BEAR, 0))
        assert "(pay {1})" in (attack.label or "")

    def test_tapped_it_taxes_nothing(self, builder):
        """The wearing-off: "as long as this creature is untapped"."""
        game = builder(players=2).battlefield(0, [BEAR]).battlefield(1, [ANGEL]).build()
        game.state.objects[only_oid(game, ANGEL, 1)].tapped = True
        game.state.bump_chars()
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        attack = find_action(game, ActionKind.ADD_ATTACKER, source=only_oid(game, BEAR, 0))
        assert "pay" not in (attack.label or "")

    def test_attacking_taps_it_and_switches_the_attack_tax_off(self, builder):
        """The two halves hand over: the attacking Angel is tapped, so its own
        controller's opponents attack freely next -- and blocks cost {1} now."""
        game = position(builder, attackers=(ANGEL,), defenders=(BEAR,), lands=1)
        to_blockers(game, [only_oid(game, ANGEL, 0)])
        angel = only_oid(game, ANGEL, 0)
        assert game.state.objects[angel].tapped
        assert block_tax(game.state, only_oid(game, BEAR, 1)) == "{1}"


class TestItReachesPlaneswalkers:
    def walker_attack(self, builder, fort: str, lands: int):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR] + ["forest"] * lands)
            .battlefield(1, [fort, WALKER])
            .build()
        )
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        walker = only_oid(game, WALKER, 1)
        return game, [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.targets[0] == TargetRef.obj(walker)
        ]

    def test_an_attack_on_its_controllers_walker_is_taxed(self, builder):
        _, offered = self.walker_attack(builder, ANGEL, lands=0)
        assert offered == [], "{1} unpaid: the walker cannot be attacked"
        _, offered = self.walker_attack(builder, ANGEL, lands=1)
        assert len(offered) == 1 and "(pay {1})" in (offered[0].label or "")

    def test_declaring_it_charges_the_mana(self, builder):
        game, offered = self.walker_attack(builder, ANGEL, lands=1)
        game.apply(offered[0])
        forest = only_oid(game, "forest", 0)
        assert game.state.objects[forest].tapped
        assert only_oid(game, BEAR, 0) in game.state.combat.attackers

    def test_propaganda_still_leaves_the_walker_alone(self, builder):
        """The flag is the printed sentence: Propaganda names only "you"."""
        _, offered = self.walker_attack(builder, PROPAGANDA, lands=0)
        assert len(offered) == 1 and "pay" not in (offered[0].label or "")


class TestNobodyMustPayToObeyARequirement:
    def test_a_provoked_creature_under_the_toll_owes_nothing(self, builder):
        """509.1c: the requirement does not oblige the payment."""
        game = position(builder, extra=(TOLL,), lands=1)
        attacker = only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        game.state.objects[blocker].must_block = attacker
        to_blockers(game, [attacker])
        assert unmet_block_requirements(game.state, 1) == []
        find_action(game, ActionKind.FINISH_DECLARATION)

    def test_without_the_toll_the_same_requirement_binds(self, builder):
        """The counterfactual: 'Done blocking' is withheld until it blocks."""
        game = position(builder, lands=0)
        attacker = only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        game.state.objects[blocker].must_block = attacker
        to_blockers(game, [attacker])
        assert unmet_block_requirements(game.state, 1) == [blocker]


class TestTheLoader:
    def _card(self, static):
        return CardModel.model_validate(
            {
                "id": "t_bad_toll",
                "name": "Bad Toll",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "colors": ["W"],
                "color_identity": ["W"],
                "abilities": [{"kind": "static", "text": "Bad.", **static}],
            }
        )

    AFFECTS = {"controller": "any", "types": ["Creature"]}

    def test_the_angel_compiles_with_both_statics(self, registry):
        statics = [a.static for a in registry.get(ANGEL).abilities if a.is_static]
        assert [s["effect"] for s in statics] == ["attack_tax", "block_tax"]
        assert statics[0]["or_planeswalkers"] is True
        assert statics[1]["cost"] == {"mana": "{1}"}

    def test_a_toll_with_no_cost_is_refused(self):
        with pytest.raises(DslError, match="block_tax needs a 'cost'"):
            compile_card(self._card({"effect": "block_tax", "affects": self.AFFECTS}))

    def test_a_non_mana_toll_is_refused(self):
        with pytest.raises(DslError, match="mana only"):
            compile_card(
                self._card(
                    {
                        "effect": "block_tax",
                        "affects": self.AFFECTS,
                        "cost": {"mana": "{1}", "pay_life": 1},
                    }
                )
            )

    def test_a_toll_that_names_no_creature_is_refused(self):
        """A missing filter matches nothing: a toll that taxes nobody."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(self._card({"effect": "block_tax", "cost": {"mana": "{1}"}}))

    def test_or_planeswalkers_belongs_to_the_attack_tax_only(self):
        with pytest.raises(DslError, match="'or_planeswalkers' only means"):
            compile_card(
                self._card(
                    {
                        "effect": "block_tax",
                        "affects": self.AFFECTS,
                        "cost": {"mana": "{1}"},
                        "or_planeswalkers": True,
                    }
                )
            )
