"""A price that reads the turn's dead: "{1} less for each creature that died this turn".

Blood for the Blood God! -- "This spell costs {1} less to cast for each
creature that died this turn." -- is the witness. The reduction is generic only
(601.2f), counts every creature that died this turn whoever controlled it, tokens
included (a token dies, 700.4, before state-based actions sweep it), and is
priced from the turn ledger, `TurnLedger.creatures_died`, the tally the
`creatures_died_this_turn` value leaf reads.

`count` is the near miss and cannot say it: its filter walks a battlefield, and
the dead are no longer on it. So the card-level `cost_reduction` gained the
ledger head `creatures_died_this_turn`, taking a player spec as its sibling
`energy_spent_this_turn` does.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.zones import destroy
from tests.conftest import cost_reduction_probe

BLOOD = "t_crd_blood"  # {6}{B}{R}, {1} less per creature that died this turn
BEAR = "t_eb_bear"
SCION = "eldrazi_scion_1_1_c"


def position(builder, *, bears: int = 3, lands=("swamp", "mountain")):
    """Player 0's precombat main phase, frozen: ``bears`` Bears each side,
    ``lands`` and the spell in hand. Frozen because with nothing castable the
    auto-pass would roll the turn on before a Bear could die."""
    b = (
        builder(players=2)
        .battlefield(0, list(lands) + [BEAR] * bears)
        .battlefield(1, [BEAR] * bears)
        .hand(0, [BLOOD])
    )
    for pid in range(2):
        b.library(pid, ["swamp"] * 20)
    return b.active(0).step(Step.PRECOMBAT_MAIN).build(advance=False)


def bears_of(game, pid: int) -> list[int]:
    return [
        oid
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == BEAR and game.state.objects[oid].controller == pid
    ]


def kill(game, pid: int, n: int) -> None:
    for oid in bears_of(game, pid)[:n]:
        destroy(game.state, oid, cause="test")


def can_cast(game) -> bool:
    """Hand player 0 priority in the main phase, as `build` would, and ask."""
    game._advance()
    if game.state.step is not Step.PRECOMBAT_MAIN:
        return False  # the auto-pass found nothing to do, the spell included
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BLOOD
        for a in game.legal_actions()
    )


class TestTheDiscount:
    def test_nothing_died_nothing_off(self, registry, builder):
        game = position(builder)
        assert cost_reduction(game.state, 0, registry.get(BLOOD)) == 0

    def test_one_per_death(self, registry, builder):
        game = position(builder)
        kill(game, 0, 2)
        assert cost_reduction(game.state, 0, registry.get(BLOOD)) == 2

    def test_any_controllers_creature_counts(self, registry, builder):
        """"Each creature that died" -- the opponent's dead discount it too."""
        game = position(builder)
        kill(game, 0, 1)
        kill(game, 1, 2)
        assert cost_reduction(game.state, 0, registry.get(BLOOD)) == 3

    def test_a_token_that_died_counts(self, registry, builder):
        game = position(builder)
        (scion,) = create_token(game.state, SCION, 1)
        destroy(game.state, scion, cause="test")
        assert cost_reduction(game.state, 0, registry.get(BLOOD)) == 1

    def test_it_wears_off_with_the_turn(self, registry, builder):
        game = position(builder)
        kill(game, 1, 3)
        game.state.turn_ledger.clear()
        assert cost_reduction(game.state, 0, registry.get(BLOOD)) == 0


class TestGenericOnly:
    def test_five_dead_is_not_enough_on_two_lands(self, builder):
        """{6}{B}{R} minus five is {1}{B}{R}: a Swamp and a Mountain cannot."""
        game = position(builder)
        kill(game, 0, 3)
        kill(game, 1, 2)
        assert not can_cast(game)

    def test_six_dead_casts_it_for_the_pips(self, builder):
        game = position(builder)
        kill(game, 0, 3)
        kill(game, 1, 3)
        assert can_cast(game)

    def test_more_dead_than_generic_still_needs_both_pips(self, builder):
        """Eight dead take off six, never the {B}: a lone Mountain cannot."""
        game = position(builder, bears=4, lands=("mountain",))
        kill(game, 0, 4)
        kill(game, 1, 4)
        assert not can_cast(game)


class TestLoading:
    def test_the_printed_shape_loads(self):
        card = compile_card(cost_reduction_probe({"creatures_died_this_turn": "all"}))
        assert card.cost_reduction == {"creatures_died_this_turn": "all"}

    @pytest.mark.parametrize("bad", ["nobody", 3, None])
    def test_it_needs_a_player_spec(self, bad):
        with pytest.raises(DslError, match="creatures_died_this_turn"):
            compile_card(cost_reduction_probe({"creatures_died_this_turn": bad}))

    def test_it_refuses_a_second_head(self):
        with pytest.raises(DslError):
            compile_card(
                cost_reduction_probe({"creatures_died_this_turn": "all", "count": {}})
            )

