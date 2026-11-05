"""Moving any number of this creature's counters onto other creatures.

    "At the beginning of your upkeep, you may move any number of +1/+1
    counters from this creature onto other creatures."  -- Forgotten Ancient

Not the targeted division `distribute_counters` is. 601.2d announces a
division among **targets**, and 603.3d carries that announcement to a
trigger as it is put on the stack; Forgotten Ancient targets nothing, so there
is nothing to announce, and how many counters move and where they go are
choices made while the effect is applied (608.2d). Its ruling says so: the
counters and the creatures are chosen as the ability resolves.

`move_counters` puts one amount on every destination, so it cannot split
three counters two-and-one; a `repeat` of a one-counter move reaches the
split but places one counter at a time, so a Hardened Scales would add one per
counter rather than one per creature. `distribute_moved_counters` asks how
many (0 is the "may" declined), then each counter's creature, removes them
once and places each creature's share once.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid, pass_until, settle

ANCIENT = "t_dmc_ancient"
BEAR = "t_rc_bear"
SCALES = "t_rc_scales"


def position(builder, *, counters=3, mine=(BEAR, BEAR), theirs=(BEAR,), extra=()):
    """The Ancient with ``counters`` +1/+1 counters, our ``mine``, their ``theirs``,
    stopped at the start of our turn so the upkeep trigger is next."""
    game = (
        builder(players=2)
        .battlefield(0, [ANCIENT], counters={"+1/+1": counters} if counters else {})
        .battlefield(0, list(mine) + list(extra))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .step(Step.UNTAP)
        .active(0)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, ANCIENT, 0)


def to_how_many(game):
    pass_until(
        game,
        lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_X,
        limit=60,
    )
    return game.pending()


def answer_x(game, x: int) -> None:
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


def give_next_to(game, oid: int) -> None:
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_OBJECTS
    assert decision.context["purpose"] == "distribute"
    index = next(i for i, o in enumerate(decision.options) if o.value == oid)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


def plus(game, oid: int) -> int:
    return game.state.objects[oid].counter("+1/+1")


class TestTheSplit:
    def test_counters_split_unevenly_among_creatures_of_any_controller(self, builder):
        game, ancient = position(builder)
        mine = oids_of(game, BEAR, 0)
        theirs = only_oid(game, BEAR, 1)
        decision = to_how_many(game)
        assert decision.context["max_x"] == 3
        answer_x(game, 3)
        give_next_to(game, mine[0])
        give_next_to(game, mine[0])
        give_next_to(game, theirs)
        settle(game)
        assert plus(game, ancient) == 0
        assert (plus(game, mine[0]), plus(game, mine[1]), plus(game, theirs)) == (2, 0, 1)

    def test_some_counters_may_stay(self, builder):
        game, ancient = position(builder)
        bear = oids_of(game, BEAR, 0)[0]
        to_how_many(game)
        answer_x(game, 1)
        give_next_to(game, bear)
        settle(game)
        assert (plus(game, ancient), plus(game, bear)) == (2, 1)

    def test_zero_is_the_may_declined(self, builder):
        game, ancient = position(builder)
        to_how_many(game)
        answer_x(game, 0)
        settle(game)
        assert plus(game, ancient) == 3
        assert all(plus(game, oid) == 0 for oid in oids_of(game, BEAR))

    def test_the_ancient_itself_is_never_offered(self, builder):
        game, ancient = position(builder)
        to_how_many(game)
        answer_x(game, 1)
        values = [o.value for o in game.pending().options]
        assert ancient not in values
        assert set(values) == set(oids_of(game, BEAR))


class TestOnePlacementPerCreature:
    def test_hardened_scales_adds_one_per_creature_not_per_counter(self, builder):
        game, ancient = position(builder, extra=(SCALES,))
        bear = oids_of(game, BEAR, 0)[0]
        to_how_many(game)
        answer_x(game, 3)
        for _ in range(3):
            give_next_to(game, bear)
        settle(game)
        assert plus(game, ancient) == 0
        assert plus(game, bear) == 4, "three moved, plus one for a single placement"


class TestNothingToAsk:
    def test_no_counters_asks_nothing(self, builder):
        game, ancient = position(builder, counters=0)
        settle(game)
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN, limit=60)
        assert plus(game, ancient) == 0

    def test_no_other_creature_asks_nothing(self, builder):
        game, ancient = position(builder, mine=(), theirs=())
        pass_until(
            game,
            lambda g: g.state.step is Step.PRECOMBAT_MAIN
            or ((d := g.pending()) is not None and d.kind is DecisionKind.CHOOSE_X),
            limit=60,
        )
        assert game.state.step is Step.PRECOMBAT_MAIN
        assert plus(game, ancient) == 3

    def test_a_single_creature_is_not_asked_for(self, builder):
        game, ancient = position(builder, mine=(BEAR,), theirs=())
        bear = only_oid(game, BEAR, 0)
        to_how_many(game)
        answer_x(game, 2)
        settle(game)
        assert (plus(game, ancient), plus(game, bear)) == (1, 2)


def _card(effect) -> dict:
    return {
        "id": "t_dmc_probe",
        "name": "Probe",
        "types": ["Creature"],
        "power": 0,
        "toughness": 3,
        "abilities": [
            {
                "kind": "triggered",
                "text": "At the beginning of your upkeep, move counters.",
                "trigger": {"event": "upkeep", "controller": "you"},
                "effects": [effect],
            }
        ],
    }


class TestTheLoader:
    def test_the_shipped_shape_loads(self):
        compile_card(
            CardModel.model_validate(
                _card(
                    {
                        "op": "distribute_moved_counters",
                        "objects": {"types": ["Creature"], "exclude_self": True},
                    }
                )
            )
        )

    @pytest.mark.parametrize(
        "effect",
        [
            {"op": "distribute_moved_counters"},
            {"op": "distribute_moved_counters", "objects": {"target": "t1"}},
            {"op": "distribute_moved_counters", "objects": {"types": ["Creature"]}, "amount": 2},
            {
                "op": "distribute_moved_counters",
                "objects": {"types": ["Creature"]},
                "from": {"self_only": True},
            },
        ],
        ids=["no_pool", "targeted", "amount", "from"],
    )
    def test_refused(self, effect):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_card(effect)))
