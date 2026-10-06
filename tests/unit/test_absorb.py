"""Absorb — damage prevention with a number on it.

    "Absorb 2 (If a source would deal damage to this creature, prevent 2 of that
    damage.)"

The census filed absorb as blocked: "damage prevention, which the engine models
only as protection". Protection is the near miss and is a strictly different
card in **four** ways, only one of which is about damage — it prevents *all* of
it, and it also stops the creature being blocked, enchanted and targeted. An
absorb creature written as protection is unblockable and untargetable, which is
not a smaller version of the card but a much bigger one.

So it is its own static, parameterised on N, which is why it cannot be a
`Keyword` either — the census's own routing rule, a quality with a parameter.

The clause that decides everything is "**a source**". Prevention is per source
and per instance, not a pool that drains: a creature with absorb 1 blocked by
three 1/1s takes nothing from any of them, and the same creature hit by one 3/3
takes two. That is the whole reason absorb 1 is printable, and a running total
would make it a one-shot.

Prevented damage was **never dealt**, so it happens before everything the damage
pipeline does afterwards: no deathtouch mark, no lifelink, no entry in the
damage ledger, and a `DAMAGE_DEALT` event carrying the reduced number rather
than the printed one.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_permanent
from tests.conftest import only_oid

WALL = "t_absorber"        # 1/4, absorb 2
BEAR = "t_bear"            # 2/2
DEATHTOUCHER = "t_deathtoucher"


def board(builder, *others: str):
    game = (
        builder(players=2)
        .battlefield(0, [WALL])
        .battlefield(1, list(others))
        .build(advance=False)
    )
    return game, only_oid(game, WALL)


class TestHowMuchIsPrevented:
    def test_damage_below_the_number_is_prevented_entirely(self, builder):
        game, wall = board(builder)
        assert damage_permanent(game.state, wall, 1, None) == 0
        assert game.state.objects[wall].damage == 0

    def test_damage_equal_to_it_is_prevented_entirely(self, builder):
        game, wall = board(builder)
        assert damage_permanent(game.state, wall, 2, None) == 0
        assert game.state.objects[wall].damage == 0

    def test_the_excess_gets_through(self, builder):
        game, wall = board(builder)
        assert damage_permanent(game.state, wall, 5, None) == 3
        assert game.state.objects[wall].damage == 3

    def test_a_creature_without_it_takes_everything(self, builder):
        game, _ = board(builder, BEAR)
        bear = only_oid(game, BEAR, 1)
        damage_permanent(game.state, bear, 2, None)
        assert game.state.objects[bear].damage == 2


class TestItIsPerSource:
    def test_three_small_hits_are_each_prevented(self, builder):
        """The clause that makes absorb 1 printable. A pool would let the third through."""
        game, wall = board(builder)
        for _ in range(3):
            damage_permanent(game.state, wall, 2, None)

        assert game.state.objects[wall].damage == 0

    def test_a_single_large_hit_is_reduced_once(self, builder):
        game, wall = board(builder)
        damage_permanent(game.state, wall, 3, None)
        damage_permanent(game.state, wall, 3, None)

        assert game.state.objects[wall].damage == 2, "one through each time"


class TestWhatPreventedDamageDoesNotDo:
    def test_it_marks_no_deathtouch(self, builder):
        """Prevented damage was never dealt, so nothing downstream should see it."""
        game, wall = board(builder, DEATHTOUCHER)
        killer = only_oid(game, DEATHTOUCHER, 1)

        damage_permanent(game.state, wall, 1, killer, is_combat=True)

        assert game.state.objects[wall].deathtouched is False

    def test_it_writes_no_damage_ledger_entry(self, builder):
        game, wall = board(builder, BEAR)
        bear = only_oid(game, BEAR, 1)

        damage_permanent(game.state, wall, 2, bear, is_combat=True)

        assert bear not in game.state.damage_ledger.get(wall, set())

    def test_the_event_carries_the_reduced_number(self, builder):
        game, wall = board(builder)
        before = len(game.state.events)

        damage_permanent(game.state, wall, 5, None)

        dealt = [e for e in game.state.events[before:] if e.type == "damage_dealt"]
        prevented = [e for e in game.state.events[before:] if e.type == "damage_prevented"]
        assert [e.data["amount"] for e in dealt] == [3]
        assert [e.data["amount"] for e in prevented] == [2]

    def test_the_deathtouch_still_lands_on_the_excess(self, builder):
        """Only what was prevented is gone; the rest is ordinary damage."""
        game, wall = board(builder, DEATHTOUCHER)
        killer = only_oid(game, DEATHTOUCHER, 1)

        damage_permanent(game.state, wall, 3, killer, is_combat=True)

        assert game.state.objects[wall].deathtouched is True


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
                "id": "t_absorb_probe",
                "name": "Absorb Probe",
                "mana_cost": "{2}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [base],
            }
        )

    def test_a_well_formed_static_loads(self):
        compile_card(self._card(amount={"const": 2}))

    def test_omitting_the_amount_is_refused(self):
        """Absorb 0 prevents nothing and would appear in the card's text anyway."""
        with pytest.raises(DslError, match="prevent_damage' needs an 'amount'"):
            compile_card(self._card())
