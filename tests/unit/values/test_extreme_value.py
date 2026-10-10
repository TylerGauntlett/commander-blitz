"""Edgar, Master Machinist — "the **greatest** mana value among artifacts you control".

    Tools — Whenever Edgar attacks, it gets +X/+0 until end of turn, where X is
    the greatest mana value among artifacts you control.

A single number off a pool, and neither existing piece gives one:

- `mana_value_of` with an `objects` ref **sums** over the pool (`_characteristic`),
  which is a different number entirely on any board with more than one artifact.
- the `extreme` **selector** key deliberately keeps *every* object tied for the
  extremum, so `choose_objects` can break the tie -- which is right for "target
  creature with the least toughness" and wrong here.

Composing the two is the trap, and it is silent: `mana_value_of` over an
`extreme`-narrowed pool reads 2X when two artifacts tie for greatest and 3X when
three do. Nothing about the card looks wrong; Edgar is just bigger than he
prints, on an ordinary board, some of the time.

The fixture board ties on purpose — Mind Stone and 2 Mace are both mana value 2 —
because a board with a unique maximum is exactly the board where the bug hides.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value

ARTIFACTS = {"zone": "battlefield", "controller": "you", "types": ["Artifact"]}


def board(builder, cards):
    return builder(players=2).battlefield(0, cards).build(advance=False)


def value(game, expr, controller: int = 0):
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def extreme(game, pick: str = "greatest", of: str = "mana_value"):
    return value(
        game, {"extreme_value": {"of": of, "pick": pick, "objects": ARTIFACTS}}
    )


class TestItPicksOneNumber:
    def test_the_greatest(self, builder):
        game = board(builder, ["sol_ring", "mind_stone", "2_mace"])
        assert extreme(game) == 2

    def test_the_least(self, builder):
        game = board(builder, ["sol_ring", "mind_stone", "2_mace"])
        assert extreme(game, pick="least") == 1

    def test_a_single_artifact_is_its_own_extreme(self, builder):
        game = board(builder, ["sol_ring"])
        assert extreme(game) == 1

    def test_an_empty_pool_is_zero(self, builder):
        """No artifacts is +0/+0, not an error -- as every pool value here reads."""
        game = board(builder, ["forest"])
        assert extreme(game) == 0


class TestItIsNotTheSum:
    """The near miss, measured on a board where the two disagree."""

    def test_summing_reads_something_else_entirely(self, builder):
        game = board(builder, ["sol_ring", "mind_stone", "2_mace"])
        assert value(game, {"mana_value_of": {"objects": ARTIFACTS}}) == 5
        assert extreme(game) == 2

    def test_a_tie_does_not_double_it(self, builder):
        """Two artifacts tied for greatest, and the answer is still one of them.

        This is the case the `extreme` selector plus `mana_value_of` gets wrong:
        the selector keeps both tied objects on purpose, and the sum then reads
        4 rather than 2.
        """
        game = board(builder, ["mind_stone", "2_mace"])
        assert extreme(game) == 2
        assert value(game, {"mana_value_of": {"objects": ARTIFACTS}}) == 4


class TestItReadsOtherCharacteristics:
    def test_greatest_power(self, builder):
        game = builder(players=2).battlefield(0, ["t_bear", "t_dork"]).build(
            advance=False
        )
        pool = {"zone": "battlefield", "controller": "you", "types": ["Creature"]}
        best = value(
            game, {"extreme_value": {"of": "power", "pick": "greatest", "objects": pool}}
        )
        least = value(
            game, {"extreme_value": {"of": "power", "pick": "least", "objects": pool}}
        )
        assert best > least


class TestTheLoaderKnowsTheKey:
    def test_it_validates(self):
        from commanderblitz.engine.effects.values import validate_value

        validate_value(
            {"extreme_value": {"of": "mana_value", "pick": "greatest", "objects": ARTIFACTS}},
            "test",
        )

    def test_an_unknown_value_key_is_still_refused(self):
        from commanderblitz.engine.effects.values import validate_value
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="unknown value keys"):
            validate_value({"extremest_value": {}}, "test")
