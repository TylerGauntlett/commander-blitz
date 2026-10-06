"""Join forces — the one cost the whole table pays.

    "Join forces — Starting with you, each player may pay any amount of mana.
    Draw a card for each mana paid this way."

Every other cost in the engine hangs off **one** player. `may`'s `pay` grew a
`player` spec for Rhystic Study, which is as close as the vocabulary gets — and
it asks that player once. Join forces asks the whole table, repeatedly, and adds
the answers up.

It is asked one unit at a time, and that is forced rather than stylistic: "any
amount" has no ceiling to offer as a `choose_x`, and a seat that stops paying is
a seat that answered no.

**Order is the card.** Starting with the controller, in turn order, later
players see what earlier ones have already put in — which is the whole politics
of a join-forces spell at a pod. Asked simultaneously, or in seat order
regardless of who cast it, it would be a different card.

The total lands in a binding named by `as`, read back with `{"binding": …}` the
way clash's `clash_won` is. An effect that collects it and names no binding has
taxed the whole table for nothing, so the loader refuses one.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader.effects import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import DecisionKind
from automtg.engine.errors import DslError

ISLAND = "island"
SPELL = "t_join_forces"

SPEC = {
    "op": "join_forces",
    "as": "joined",
    "pay": {"mana": "{1}"},
    "prompt": "Pay {1} into the shared pool?",
}


def table(builder, *lands_each: int):
    game = builder(players=len(lands_each))
    for pid, lands in enumerate(lands_each):
        game = game.battlefield(pid, [ISLAND] * lands)
    return game.build(advance=False)


def run(game, answers: dict[int, int], controller: int = 0):
    """Drive the op, letting each player say yes ``answers[pid]`` times."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = OPS["join_forces"](ctx, SPEC)
    said_yes: dict[int, int] = {}
    asked: list[int] = []
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return ctx, asked
        assert decision.kind is DecisionKind.MAY
        pid = decision.player
        asked.append(pid)
        used = said_yes.get(pid, 0)
        if used < answers.get(pid, 0):
            said_yes[pid] = used + 1
            send = [0]      # yes
        else:
            send = [1]      # no


class TestTheTotal:
    def test_nobody_paying_is_zero(self, builder):
        game = table(builder, 3, 3)
        ctx, _ = run(game, {})
        assert ctx.bindings["joined"] == 0

    def test_one_player_paying_counts(self, builder):
        game = table(builder, 3, 3)
        ctx, _ = run(game, {0: 2})
        assert ctx.bindings["joined"] == 2

    def test_every_seat_adds_to_it(self, builder):
        """The whole point: it is one number the table built together."""
        game = table(builder, 3, 3, 3)
        ctx, _ = run(game, {0: 1, 1: 2, 2: 3})
        assert ctx.bindings["joined"] == 6

    def test_an_opponent_can_pay_when_the_caster_does_not(self, builder):
        game = table(builder, 3, 3)
        ctx, _ = run(game, {1: 2})
        assert ctx.bindings["joined"] == 2


class TestWhatIsActuallySpent:
    def test_the_mana_leaves_each_player(self, builder):
        game = table(builder, 3, 3)
        run(game, {0: 2, 1: 1})

        tapped = {
            pid: sum(1 for o in game.state.battlefield_objects(pid) if o.tapped)
            for pid in (0, 1)
        }
        assert tapped == {0: 2, 1: 1}

    def test_a_player_with_no_mana_is_not_asked(self, builder):
        """Rule 118.4 again -- a cost nobody can pay is not offered."""
        game = table(builder, 3, 0)
        _, asked = run(game, {0: 1})
        assert 1 not in asked

    def test_it_stops_when_a_player_runs_out(self, builder):
        game = table(builder, 2, 0)
        ctx, _ = run(game, {0: 5})
        assert ctx.bindings["joined"] == 2, "two Islands, two mana"


class TestTheOrder:
    def test_it_starts_with_the_controller(self, builder):
        game = table(builder, 3, 3, 3)
        _, asked = run(game, {}, controller=1)
        assert asked[0] == 1

    def test_it_goes_round_the_table_in_turn_order(self, builder):
        game = table(builder, 3, 3, 3)
        _, asked = run(game, {}, controller=1)
        assert list(dict.fromkeys(asked)) == [1, 2, 0]


class TestTheLoaderGuard:
    def test_a_well_formed_effect_loads(self):
        _validate_effect(SPEC, "test", {})

    def test_omitting_as_is_refused(self):
        """Collecting the mana and naming no binding taxes the table for nothing."""
        with pytest.raises(DslError, match="join_forces needs an 'as'"):
            _validate_effect({"op": "join_forces", "pay": {"mana": "{1}"}}, "test", {})

    def test_a_malformed_pay_is_refused(self):
        with pytest.raises(DslError, match="bad 'pay' cost"):
            _validate_effect(
                {"op": "join_forces", "as": "joined", "pay": {"nonsense": 1}}, "test", {}
            )
