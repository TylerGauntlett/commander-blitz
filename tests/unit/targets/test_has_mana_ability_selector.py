"""``has_mana_ability`` — whether an object has a mana ability right now.

    Midnight Arsonist — "When this creature enters, destroy up to X target
    artifacts **without mana abilities**, where X is the number of Vampires
    you control."

605.1a: an activated ability is a mana ability when it could add mana, needs
no target and is not a loyalty ability. The question is about the abilities
the object *has*, so a mana ability another permanent grants counts, as Citanul
Hierophants' "Creatures you control have '{T}: Add {G}.'" does, and a land's
intrinsic 305.6 ability counts too.

Without the key the line could not be said at all: `not_keywords` is the near
miss and a mana ability is not a keyword, and `any_mana_ability` lives only on
a mana-ability rider's `tapped_permanent`. Writing the card without the clause
would let Midnight Arsonist destroy Sol Ring, which the printed card cannot.

The selector reads `characteristics.abilities_of`, the one function that says
which abilities an object has, so it cannot disagree with what the player can
activate.

Witness: Midnight Arsonist (`midnight_arsonist` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool, validate_selector
from commanderblitz.engine.errors import DslError

SOL_RING = "sol_ring"  # {T}: Add {C}{C}.
MINE = "howling_mine"  # no activated ability at all
BEAR = "t_bear"  # 2/2 vanilla
HIEROPHANTS = "citanul_hierophants"  # Creatures you control have "{T}: Add {G}."
FOREST = "forest"

ARTIFACTS_WITHOUT = {
    "zone": "battlefield",
    "types": ["Artifact"],
    "has_mana_ability": False,
    "count": "all",
}


def board(builder, mine=(SOL_RING, MINE, BEAR)):
    return (
        builder(players=2)
        .battlefield(0, [FOREST, *mine])
        .battlefield(1, [FOREST])
        .build()
    )


def ctx(game, controller: int = 0) -> EffectContext:
    return EffectContext(state=game.state, controller=controller, source_oid=None)


def pool(game, selector) -> set[str]:
    state = game.state
    return {state.card_of(state.objects[o]).id for o in resolve_pool(ctx(game), selector)}


class TestArtifactsWithoutManaAbilities:
    def test_the_mine_is_gathered_and_the_ring_is_not(self, builder):
        assert pool(board(builder), ARTIFACTS_WITHOUT) == {MINE}

    def test_true_gathers_the_ring(self, builder):
        selector = {**ARTIFACTS_WITHOUT, "has_mana_ability": True}
        assert pool(board(builder), selector) == {SOL_RING}


class TestItReadsTheAbilitiesTheObjectHas:
    def test_a_land_has_its_intrinsic_mana_ability(self, builder):
        selector = {"zone": "battlefield", "types": ["Land"], "has_mana_ability": True, "count": "all"}
        assert pool(board(builder), selector) == {FOREST}

    def test_a_vanilla_creature_has_none(self, builder):
        selector = {"zone": "battlefield", "types": ["Creature"], "has_mana_ability": False, "count": "all"}
        assert pool(board(builder), selector) == {BEAR}

    def test_a_granted_mana_ability_counts(self, builder):
        game = board(builder, mine=(BEAR, HIEROPHANTS))
        selector = {"zone": "battlefield", "types": ["Creature"], "has_mana_ability": False, "count": "all"}
        assert pool(game, selector) == set()


class TestLoadTime:
    def test_a_bool_is_accepted(self):
        validate_selector({"has_mana_ability": False}, "t")

    def test_anything_else_is_refused(self):
        with pytest.raises(DslError, match="has_mana_ability"):
            validate_selector({"has_mana_ability": "no"}, "t")
