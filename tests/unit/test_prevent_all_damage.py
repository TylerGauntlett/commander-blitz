"""A total damage shield — "prevent **all** damage", not absorb N.

    Rescue Retriever — "Prevent all damage that would be dealt to other
    attacking Soldiers you control."

`tests/unit/test_absorb.py` builds the numbered form and argues at length that
protection is the wrong near miss for it. This is the third point on that line,
and it is not a larger absorb.

**A big number is not "all", and 702.63a is why.** Absorb is per source and per
instance, so any finite N is a per-source cap the printed card never named: a
Soldier under absorb 2 is untouched by three 1/1 attackers and takes four from a
single 6/6, while the same Soldier under a total shield takes nothing from
either. `docs/rules-coverage.md` recorded "prevent all damage to a permanent" as
unimplemented for exactly this reason — the `prevent_damage` static refuses an
absent `amount` rather than reading it as infinite.

**It is not protection either**, which is the trap the absorb file already names:
protection prevents all the damage *and* stops the creature being blocked,
enchanted and targeted. A shielded attacking Soldier written as protection is
unblockable, which is three extra cards' worth of text on a card that printed
none of it.

So it is a bool beside the number rather than a value of it — `prevents_all_damage`
answers the whole event however big it is, the way `protected_from` does, and the
loader requires exactly one of `prevent_all` and `amount`.

**The two narrowing clauses are the card.** "**Other**" and "**attacking**" are
what stop this being a blanket Fog on your team: the Retriever does not shield
itself, and it shields nothing sitting at home. Both are pinned below, because a
version that dropped either would look identical on a board where everything
happens to be attacking.

Witness: Rescue Retriever (`rescue_retriever` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import prevented_damage, prevents_all_damage
from automtg.engine.primitives import damage_permanent
from tests.conftest import only_oid

RETRIEVER = "t_retriever"  # prevent all damage to OTHER ATTACKING Soldiers
BLANKET = "t_blanket_shield"  # the same with no `other`/`attacking` narrowing
SOLDIER = "t_soldier_plain"  # 2/3 Soldier for it to protect
BEAR = "t_bear"  # 2/2, not a Soldier


def board(builder, mine=(RETRIEVER, SOLDIER)):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, ["forest"])
        .build(advance=False)
    )


def attacking(game, *oids: int) -> None:
    """Mark these permanents as attacking, which is what the filter reads.

    The state is set directly rather than driven through a combat phase: the
    claim here is about the damage pipeline and the filter, and a real
    declaration would also have to survive blockers and first strike to reach
    the same call.
    """
    from automtg.engine.structs import CombatState

    game.state.combat = CombatState(attackers={oid: 1 for oid in oids})


class TestTheShieldIsTotal:
    def test_a_large_hit_is_prevented_entirely(self, builder):
        """The claim a number cannot make: six damage, none of it dealt."""
        game = board(builder)
        soldier = only_oid(game, SOLDIER, 0)
        attacking(game, soldier)
        assert damage_permanent(game.state, soldier, 6, None) == 0

    def test_and_so_is_a_small_one(self, builder):
        game = board(builder)
        soldier = only_oid(game, SOLDIER, 0)
        attacking(game, soldier)
        assert damage_permanent(game.state, soldier, 1, None) == 0

    def test_without_the_shield_it_takes_everything(self, builder):
        """Pins that the prevention is the static's and not the position's."""
        game = board(builder, mine=(SOLDIER,))
        soldier = only_oid(game, SOLDIER, 0)
        attacking(game, soldier)
        assert damage_permanent(game.state, soldier, 6, None) == 6

    def test_it_marks_the_permanent_with_no_damage(self, builder):
        """Prevented damage was never dealt, so nothing downstream sees it."""
        game = board(builder)
        soldier = only_oid(game, SOLDIER, 0)
        attacking(game, soldier)
        damage_permanent(game.state, soldier, 6, None)
        assert game.state.objects[soldier].damage == 0


class TestItIsNotAbsorbWithABigNumber:
    """The two rules answer differently, and `prevented_damage` is the witness.

    A total shield contributes **nothing** to the absorb sum, so the two cannot
    be conflated by a caller reading only the number.
    """

    def test_the_absorb_sum_stays_zero(self, builder):
        game = board(builder)
        soldier = only_oid(game, SOLDIER, 0)
        attacking(game, soldier)
        assert prevented_damage(game.state, soldier) == 0
        assert prevents_all_damage(game.state, soldier) is True

    def test_repeated_hits_are_each_prevented_in_full(self, builder):
        """Where absorb N is a per-source cap, this is not a pool that drains:
        three separate sources each deal nothing."""
        game = board(builder)
        soldier = only_oid(game, SOLDIER, 0)
        attacking(game, soldier)
        assert [damage_permanent(game.state, soldier, 5, None) for _ in range(3)] == [0, 0, 0]
        assert game.state.objects[soldier].damage == 0


class TestTheNarrowingClausesAreTheCard:
    def test_it_does_not_shield_itself(self, builder):
        """"**Other** attacking Soldiers" -- `exclude_self`. The Retriever is an
        attacking Soldier you control, so without the clause it would be immune
        to everything while attacking."""
        game = board(builder)
        retriever = only_oid(game, RETRIEVER, 0)
        attacking(game, retriever)
        assert prevents_all_damage(game.state, retriever) is False
        assert damage_permanent(game.state, retriever, 3, None) == 3

    def test_it_does_not_shield_a_soldier_sitting_at_home(self, builder):
        """"**Attacking**" -- a Soldier that did not attack is unprotected, which
        is most of what stops this being a one-sided Fog."""
        game = board(builder)
        soldier = only_oid(game, SOLDIER, 0)
        game.state.combat = None
        assert prevents_all_damage(game.state, soldier) is False
        assert damage_permanent(game.state, soldier, 3, None) == 3

    def test_it_does_not_shield_a_non_soldier(self, builder):
        game = board(builder, mine=(RETRIEVER, BEAR))
        bear = only_oid(game, BEAR, 0)
        attacking(game, bear)
        assert prevents_all_damage(game.state, bear) is False

    def test_the_unnarrowed_version_does_shield_all_three(self, builder):
        """The contrast that proves the clauses above are doing the narrowing
        rather than the static being inert."""
        game = board(builder, mine=(BLANKET, SOLDIER, BEAR))
        game.state.combat = None
        for card in (SOLDIER, BEAR):
            assert prevents_all_damage(game.state, only_oid(game, card, 0)) is True


class TestTheLoaderGuard:
    def _card(self, **static) -> CardModel:
        base = {
            "kind": "static",
            "effect": "prevent_damage",
            "affects": {"self_only": True},
        }
        base.update(static)
        return CardModel.model_validate(
            {
                "id": "t_prevent_all_probe",
                "name": "Prevent All Probe",
                "mana_cost": "{2}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [base],
            }
        )

    def test_the_total_shield_loads(self):
        compile_card(self._card(prevent_all=True))

    def test_the_numbered_form_still_loads(self):
        """Relaxing the `amount` requirement must not have removed it."""
        compile_card(self._card(amount={"const": 2}))

    def test_neither_is_refused(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(self._card())

    def test_both_together_are_refused(self):
        """Two answers to one question, with nothing to say which wins."""
        with pytest.raises(DslError, match="not both"):
            compile_card(self._card(prevent_all=True, amount={"const": 2}))

    def test_the_flag_on_another_static_is_refused(self):
        """A flag nothing reads is a printed line that does nothing."""
        with pytest.raises(DslError, match="read only by"):
            compile_card(
                self._card(effect="buff", power={"const": 1}, toughness={"const": 1},
                           prevent_all=True)
            )
