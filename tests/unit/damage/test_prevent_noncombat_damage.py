"""A static shield over **noncombat** damage -- `noncombat_only` on the
`prevent_damage` static.

    Crystal Barricade -- "Prevent all noncombat damage that would be dealt to
    other creatures you control."
    Drogskol Reinforcements -- "Prevent all noncombat damage that would be
    dealt to Spirits you control."

615.1 with 510.2: a prevention effect answers exactly the damage it names, and
combat damage is the damage the combat damage step deals. "Noncombat" is all the
rest -- burn, a fight (701.12), a dying token's ping.

The near misses are each a different card. Plain `prevent_all` also stops
combat damage, so a Barricade written that way makes every creature you control
an unkillable blocker: a strictly better card that loads clean. `combat_only`
is the exact opposite card (Seraph of the Sword). `protection` stops blocking
and targeting too.

What is pinned below:

1. Noncombat damage to a matching permanent is prevented, through
   `damage_permanent` and through a real fight, and fires `DAMAGE_PREVENTED`.
2. Combat damage to the same permanent lands in full.
3. The filter still narrows: "other" leaves the source exposed, and an
   opponent's creature is not shielded.
4. The flag narrows the absorb form the same way.
5. The loader refuses it beside `combat_only` and on any other static.

Witnesses: Crystal Barricade and Drogskol Reinforcements (`data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import (
    prevented_damage,
    prevention_reaches,
    prevents_all_damage,
)
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent
from tests.conftest import only_oid, two_seat_board

BARRICADE = "t_noncombat_barricade"  # prevent all noncombat damage to OTHER creatures you control
ABSORBER = "t_noncombat_absorber"  # absorb 2, noncombat damage only, itself
BEAR = "t_bear"


def position(builder, mine=(BARRICADE, BEAR), theirs=(BEAR,)):
    """Returns ``(game, my_bear, their_bear)``."""
    game = two_seat_board(builder, mine=list(mine), theirs=list(theirs), advance=False)
    return game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)


def prevented(game) -> list:
    return [e for e in game.state.events if e.type == "damage_prevented"]


class TestNoncombatDamageIsPrevented:
    def test_burn_to_another_creature_you_control_is_prevented(self, builder):
        game, mine, _ = position(builder)

        assert damage_permanent(game.state, mine, 5, None) == 0
        assert game.state.objects[mine].damage == 0

    def test_it_fires_damage_prevented(self, builder):
        game, mine, _ = position(builder)

        damage_permanent(game.state, mine, 3, None)

        assert [e.data.get("amount") for e in prevented(game)] == [3]

    def test_a_fight_is_noncombat_damage(self, builder):
        """701.12: fight damage is dealt by the creatures, outside combat."""
        game, mine, theirs = position(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        ctx.bindings.update(a=[mine], b=[theirs])
        spec = {"op": "fight", "objects": {"binding": "a"}, "other": {"binding": "b"}}
        for _ in execute_one(ctx, spec):  # pragma: no cover - it asks nothing
            raise AssertionError("fight asked a decision")

        assert game.state.objects[mine].damage == 0
        assert game.state.objects[theirs].damage == 2


class TestCombatDamageLands:
    def test_combat_damage_to_the_same_creature_is_dealt(self, builder):
        game, mine, theirs = position(builder)

        assert damage_permanent(game.state, mine, 2, theirs, is_combat=True) == 2
        assert game.state.objects[mine].damage == 2

    def test_the_question_is_the_damage_kind(self, builder):
        game, mine, _ = position(builder)

        assert prevents_all_damage(game.state, mine, is_combat=False) is True
        assert prevents_all_damage(game.state, mine, is_combat=True) is False

    def test_the_three_shapes_of_the_clause(self):
        assert prevention_reaches({}, is_combat=True) is True
        assert prevention_reaches({}, is_combat=False) is True
        assert prevention_reaches({"combat_only": True}, is_combat=True) is True
        assert prevention_reaches({"combat_only": True}, is_combat=False) is False
        assert prevention_reaches({"noncombat_only": True}, is_combat=True) is False
        assert prevention_reaches({"noncombat_only": True}, is_combat=False) is True


class TestTheFilterStillNarrows:
    def test_it_does_not_shield_itself(self, builder):
        """"**Other** creatures you control" -- `exclude_self`."""
        game, _, _ = position(builder)
        barricade = only_oid(game, BARRICADE, 0)

        assert damage_permanent(game.state, barricade, 3, None) == 3

    def test_an_opponents_creature_is_not_shielded(self, builder):
        game, _, theirs = position(builder)

        assert damage_permanent(game.state, theirs, 2, None) == 2

    def test_without_the_source_burn_lands(self, builder):
        game, mine, _ = position(builder, mine=(BEAR,))

        assert damage_permanent(game.state, mine, 2, None) == 2


class TestTheAbsorbFormIsNarrowedToo:
    def test_noncombat_damage_loses_two(self, builder):
        game, _, _ = position(builder, mine=(ABSORBER, BEAR))
        absorber = only_oid(game, ABSORBER, 0)

        assert prevented_damage(game.state, absorber, is_combat=False) == 2
        assert damage_permanent(game.state, absorber, 3, None) == 1

    def test_combat_damage_loses_nothing(self, builder):
        game, _, theirs = position(builder, mine=(ABSORBER, BEAR))
        absorber = only_oid(game, ABSORBER, 0)

        assert prevented_damage(game.state, absorber, is_combat=True) == 0
        assert damage_permanent(game.state, absorber, 3, theirs, is_combat=True) == 3


class TestTheLoaderGuard:
    def _card(self, **static) -> CardModel:
        base = {"kind": "static", "effect": "prevent_damage", "affects": {"self_only": True}}
        base.update(static)
        return CardModel.model_validate(
            {
                "id": "t_noncombat_probe",
                "name": "Noncombat Probe",
                "mana_cost": "{2}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [base],
            }
        )

    def test_the_shield_loads(self):
        ability = compile_card(self._card(prevent_all=True, noncombat_only=True)).abilities[0]
        assert ability.static["noncombat_only"] is True

    def test_beside_combat_only_is_refused(self):
        """Together they name no damage at all."""
        with pytest.raises(DslError, match="not both"):
            compile_card(self._card(prevent_all=True, noncombat_only=True, combat_only=True))

    def test_on_another_static_is_refused(self):
        with pytest.raises(DslError, match="noncombat_only"):
            compile_card(
                self._card(effect="buff", power={"const": 1}, toughness={"const": 1},
                           noncombat_only=True)
            )
