"""A static that makes somebody else's **activated ability** cost more mana.

"Abilities your opponents activate that target a Merfolk you control cost {2}
more to activate." Kopala, Warden of Waves, the witness.

602.2b runs an activation through 601.2b-h, so 601.2f's cost increases apply
to it exactly as to a spell. `ability_cost_reduction` could only discount, and
read its `targeting` clause generously at the pre-target gate; a negative
amount there would have been a tax read the reduction's way, offering aims the
payment then refuses. `spell_cost_increase` taxed casts only.

`ability_cost_increase` is the mirror, and it takes `spell_mana_tax`'s
conventions whole. The surcharge is netted into `costs.ability_mana` as a
negative discount -- the one number legality, `can_pay` and `pay` share -- so
the offer and the charge cannot disagree. Its `targeting` clause is read
**meanly** at the gate, before any target exists, and every tuple legality
enumerates is then priced at its own targets: the plain per-aim pass, the
per-X pass for an ability whose targets read X, and the X ceiling `Game._activate`
asks once the targets are declared. A mana ability has no targets (605.1a), so
the clause never reaches one.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import ability_mana_tax
from tests.conftest import activations, only_oid, settle

KOPALA = "t_aci_kopala"
MERFOLK = "t_aci_merfolk"
BEAR = "t_aci_bear"
TAPPER = "t_aci_tapper"  # {1}: tap target creature
PUMPER = "t_aci_pumper"  # {X}: tap target creature, gain X life -- X asked after targets
AIMER = "t_aci_aimer"  # {X}: tap target creature with mana value X -- X offered with targets
EQUIP_TAX = "t_aci_equip_tax"  # equip abilities opponents activate cost {1} more
BLADE = "t_aci_blade"  # equip {1}


def board(builder, rod=TAPPER, *, islands=3, mine=(KOPALA, MERFOLK, BEAR), theirs=()):
    """P0 holds Kopala's line and the creatures; P1 holds a rod and the mana, and acts."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, ["island"] * islands + [rod] + list(theirs))
        .active(1)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def aims(game, rod=TAPPER) -> dict[int, list]:
    """Each oid P1 may aim ``rod`` at, with the activations doing it."""
    out: dict[int, list] = {}
    for a in activations(game, only_oid(game, rod, 1)):
        for ref in a.targets:
            out.setdefault(ref.id, []).append(a)
    return out


def islands_tapped_since(game, mark: int) -> int:
    return sum(
        1
        for event in list(game.state.events)[mark:]
        if event.type == "tapped" and game.state.objects[event.data["oid"]].def_id == "island"
    )


def tax(game, at: int, *, pid: int = 1, rod=TAPPER) -> int:
    oid = only_oid(game, rod, 1)
    ability = game.state.card_of(game.state.objects[oid]).abilities[0]
    targets = aims(game, rod)[at][0].targets
    return ability_mana_tax(game.state, pid, ability, oid, targets)


class TestWhatItTaxes:
    def test_an_ability_aimed_at_my_merfolk_costs_two_more(self, builder):
        game = board(builder)
        assert tax(game, only_oid(game, MERFOLK, 0)) == 2

    def test_an_ability_aimed_at_a_non_merfolk_is_not_taxed(self, builder):
        game = board(builder)
        assert tax(game, only_oid(game, BEAR, 0)) == 0

    def test_an_opponents_merfolk_is_not_protected(self, builder):
        """"a Merfolk **you** control" -- the static's controller's."""
        game = board(builder, theirs=(MERFOLK,))
        assert tax(game, only_oid(game, MERFOLK, 1)) == 0

    def test_its_controllers_own_activation_is_not_taxed(self, builder):
        """"Abilities your **opponents** activate"."""
        game = board(builder)
        assert tax(game, only_oid(game, MERFOLK, 0), pid=0) == 0

    def test_the_gate_reads_the_clause_meanly(self, builder):
        """No targets yet: the tax is left out, so the gate refuses nothing
        the activator could afford aimed elsewhere."""
        game = board(builder)
        oid = only_oid(game, TAPPER, 1)
        ability = game.state.card_of(game.state.objects[oid]).abilities[0]
        assert ability_mana_tax(game.state, 1, ability, oid, None) == 0


class TestTheOfferAndTheCharge:
    def test_unaffordable_aim_is_not_offered(self, builder):
        """{1} plus {2} is three mana, and two Islands cannot pay it."""
        game = board(builder, islands=2)
        offered = aims(game)
        assert only_oid(game, MERFOLK, 0) not in offered
        assert only_oid(game, BEAR, 0) in offered, "aimed elsewhere it still costs {1}"

    def test_affordable_aim_is_offered_and_the_surcharge_is_paid(self, builder):
        game = board(builder, islands=3)
        merfolk = only_oid(game, MERFOLK, 0)
        mark = len(game.state.events)
        game.apply(aims(game)[merfolk][0])
        assert islands_tapped_since(game, mark) == 3, "{1} and {2} -- three Islands"
        settle(game)
        assert any(
            e.type == "tapped" and e.data["oid"] == merfolk
            for e in list(game.state.events)[mark:]
        ), "and the ability resolves"

    def test_without_kopala_it_is_the_printed_price(self, builder):
        game = board(builder, islands=1, mine=(MERFOLK,))
        assert only_oid(game, MERFOLK, 0) in aims(game)


