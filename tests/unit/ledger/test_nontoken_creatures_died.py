"""`nontoken_creatures_died_this_turn` -- the deaths that were not tokens.

"At the beginning of your end step, create a Treasure token for each
**nontoken** creature that died this turn" (Gadrak, the Crown-Scourge); "create
an X/X... where X is the number of **nontoken** creatures that died this turn"
(Vile Redeemer). `creatures_died_this_turn` counts a dead Scion as readily as a
dead commander, so a board of chump-blocking tokens would pay out for every
one of them -- a strictly better card than printed.

`GameState._tally` adds the death to `TurnLedger.nontoken_creatures_died`
beside `creatures_died`, keyed by the controller it died under. The token is
still an object when DIES fires (state-based actions sweep it later, 704.5d),
so its flag is read there.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid

BEAR = "t_eb_bear"
SCION = "eldrazi_scion_1_1_c"


def position(builder):
    b = builder(players=2).battlefield(0, [BEAR]).battlefield(1, [BEAR])
    for pid in range(2):
        b.library(pid, ["swamp"] * 20)
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)
    (scion,) = create_token(game.state, SCION, 0)
    return game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1), scion


def died(game, spec="all", controller=0) -> int:
    ctx = EffectContext(game.state, controller=controller, source_oid=None)
    return evaluate_value(ctx, {"nontoken_creatures_died_this_turn": spec})


class TestTokensAreNotCounted:
    def test_a_nontoken_creature_counts(self, builder):
        game, bear, _, _ = position(builder)
        destroy(game.state, bear, cause="test")
        assert died(game) == 1

    def test_a_token_creature_does_not(self, builder):
        """The whole point: `creatures_died_this_turn` counts it."""
        game, _, _, scion = position(builder)
        destroy(game.state, scion, cause="test")
        assert died(game) == 0
        ctx = EffectContext(game.state, controller=0, source_oid=None)
        assert evaluate_value(ctx, {"creatures_died_this_turn": "all"}) == 1


class TestWhoseDeaths:
    @pytest.mark.parametrize(("spec", "expected"), [("all", 2), ("you", 1), ("opponent", 1)])
    def test_it_sums_over_the_named_players(self, builder, spec, expected):
        game, mine, theirs, scion = position(builder)
        for oid in (mine, theirs, scion):
            destroy(game.state, oid, cause="test")
        assert died(game, spec) == expected

    def test_it_wears_off_with_the_turn(self, builder):
        game, bear, _, _ = position(builder)
        destroy(game.state, bear, cause="test")
        game.state.turn_ledger.clear()
        assert died(game) == 0


def test_a_non_player_spec_is_refused():
    from commanderblitz.engine.effects.values import validate_value

    with pytest.raises(DslError, match="player spec"):
        validate_value({"nontoken_creatures_died_this_turn": 3}, "test")
