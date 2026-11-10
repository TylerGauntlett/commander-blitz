"""`exile_until`'s ``rest_to_bottom`` — the walked cards go back, randomly.

Chaos Wand: "Target opponent exiles cards from the top of their library until
they exile an instant or sorcery card. You may cast that card without paying
its mana cost. Then put the exiled cards that weren't cast this way on the
bottom of that library in a random order."

Without the last sentence every walked card stays in exile, which is a mill
of the opponent's library that the printed card is not: the walked-past cards,
and an instant the controller declined, return to the bottom of the library
they came from. "That weren't cast this way" is the boundary: the cast card is
on the stack (601.2a) and is not among them, while a declined or refused hit
is. The order is random over those cards only, cascade's tail (702.85a), never
a shuffle of the whole library. Rule 400.3 keeps every card its owner's, so
the bottom is the walked library's, whoever controlled the effect -- and the
free cast still goes to the controller, the "you" of "you may cast" (109.5).
Dazzling Sphinx is the same walk from a combat-damage trigger.
"""

from __future__ import annotations

import inspect

import pytest

from commanderblitz.cards.loader import DslError, compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.structs import TargetRef
from tests.conftest import library_ids

FOREST = "forest"
BEAR = "t_bear"
INSTANT = "t_plain_instant"   # an untargeted instant, the Chaos Wand stop
SOURCE = "t_cascader"


def wand(**extra) -> dict:
    """Chaos Wand's walk."""
    return {
        "op": "exile_until",
        "player": {"target": "t1"},
        "objects": {"any_types": ["Instant", "Sorcery"]},
        "cast_free": True,
        "rest_to_bottom": True,
        "as": "hit",
        **extra,
    }


def board(builder, *, theirs: list[str], mine: list[str] | None = None):
    game = (
        builder(players=2)
        .battlefield(0, [SOURCE])
        .library(0, mine or [])
        .library(1, theirs)
        .build(advance=False)
    )
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, spec: dict, source: int, *, cast: bool):
    """Run the op with seat 1 as t1; answers every yes/no; returns (ctx, asked)."""
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        targets={"t1": (TargetRef("player", 1),)},
    )
    gen = OPS[spec["op"]](ctx, spec)
    asked: list[int] = []
    if inspect.isgenerator(gen):
        send = None
        while True:
            try:
                decision = gen.send(send)
            except StopIteration:
                break
            asked.append(decision.player)
            send = [0] if cast else [1]
    return ctx, asked


class TestTheCastCard:
    def test_a_cast_hit_is_not_bottomed_and_the_rest_are(self, builder):
        game, src = board(builder, theirs=[BEAR, FOREST, INSTANT, BEAR])

        ctx, asked = run(game, wand(), src, cast=True)

        assert asked == [0], "the controller, not the library's owner, may cast it"
        (item,) = game.state.stack
        assert item.def_id == INSTANT and item.controller == 0
        assert library_ids(game, 1)[0] == BEAR, "the unwalked card is still on top"
        assert sorted(library_ids(game, 1)[1:]) == sorted([BEAR, FOREST])
        assert game.state.players[1].exile == []
        assert ctx.bindings["hit"], "the binding still names the hit"

    def test_a_declined_hit_goes_to_the_bottom_with_the_rest(self, builder):
        game, src = board(builder, theirs=[FOREST, INSTANT, BEAR])

        run(game, wand(), src, cast=False)

        assert game.state.stack == []
        assert game.state.players[1].exile == []
        assert library_ids(game, 1)[0] == BEAR
        assert sorted(library_ids(game, 1)[1:]) == sorted([FOREST, INSTANT])

    def test_a_hit_that_cannot_be_cast_is_bottomed_too(self, builder):
        """A `cast_free_if` the hit fails is a cast that never happened."""
        game, src = board(builder, theirs=[FOREST, INSTANT])
        spec = wand(cast_free_if={"mana_value": {"op": ">=", "value": 5}})

        _, asked = run(game, spec, src, cast=True)

        assert asked == [], "a forbidden yes is no question"
        assert game.state.stack == []
        assert sorted(library_ids(game, 1)) == sorted([FOREST, INSTANT])


class TestWhereTheyGo:
    def test_the_bottom_is_the_walked_librarys_and_the_cards_stay_their_owners(
        self, builder
    ):
        game, src = board(builder, theirs=[FOREST, INSTANT], mine=[BEAR])

        run(game, wand(), src, cast=False)

        assert library_ids(game, 0) == [BEAR], "the controller's library is untouched"
        for oid in game.state.players[1].library:
            assert game.state.objects[oid].owner == 1

    def test_the_order_is_random_over_the_walked_cards(self, builder):
        orders = set()
        for seed in range(12):
            game = (
                builder(players=2, seed=seed)
                .battlefield(0, [SOURCE])
                .library(1, [FOREST, BEAR, FOREST, INSTANT])
                .build(advance=False)
            )
            src = next(o.oid for o in game.state.battlefield_objects(0))
            run(game, wand(), src, cast=False)
            orders.add(tuple(library_ids(game, 1)))
        assert len(orders) > 1, "the same order every time is not random"

    def test_an_exhausted_library_takes_everything_back(self, builder):
        game, src = board(builder, theirs=[FOREST, BEAR])

        ctx, asked = run(game, wand(), src, cast=True)

        assert asked == []
        assert ctx.bindings["hit"] == []
        assert sorted(library_ids(game, 1)) == sorted([FOREST, BEAR])
        assert game.state.players[1].exile == []

    def test_without_it_the_walk_stays_in_exile(self, builder):
        game, src = board(builder, theirs=[FOREST, INSTANT])
        spec = wand()
        del spec["rest_to_bottom"]

        run(game, spec, src, cast=False)

        assert library_ids(game, 1) == []
        assert len(game.state.players[1].exile) == 2


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_rest_to_bottom_probe",
                "name": "Rest To Bottom Probe",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "targets": [
                    {"id": "t1", "kind": "player", "count": 1,
                     "selector": {"controller": "opponent"}}
                ],
                "spell_effects": [effect],
            }
        )
    )


class TestTheLoader:
    def test_chaos_wands_walk_loads(self):
        probe(wand())

    def test_it_needs_the_cast(self):
        spec = wand()
        del spec["cast_free"]
        with pytest.raises(DslError, match="rest_to_bottom' needs 'cast_free'"):
            probe(spec)

    def test_an_uncast_hit_has_one_home(self):
        with pytest.raises(DslError, match="not both"):
            probe(wand(else_destination="hand"))

    def test_it_is_a_flag(self):
        with pytest.raises(DslError, match="true or false"):
            probe(wand(rest_to_bottom="yes"))
