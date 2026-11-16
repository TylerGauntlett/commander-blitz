"""Binding what a proliferate actually grew.

    Ripples of Potential -- "Proliferate, then choose any number of permanents
    you control **that had a counter put on them this way**. Those permanents
    phase out."

"This way" is the proliferate's own record (608.2c reads back what the earlier
part of the effect did), and nothing else on the board says it. A `has_counters`
selector afterwards would also offer every permanent you control that carried a
counter and was declined, and a permanent the controller chose whose placement
could not happen (101.2, Darksteel Angel's "can't have -1/-1 counters put on
them") would be offered although it received nothing.

So `as` on `proliferate` binds the permanents that **received** a counter, each
once, across every repetition a `replace_proliferate` adds (Tekuthal: each
repetition is a proliferate of this one effect, so both are "this way"). Players
are never in it. The witness is Ripples of Potential's effect list, run below as
written on the card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid

BEAR = "t_bear"
WARD = "t_chc_ward"  # "Creatures you control can't have -1/-1 counters put on them."
DOUBLER = "t_proliferate_doubler"

RIPPLES = [
    {"op": "proliferate", "as": "proliferated"},
    {
        "op": "choose_permanents",
        "as": "chosen",
        "objects": {
            "binding": "proliferated",
            "zone": "battlefield",
            "controller": "you",
            "count": "any",
            "chooser": "controller",
        },
    },
    {"op": "phase_out", "objects": {"binding": "chosen", "zone": "battlefield"}},
]


def position(builder, *, doubler: bool = False, ward: bool = False):
    """Two bears of ours and one of theirs, each with a +1/+1 counter.

    ``ward`` adds a bear of ours carrying only a -1/-1 counter under a
    ``cant_have_counters`` static: choosing it adds nothing.
    """
    b = (
        builder(players=2)
        .battlefield(0, [BEAR, BEAR], counters={"+1/+1": 1})
        .battlefield(1, [BEAR], counters={"+1/+1": 1})
    )
    if ward:
        b = b.battlefield(0, ["t_chc_bear"], counters={"-1/-1": 1}).battlefield(0, [WARD])
    if doubler:
        b = b.battlefield(0, [DOUBLER])
    game = b.build()
    mine = oids_of(game, BEAR, 0)
    theirs = only_oid(game, BEAR, 1)
    return game, mine, theirs


def run(game, effects, answers) -> list:
    """Resolve ``effects`` for player 0. ``answers`` is a list of oid sets, one
    per decision, each answered with the options whose ref is in it."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, effects)
    asked = []
    queue = list(answers)
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            wanted = queue.pop(0)
            picks = [i for i, o in enumerate(decision.options) if o.ref and o.ref.id in wanted]
            decision = gen.send(picks)
    except StopIteration:
        pass
    return asked, ctx


def offered(decision) -> set[int]:
    return {o.ref.id for o in decision.options if o.ref and o.ref.kind == "object"}


class TestTheBindingIsWhatReceivedACounter:
    def test_a_declined_permanent_is_not_offered(self, builder):
        game, (a, b), theirs = position(builder)
        asked, _ = run(game, RIPPLES, [{a, theirs}, {a}])
        assert offered(asked[1]) == {a}
        assert b not in offered(asked[1])

    def test_an_opponents_permanent_received_one_and_is_not_offered(self, builder):
        game, (a, _), theirs = position(builder)
        asked, ctx = run(game, RIPPLES, [{a, theirs}, {a}])
        assert theirs in ctx.bindings["proliferated"]
        assert theirs not in offered(asked[1])

    def test_a_prohibited_placement_received_nothing(self, builder):
        game, (a, _), _ = position(builder, ward=True)
        shielded = only_oid(game, "t_chc_bear", 0)
        asked, ctx = run(game, RIPPLES, [{a, shielded}, {a}])
        assert game.state.objects[shielded].counters.get("-1/-1") == 1
        assert ctx.bindings["proliferated"] == [a]
        assert shielded not in offered(asked[1])

    def test_players_are_never_bound(self, builder):
        game, (a, _), _ = position(builder)
        game.state.players[1].poison = 1
        _, ctx = run(game, [{"op": "proliferate", "as": "proliferated"}], [{a, 1}])
        assert game.state.players[1].poison == 2
        assert ctx.bindings["proliferated"] == [a]

    def test_nothing_chosen_binds_an_empty_pool(self, builder):
        game, _, _ = position(builder)
        _, ctx = run(game, [{"op": "proliferate", "as": "proliferated"}], [set()])
        assert ctx.bindings["proliferated"] == []


class TestEveryRepetitionIsThisWay:
    def test_both_proliferates_under_a_doubler_bind(self, builder):
        game, (a, b), _ = position(builder, doubler=True)
        asked, ctx = run(game, RIPPLES, [{a}, {b}, {a, b}])
        assert ctx.bindings["proliferated"] == [a, b]
        assert offered(asked[2]) == {a, b}

    def test_a_permanent_grown_twice_is_bound_once(self, builder):
        game, (a, _), _ = position(builder, doubler=True)
        _, ctx = run(game, [{"op": "proliferate", "as": "proliferated"}], [{a}, {a}])
        assert game.state.objects[a].counters["+1/+1"] == 3
        assert ctx.bindings["proliferated"] == [a]


class TestThoseThatWereChosenPhaseOut:
    def test_only_the_chosen_phase_out(self, builder):
        game, (a, b), _ = position(builder)
        run(game, RIPPLES, [{a, b}, {b}])
        assert game.state.objects[b].phased_out
        assert not game.state.objects[a].phased_out

    def test_choosing_none_phases_out_nothing(self, builder):
        game, (a, b), _ = position(builder)
        run(game, RIPPLES, [{a, b}, set()])
        assert not game.state.objects[a].phased_out
        assert not game.state.objects[b].phased_out


def _probe(effects: list) -> CardModel:
    text = "Proliferate."
    return CardModel.model_validate(
        {
            "id": "t_proliferate_as_probe",
            "name": "Test Proliferate As Probe",
            "oracle_text": text,
            "mana_cost": "{1}{U}",
            "types": ["Sorcery"],
            "spell_effects": effects,
        }
    )


class TestTheLoader:
    def test_as_is_accepted(self):
        compile_card(_probe([{"op": "proliferate", "as": "proliferated"}]), source="test")

    def test_a_non_string_as_is_refused(self):
        with pytest.raises(DslError, match="'as'"):
            compile_card(_probe([{"op": "proliferate", "as": 3}]), source="test")
