"""`suspend` -- "…with two time counters on it. If it doesn't have suspend, it
gains suspend." (702.62)

Doom's Time Platform exiles a card from a graveyard that way; Kang Prime puts
the counters on a card its own `exile_until` walk already exiled. Either way the
card must end up exactly where suspending it from hand leaves it, because the
rest -- the upkeep countdown, the free cast, a creature's haste -- belongs to
suspend and not to the card that did it.

The near miss is `exile` followed by `add_counters`: a card in exile with two
time counters that nothing ever ticks, which is a removal spell aimed at your
own graveyard. The other is whose card it is. A card in exile is controlled by
its owner, so "your upkeep" and "you may cast it" both name the **owner**; a
suspend recorded for the effect's controller would let me cast my opponent's
card on my upkeep.
"""

from __future__ import annotations

import inspect

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.suspend import TIME_COUNTER
from tests.conftest import pass_until

BEAR = "grizzly_bears"
FOREST = "forest"
SOURCE = "t_cascader"  # only somewhere for the effect to come from


def board(builder, *, mine: list[str] = (), theirs: list[str] = (), library: list[str] = ()):
    """Seat 0 controls the source; each seat's graveyard as given."""
    game = (
        builder(players=2)
        .battlefield(0, [SOURCE])
        .graveyard(0, list(mine))
        .graveyard(1, list(theirs))
        .library(0, list(library) + [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )
    src = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == SOURCE)
    return game, src


def run(game, source: int, *specs: dict, bindings: dict | None = None) -> EffectContext:
    """Run ops in one resolution, as seat 0, sharing their bindings."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    ctx.bindings.update(bindings or {})
    for spec in specs:
        gen = OPS[spec["op"]](ctx, spec)
        if inspect.isgenerator(gen):
            for _ in gen:
                raise AssertionError("suspend asked a question it has no reason to ask")
    return ctx


def in_graveyard(game, pid: int, def_id: str) -> int:
    return next(o for o in game.state.players[pid].graveyard if game.state.objects[o].def_id == def_id)


def suspend_it(oid: int, amount=2) -> tuple[dict, dict]:
    return {"op": "suspend", "objects": {"binding": "it"}, "amount": amount}, {"it": [oid]}


def past_the_next_upkeep_of(game, pid: int) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn > turn
        and g.state.active_player == pid
        and g.state.step > Step.UPKEEP,
    )


class TestSuspending:
    def test_a_graveyard_card_is_exiled_with_its_time_counters(self, builder):
        """Doom's Time Platform: out of the graveyard, two counters, suspended."""
        game, src = board(builder, mine=[BEAR])
        bear = in_graveyard(game, 0, BEAR)
        spec, bound = suspend_it(bear)

        run(game, src, spec, bindings=bound)

        obj = game.state.objects[bear]
        assert obj.zone is Zone.EXILE
        assert bear in game.state.players[0].exile
        assert obj.counter(TIME_COUNTER) == 2
        assert obj.suspended_by == 0

    def test_a_card_already_in_exile_stays_put_and_is_suspended(self, builder):
        """Kang Prime: the walk exiled it; "put two time counters on that card"."""
        game, src = board(builder, library=[FOREST, BEAR])
        walk = {"op": "exile_until", "objects": {"not_types": ["Land"]}, "as": "hit"}
        mark = {"op": "suspend", "objects": {"binding": "hit"}, "amount": 2}

        ctx = run(game, src, walk, mark)

        (hit,) = ctx.bindings["hit"]
        assert game.state.objects[hit].def_id == BEAR
        assert game.state.objects[hit].counter(TIME_COUNTER) == 2
        assert game.state.objects[hit].suspended_by == 0
        forest = next(
            o for o in game.state.players[0].exile if game.state.objects[o].def_id == FOREST
        )
        assert game.state.objects[forest].suspended_by is None, "only that card"
        assert game.state.objects[forest].counter(TIME_COUNTER) == 0

    def test_nothing_goes_on_the_stack(self, builder):
        game, src = board(builder, mine=[BEAR])
        spec, bound = suspend_it(in_graveyard(game, 0, BEAR))
        run(game, src, spec, bindings=bound)
        assert game.state.stack == []

    def test_the_count_is_a_value(self, builder):
        game, src = board(builder, mine=[BEAR])
        bear = in_graveyard(game, 0, BEAR)
        spec, bound = suspend_it(bear, amount={"const": 4})
        run(game, src, spec, bindings=bound)
        assert game.state.objects[bear].counter(TIME_COUNTER) == 4


class TestTheCountdown:
    def test_one_counter_per_upkeep_then_a_free_cast_with_haste(self, builder):
        """The whole point: two of your upkeeps, then a hasty Bear for nothing."""
        game, src = board(builder, mine=[BEAR])
        bear = in_graveyard(game, 0, BEAR)
        spec, bound = suspend_it(bear)
        run(game, src, spec, bindings=bound)

        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[bear].zone is Zone.EXILE, "not the first upkeep"
        assert game.state.objects[bear].counter(TIME_COUNTER) == 1

        past_the_next_upkeep_of(game, 0)
        pass_until(game, lambda g: g.state.objects[bear].zone is Zone.BATTLEFIELD)
        obj = game.state.objects[bear]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.controller == 0
        assert obj.suspended_by is None
        assert obj.entered_turn == game.state.turn, "it arrived this turn"
        assert "haste" in chars(game.state, bear).keywords

    def test_the_opponents_upkeep_does_not_tick_it(self, builder):
        game, src = board(builder, mine=[BEAR])
        bear = in_graveyard(game, 0, BEAR)
        spec, bound = suspend_it(bear)
        run(game, src, spec, bindings=bound)

        past_the_next_upkeep_of(game, 0)
        assert game.state.objects[bear].counter(TIME_COUNTER) == 1

        past_the_next_upkeep_of(game, 1)
        assert game.state.objects[bear].counter(TIME_COUNTER) == 1, "not their upkeep"


class TestWhoseCardItIs:
    def test_an_opponents_card_is_its_owners_to_tick_and_cast(self, builder):
        """A card in exile is controlled by its owner: their upkeep, their cast."""
        game, src = board(builder, theirs=[BEAR])
        bear = in_graveyard(game, 1, BEAR)
        spec, bound = suspend_it(bear)
        run(game, src, spec, bindings=bound)

        obj = game.state.objects[bear]
        assert obj.suspended_by == 1
        assert bear in game.state.players[1].exile

        past_the_next_upkeep_of(game, 0)
        assert obj.counter(TIME_COUNTER) == 2, "my upkeep does not tick their card"

        past_the_next_upkeep_of(game, 1)
        assert game.state.objects[bear].counter(TIME_COUNTER) == 1
        past_the_next_upkeep_of(game, 1)
        pass_until(game, lambda g: g.state.objects[bear].zone is Zone.BATTLEFIELD)
        assert game.state.objects[bear].controller == 1
        assert "haste" in chars(game.state, bear).keywords


class TestTheLoaderGuard:
    def _card(self, effect: dict, **extra) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_suspend_probe",
                "name": "Suspend Probe",
                "mana_cost": "{2}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
                **extra,
            }
        )

    def test_doom_s_time_platform_shape_loads(self):
        compile_card(
            self._card(
                {"op": "suspend", "objects": {"target": "t1"}, "amount": 2},
                targets=[
                    {
                        "id": "t1",
                        "kind": "card_in_graveyard",
                        "count": 1,
                        "selector": {
                            "zone": "graveyard",
                            "controller": "you",
                            "not_types": ["Land"],
                        },
                    }
                ],
            )
        )

    @pytest.mark.parametrize(
        ("effect", "message"),
        [
            ({"op": "suspend", "amount": 2}, "needs 'objects'"),
            ({"op": "suspend", "objects": {"binding": "hit"}}, "needs an 'amount'"),
        ],
    )
    def test_refusals(self, effect, message):
        with pytest.raises(DslError, match=message):
            compile_card(self._card(effect))
