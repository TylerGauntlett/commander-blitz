"""A static that makes somebody else's spell cost more **mana**.

"Spells your opponents cast that target a creature or planeswalker you control
cost {2} more to cast." Kasmina, Enigmatic Mentor, the witness.

`spell_cost_increase` shipped for Terror of the Peaks and charged life only. Its
loader refused mana because a surcharge in mana has to reach the payment solver,
and every place the offer and the charge price a spell is a place they could
disagree. They now agree by construction: the tax is netted into the one number
both already share, `cost_reduction.cost_reduction`, as a negative discount. Legality
prices the line with it, `_priced_tuples` re-prices each target tuple with it,
and `Game._cast` charges it off the action's own targets.

601.2f is the order of operations, and netting gets it right. Increases are
added, then reductions are subtracted, and only the generic part can fall, never
below zero. That is (generic + increase - reduction) clamped at zero, which is
what the solver already computes with a negative discount.

The `targeting` clause reads the targets the cast chose. At the gate, before any
target exists, it is read **meanly**, as the life tax reads it. The tax is left
out there, so a spell the caster could afford aimed elsewhere is not refused.
Each target tuple then pays exactly.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import spell_mana_tax
from tests.conftest import only_oid, pass_until

MENTOR = "t_mana_toll_mentor"  # opponents' spells aimed at my creatures cost {2} more
TOLL = "t_mana_toll_all"  # every spell opponents cast costs {1} more
BEAR = "t_bear"
BOLT = "t_bolt"  # {R} instant, 3 damage to any target


def board(builder, mine=(MENTOR, BEAR), *, mountains=6, theirs=()):
    """P0 holds the taxing permanent and a Bear; P1 holds a Bolt and the mana."""
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 4 + list(mine))
        .battlefield(1, ["mountain"] * mountains + list(theirs))
        .hand(1, [BOLT])
        .active(0)
        .build()
    )


def casts(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BOLT
    ]


def aims(game) -> set[int]:
    """Every object oid P1 is allowed to aim the Bolt at right now."""
    pass_until(game, lambda g: bool(casts(g)) or not g.legal_actions())
    return {r.id for a in casts(game) for r in a.targets if r.kind == "object"}


def tax(game, oid: int, *, pid: int = 1) -> int:
    pass_until(game, lambda g: bool(casts(g)))
    targets = next(a for a in casts(game) if any(r.id == oid for r in a.targets)).targets
    return spell_mana_tax(game.state, pid, game.state.registry.get(BOLT), targets)


def mountains_tapped_since(game, mark: int) -> int:
    """Mountains tapped after event ``mark``. Read off the log, because passing
    priority after the cast runs the turn on into the caster's untap step."""
    return sum(
        1
        for event in list(game.state.events)[mark:]
        if event.type == "tapped"
        and game.state.objects[event.data["oid"]].def_id == "mountain"
    )


class TestWhatItTaxes:
    def test_a_spell_aimed_at_my_creature_costs_two_more(self, builder):
        game = board(builder)
        assert tax(game, only_oid(game, BEAR, 0)) == 2

    def test_a_spell_aimed_at_their_own_creature_is_not_taxed(self, builder):
        game = board(builder, theirs=(BEAR,))
        assert tax(game, only_oid(game, BEAR, 1)) == 0

    def test_a_tax_with_no_targeting_clause_reaches_every_spell(self, builder):
        game = board(builder, mine=(TOLL, BEAR), theirs=(BEAR,))
        assert tax(game, only_oid(game, BEAR, 1)) == 1

    def test_two_of_them_stack(self, builder):
        game = board(builder, mine=(MENTOR, TOLL, BEAR))
        assert tax(game, only_oid(game, BEAR, 0)) == 3


class TestTheOfferAndTheCharge:
    def test_unaffordable_aim_is_not_offered(self, builder):
        """{R} plus {2} is three mana, and two Mountains cannot pay it."""
        game = board(builder, mountains=2, theirs=(BEAR,))
        offered = aims(game)
        assert only_oid(game, BEAR, 0) not in offered
        assert only_oid(game, BEAR, 1) in offered, "aimed elsewhere it still costs {R}"

    def test_affordable_aim_is_offered(self, builder):
        game = board(builder, mountains=3)
        assert only_oid(game, BEAR, 0) in aims(game)

    def test_the_surcharge_is_paid(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 0)
        pass_until(game, lambda g: bool(casts(g)))
        mark = len(game.state.events)
        game.apply(next(a for a in casts(game) if any(r.id == bear for r in a.targets)))
        assert mountains_tapped_since(game, mark) == 3, "{R} and {2} -- three Mountains"

    def test_its_own_controller_is_not_taxed(self, builder):
        """"Spells your **opponents** cast."""
        game = board(builder)
        assert tax(game, only_oid(game, BEAR, 0), pid=0) == 0


class TestTheLoader:
    def _card(self, cost: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_taxer",
                "name": "Test Taxer",
                "mana_cost": "{2}",
                "types": ["Enchantment"],
                "oracle_text": "Spells your opponents cast cost {2} more to cast.",
                "abilities": [
                    {
                        "kind": "static",
                        "text": "Spells your opponents cast cost {2} more to cast.",
                        "effect": "spell_cost_increase",
                        "affects_spells": {"controller": "opponent"},
                        "cost": cost,
                    }
                ],
            }
        )

    def test_generic_mana_loads(self):
        compile_card(self._card({"mana": "{2}"}))

    def test_a_coloured_surcharge_is_refused(self):
        with pytest.raises(DslError, match="generic"):
            compile_card(self._card({"mana": "{U}"}))

    def test_nothing_more_is_refused(self):
        with pytest.raises(DslError, match="generic"):
            compile_card(self._card({"mana": "{0}"}))

    def test_life_and_mana_together_are_refused(self):
        with pytest.raises(DslError, match="spell_cost_increase"):
            compile_card(self._card({"mana": "{2}", "pay_life": 2}))
