"""A static sized by the unspent mana in a player's pool.

    "Omnath gets +1/+1 for each unspent mana you have."
                                            -- Omnath, Locus of the Void

A static's magnitude is read continuously (611.3a), so the creature is bigger
the instant mana lands in the pool and smaller the instant it is spent or
emptied. `{"unspent_mana_count": spec}` is the leaf: the total mana in the
named players' pools, restricted pips included, since "unspent" is not
"spendable on this".

Two things the tests below pin, each invisible on screen:

- **It follows the pool.** `chars` is cached per `char_version`, and none of
  the pool's funnels -- a mana ability, a payment out of floating mana, an
  `add_mana` effect, the step boundary emptying the pool -- bumped it, so the
  creature kept a stale size until something unrelated invalidated the cache.
  Every funnel bumps, as `primitives.add_poison` does for corrupted.
- **It stays acyclic** (ADR 0001). The pool is player state, a pipeline input:
  only adding, spending and emptying mana write it, and no layer of
  `characteristics` can. So the anthem cannot come to depend on another
  static's output.

Omnath, Locus of the Void is the shipped witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, pay_mana
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_mana import op_add_mana
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import ManaCost, compile_restriction
from commanderblitz.engine.turn import advance
from tests.conftest import oids_of, only_oid, pt

GROWER = "t_unspent_grower"  # 1/1, +1/+1 for each unspent mana you have
STONE = "t_colorless_stone"  # "...that mana becomes colorless instead."


def position(builder, mine=(GROWER,), theirs=()):
    """Player 0 in their precombat main phase with a Forest and ``mine``."""
    return (
        builder(players=2)
        .battlefield(0, ["forest", *mine])
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def add(game, mana: str, pid: int = 0) -> None:
    """Through the `add_mana` op, the way a resolving landfall trigger adds."""
    ctx = EffectContext(state=game.state, controller=pid)
    op_add_mana(ctx, {"op": "add_mana", "mana": mana, "player": "you"})


def tap_forest(game) -> None:
    forest = next(
        oid for oid in oids_of(game, "forest", 0) if game.state.objects[oid].on_battlefield
    )
    activate_mana_ability(game.state, forest, 0, 0)


class TestItFollowsThePool:
    def test_an_empty_pool_is_the_printed_size(self, builder):
        game = position(builder)
        assert pt(game, only_oid(game, GROWER)) == (1, 1)

    def test_an_add_mana_effect_grows_it(self, builder):
        game = position(builder)
        grower = only_oid(game, GROWER)
        pt(game, grower)  # warm the cache
        add(game, "{C}{C}")
        assert pt(game, grower) == (3, 3)

    def test_tapping_for_mana_grows_it(self, builder):
        game = position(builder)
        grower = only_oid(game, GROWER)
        pt(game, grower)
        tap_forest(game)
        assert pt(game, grower) == (2, 2)

    def test_spending_floating_mana_shrinks_it(self, builder):
        """A payment out of the pool taps nothing, so nothing else bumps."""
        game = position(builder)
        grower = only_oid(game, GROWER)
        add(game, "{C}{C}{C}")
        assert pt(game, grower) == (4, 4)
        assert pay_mana(game.state, 0, ManaCost.parse("{2}").with_x(0))
        assert pt(game, grower) == (2, 2)

    def test_the_step_boundary_empties_it(self, builder):
        game = position(builder)
        grower = only_oid(game, GROWER)
        add(game, "{G}{G}")
        assert pt(game, grower) == (3, 3)
        advance(game.state)
        assert pt(game, grower) == (1, 1)

    def test_kept_as_colorless_it_stays_the_size(self, builder):
        """Beside `mana_becomes_colorless` -- Omnath's own second line."""
        game = position(builder, mine=(GROWER, STONE))
        grower = only_oid(game, GROWER)
        add(game, "{G}{G}")
        advance(game.state)
        assert pt(game, grower) == (3, 3)

    def test_restricted_mana_is_still_unspent_mana(self, builder):
        game = position(builder)
        grower = only_oid(game, GROWER)
        pt(game, grower)
        game.state.players[0].mana_pool.add(
            "G", 2, restriction=compile_restriction(["creature"], "t")
        )
        game.state.bump_chars()  # written straight onto the pool
        assert pt(game, grower) == (3, 3)


class TestWhosePool:
    def test_you_is_its_controllers_pool(self, builder):
        game = position(builder)
        grower = only_oid(game, GROWER)
        pt(game, grower)
        add(game, "{R}{R}", pid=1)
        assert pt(game, grower) == (1, 1)

    def test_the_effect_side_reads_the_same_pool(self, builder):
        game = position(builder)
        add(game, "{U}{C}")
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"unspent_mana_count": "you"}) == 2
        assert evaluate_value(ctx, {"unspent_mana_count": "each_opponent"}) == 0


class TestTheLoader:
    def _card(self, amount):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "X gets +1/+1 for each unspent mana you have.",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "static",
                        "text": "X gets +1/+1 for each unspent mana you have.",
                        "effect": "buff",
                        "affects": {"self_only": True},
                        "power": amount,
                        "toughness": amount,
                    }
                ],
            }
        )

    def test_a_well_formed_static_loads(self):
        compile_card(self._card({"unspent_mana_count": "you"}))

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError, match="unspent_mana_count"):
            compile_card(self._card({"unspent_mana_count": "active_player"}))

    def test_the_effect_side_refuses_a_non_spec(self):
        with pytest.raises(DslError, match="unspent_mana_count"):
            validate_value({"unspent_mana_count": 3}, "v")