class TestAnnouncedX:
    def test_x_asked_after_targets_has_the_tax_under_its_ceiling(self, builder):
        """Four Islands, the Merfolk targeted: {X} plus {2}, so X is at most 2."""
        game = board(builder, PUMPER, islands=4)
        merfolk = only_oid(game, MERFOLK, 0)
        game.apply(aims(game, PUMPER)[merfolk][0])
        assert game.pending().kind is DecisionKind.CHOOSE_X
        assert len(game.legal_actions()) == 3, "X of 0, 1 or 2"

    def test_x_asked_after_a_non_merfolk_target_is_untaxed(self, builder):
        game = board(builder, PUMPER, islands=4)
        bear = only_oid(game, BEAR, 0)
        game.apply(aims(game, PUMPER)[bear][0])
        assert game.pending().kind is DecisionKind.CHOOSE_X
        assert len(game.legal_actions()) == 5, "X of 0 to 4"

    def test_x_offered_with_its_targets_is_priced_per_aim(self, builder):
        """The Merfolk has mana value 1, so X = 1 aims at it: {1} plus {2}.
        Two Islands pay for the Bear at X = 2 but not the Merfolk at X = 1."""
        game = board(builder, AIMER, islands=2)
        offered = aims(game, AIMER)
        assert only_oid(game, MERFOLK, 0) not in offered
        assert [a.x for a in offered[only_oid(game, BEAR, 0)]] == [2]

    def test_x_offered_with_its_targets_is_charged_the_tax(self, builder):
        game = board(builder, AIMER, islands=3)
        merfolk = only_oid(game, MERFOLK, 0)
        (action,) = aims(game, AIMER)[merfolk]
        assert action.x == 1
        mark = len(game.state.events)
        game.apply(action)
        assert islands_tapped_since(game, mark) == 3


class TestAClassWithoutTargeting:
    def test_an_opponents_equip_costs_one_more(self, builder):
        """Read at the gate as well as per aim: there is no clause to wait for."""
        game = (
            builder(players=2)
            .battlefield(0, [EQUIP_TAX])
            .battlefield(1, ["island", BLADE, BEAR])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        assert not activations(game, only_oid(game, BLADE, 1))

    def test_two_islands_pay_for_it(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [EQUIP_TAX])
            .battlefield(1, ["island", "island", BLADE, BEAR])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        (action,) = activations(game, only_oid(game, BLADE, 1))
        mark = len(game.state.events)
        game.apply(action)
        assert islands_tapped_since(game, mark) == 2


class TestTheLoader:
    def _card(self, **static) -> CardModel:
        line = {
            "kind": "static",
            "text": "Abilities your opponents activate that target a Merfolk you control cost {2} more to activate.",
            "effect": "ability_cost_increase",
            "affects_abilities": {"any": True},
            "activated_by": "opponent",
            "targeting": {"controller": "you", "subtypes": ["Merfolk"]},
            "cost": {"mana": "{2}"},
        }
        line.update(static)
        line = {k: v for k, v in line.items() if v is not None}
        return CardModel.model_validate(
            {
                "id": "t_aci_probe",
                "name": "Test Ability Toll",
                "mana_cost": "{2}",
                "types": ["Enchantment"],
                "oracle_text": line["text"],
                "abilities": [line],
            }
        )

    def test_kopalas_line_loads(self):
        compile_card(self._card())

    def test_any_without_targeting_is_refused(self):
        """A tap-only mana ability never reaches the static."""
        with pytest.raises(DslError, match="targeting"):
            compile_card(self._card(targeting=None))

    def test_no_class_is_refused(self):
        with pytest.raises(DslError, match="affects_abilities"):
            compile_card(self._card(affects_abilities=None))

    def test_no_cost_is_refused(self):
        with pytest.raises(DslError, match="needs a 'cost'"):
            compile_card(self._card(cost=None))

    def test_a_coloured_surcharge_is_refused(self):
        with pytest.raises(DslError, match="generic"):
            compile_card(self._card(cost={"mana": "{U}"}))

    def test_life_is_refused(self):
        with pytest.raises(DslError, match="generic mana"):
            compile_card(self._card(cost={"pay_life": 2}))

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="amount"):
            compile_card(self._card(amount={"const": 2}))
