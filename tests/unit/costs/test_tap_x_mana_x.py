"""One announced X sizing both "{X}" and "Tap X untapped artifacts" (601.2b, 601.2g-h).

    Necron Overlord: "Relentless March -- {X}, {T}, Tap X untapped artifacts
    you control: Target opponent loses X life."

107.3 and 601.2b announce X once, and every X in the cost is that number: the
ability costs X generic mana *and* X untapped artifacts. A cost is paid only by
paying all of it (601.2h), and its mana abilities are activated while paying it
(601.2g), so the two halves draw on one board -- a Sol Ring tapped for the
{X} is no longer an untapped artifact to tap for the rest. X can therefore be
no more than the largest number both halves can meet *together*, which is less
than either bound alone whenever the artifacts are also the mana.

Without this, the loader refused an `{X}` in `mana` beside `tap_x` (one X per
ability), and neither `tap_x` alone (no mana) nor `{X}` with a fixed
`tap_permanents` count said the printed cost. `costs.cost_x_ceiling` now
bounds a `tap_x` with a mana half by `_tap_x_joint_ceiling`, `can_pay` asks
`tap_x_payable`, and `pay` pays the mana from sources that leave X of the pool
untapped, spending as few of the pool on mana as it can.

Witness: Necron Overlord. `t_txm_overlord` is its ability.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, find_action, oids_of, only_oid, settle

OVERLORD = "t_txm_overlord"
ROD = "ornithopter"  # an artifact that makes no mana
RING = "sol_ring"  # an artifact that does


def position(builder, mine=(), *, lands: int = 0):
    game = (
        builder(players=2)
        .battlefield(0, [OVERLORD, *mine] + ["wastes"] * lands)
        # A land to play keeps the main phase from passing itself.
        .hand(0, ["wastes"])
        .library(0, ["wastes"] * 20)
        .library(1, ["wastes"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, OVERLORD, 0)


def activate(game, oid) -> None:
    game.apply(activations(game, oid)[0])


def max_x(game) -> int:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_X, decision.kind
    return decision.context["max_x"]


def choose_x(game, x: int) -> None:
    assert game.pending().kind is DecisionKind.CHOOSE_X
    game.apply(find_action(game, ActionKind.CHOOSE, choice=x))


def tap_these(game, oids) -> None:
    """Answer the cost's pick with exactly these permanents; a forced pick asks nothing."""
    decision = game.pending()
    if decision.kind is not DecisionKind.CHOOSE_OBJECTS:
        return
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(find_action(game, ActionKind.CHOOSE, choice=index))
    if game.pending() is decision:
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def tapped(game, card_id: str) -> list[int]:
    return [oid for oid in oids_of(game, card_id, 0) if game.state.objects[oid].tapped]


def life(game, pid: int = 1) -> int:
    return game.state.players[pid].life


class TestBothHalvesBoundX:
    def test_the_artifacts_bound_it_when_mana_is_plentiful(self, builder):
        """Three Ornithopters and five lands: three, not five -- and not four,
        since the Overlord taps for its own {T}."""
        game, overlord = position(builder, (ROD,) * 3, lands=5)
        activate(game, overlord)
        assert max_x(game) == 3

    def test_the_mana_bounds_it_when_artifacts_are_plentiful(self, builder):
        game, overlord = position(builder, (ROD,) * 3, lands=1)
        activate(game, overlord)
        assert max_x(game) == 1

    def test_a_rock_tapped_for_mana_is_not_an_artifact_left_to_tap(self, builder):
        """Two Sol Rings and nothing else: four mana and two artifacts, but X = 2
        would tap a Ring for the {2} and leave one artifact. One is the most."""
        game, overlord = position(builder, (RING,) * 2)
        activate(game, overlord)
        assert max_x(game) == 1


class TestPayingIt:
    @pytest.mark.parametrize("x", [1, 3])
    def test_x_mana_and_x_artifacts_are_paid_and_the_effect_reads_x(self, builder, x):
        """Parametrised because a constant passes any single case."""
        game, overlord = position(builder, (ROD,) * 3, lands=3)
        before = life(game)
        rods = oids_of(game, ROD, 0)[:x]
        activate(game, overlord)
        choose_x(game, x)
        tap_these(game, rods)
        assert sorted(tapped(game, ROD)) == sorted(rods)
        assert len(tapped(game, "wastes")) == x
        assert game.state.objects[overlord].tapped
        settle(game)
        assert life(game) == before - x

    def test_the_mana_is_paid_from_lands_so_the_rocks_stay_to_be_tapped(self, builder):
        """Two Sol Rings and two lands at X = 2: payable only if the lands pay
        the {2} and both Rings are tapped for the cost, and so it is paid."""
        game, overlord = position(builder, (RING,) * 2, lands=2)
        before = life(game)
        activate(game, overlord)
        assert max_x(game) == 2
        choose_x(game, 2)
        tap_these(game, oids_of(game, RING, 0))
        assert len(tapped(game, RING)) == 2
        assert len(tapped(game, "wastes")) == 2
        assert game.state.players[0].mana_pool.total() == 0
        settle(game)
        assert life(game) == before - 2

    def test_a_rock_pays_and_the_other_is_tapped(self, builder):
        game, overlord = position(builder, (RING,) * 2)
        before = life(game)
        activate(game, overlord)
        choose_x(game, 1)
        tap_these(game, oids_of(game, RING, 0))
        assert len(tapped(game, RING)) == 2
        settle(game)
        assert life(game) == before - 1

    def test_x_can_be_zero(self, builder):
        """107.3: zero is a legal announcement -- no artifact, no mana, only {T}."""
        game, overlord = position(builder)
        before = life(game)
        activate(game, overlord)
        assert game.pending().kind is not DecisionKind.CHOOSE_X
        assert game.state.objects[overlord].tapped
        settle(game)
        assert life(game) == before


class TestTheLoaderChecksIt:
    def _card(self, cost: dict) -> CardModel:
        text = "{X}, {T}, Tap X untapped artifacts you control: You gain X life."
        return CardModel.model_validate(
            {
                "id": "t_txm_bad",
                "name": "Test Bad Tap X Mana X",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "oracle_text": text,
                "abilities": [
                    {
                        "kind": "activated",
                        "text": text,
                        "cost": cost,
                        "effects": [
                            {"op": "gain_life", "player": "you", "amount": {"x": True}}
                        ],
                    }
                ],
            }
        )

    def test_an_x_in_mana_is_the_same_x(self, registry):
        compile_card(self._card({"mana": "{X}", "tap": True, "tap_x": {"types": ["Artifact"]}}))
        assert registry.get(OVERLORD).abilities[0].cost.describe() == (
            "{X}, {T}, Tap X untapped permanents"
        )

    @pytest.mark.parametrize("extra", [{"x_minimum": 1}, {"x_value": {"count": {"types": ["Artifact"]}}}])
    def test_the_announced_x_is_neither_floored_nor_defined(self, extra):
        with pytest.raises(DslError, match="'x_value' or 'x_minimum'"):
            compile_card(
                self._card({"mana": "{X}", "tap_x": {"types": ["Artifact"]}, **extra})
            )
