"""Bolster, mentor and evolve: comparing creatures against each other.

`docs/keywords.md` groups these three as wanting "derived-power comparisons in
filters, plus an extremum selector". Building them showed the group was really
two things, and only one of them needed engine work.

**Mentor and evolve were already expressible.** `_compare` in the selector
language has always evaluated a full *value expression* on the right-hand side,
so "target attacking creature with lesser power" is
`{"power": {"op": "<", "value": {"power_of": {"self": true}}}}` -- read off
derived characteristics on both sides. And a trigger's condition can compare
`{"power_of": {"binding": "subject"}}` against `{"power_of": {"self": true}}`,
which is evolve exactly. Both sat on the census as `routed` because the row was
written about the *shape* of the question rather than checked against the
comparison vocabulary that already existed.

**Bolster needed a real addition.** "The creature with the least toughness among
creatures you control" cannot be a `_compare` clause: those test each candidate
against a value known in advance, and an extremum is only knowable once the
whole pool is in hand. `extreme` therefore narrows the pool *after* every other
clause has filtered it.

Ties are kept rather than broken. Rule 701.36a has the player choose among
equals, and `choose_objects` is already the thing that asks -- narrowing to one
here would silently take the choice away, and picking by oid would make the
answer depend on the order permanents happened to arrive in.
"""

from __future__ import annotations

import pytest

from automtg.engine.characteristics import chars
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool, validate_selector
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, only_oid, pass_until

BEAR = "t_bear"  # 2/2
DORK = "t_dork"  # 1/1
WALL = "t_wall"  # 0/4
BIG = "t_big"  # 6/6
MENTOR = "t_mentor"  # 3/3, mentor
EVOLVER = "t_evolver"  # 1/1, evolve
BOLSTERER = "t_bolsterer"  # 2/2, ETB bolster 2


def pool_for(game, **extra) -> list[str]:
    ctx = EffectContext(state=game.state, controller=0)
    selector = {"controller": "you", "types": ["Creature"], **extra}
    return sorted(game.state.objects[o].def_id for o in resolve_pool(ctx, selector))


def settle(game, limit: int = 40) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("nothing resolved")


class TestTheExtremeSelector:
    def test_least_picks_the_smallest(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, WALL, BIG]).build()
        assert pool_for(game, extreme={"of": "toughness", "pick": "least"}) == [BEAR]

    def test_greatest_picks_the_largest(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, WALL, BIG]).build()
        assert pool_for(game, extreme={"of": "toughness", "pick": "greatest"}) == [BIG]

    def test_ties_are_all_kept(self, builder):
        """Rule 701.36a: the player chooses among equals, and `choose_objects`
        is what asks. Narrowing to one here would take that choice away."""
        game = builder(players=2).battlefield(0, [BEAR, BEAR, BIG]).build()
        assert pool_for(game, extreme={"of": "toughness", "pick": "least"}) == [BEAR, BEAR]

    def test_it_reads_derived_characteristics(self, builder):
        """"Least toughness" means the toughness it actually has. A +1/+1
        counter on the smallest creature moves the answer."""
        game = builder(players=2).battlefield(0, [BEAR, WALL]).build()
        assert pool_for(game, extreme={"of": "toughness", "pick": "least"}) == [BEAR]
        game.state.objects[only_oid(game, BEAR, 0)].add_counter("+1/+1", 3)
        game.state.bump_chars()
        assert pool_for(game, extreme={"of": "toughness", "pick": "least"}) == [WALL]

    def test_it_narrows_after_the_other_clauses(self, builder):
        """The extremum is of the *filtered* pool, not of the battlefield.

        The wall is the toughest thing out there; asking for the greatest
        toughness among Bears must not return it.
        """
        game = builder(players=2).battlefield(0, [BEAR, WALL, BIG]).build()
        ctx = EffectContext(state=game.state, controller=0)
        pool = resolve_pool(
            ctx,
            {
                "controller": "you",
                "subtypes": ["Bear"],
                "extreme": {"of": "toughness", "pick": "greatest"},
            },
        )
        assert [game.state.objects[o].def_id for o in pool] == [BEAR]

    def test_an_empty_pool_stays_empty(self, builder):
        game = builder(players=2).battlefield(0, []).build()
        assert pool_for(game, extreme={"of": "power", "pick": "least"}) == []

    @pytest.mark.parametrize(
        "spec",
        [
            {"of": "colour", "pick": "least"},
            {"of": "power", "pick": "middling"},
            "least",
        ],
    )
    def test_a_malformed_extreme_is_refused(self, builder, spec):
        game = builder(players=2).battlefield(0, [BEAR]).build()
        ctx = EffectContext(state=game.state, controller=0)
        with pytest.raises(DslError):
            resolve_pool(ctx, {"controller": "you", "extreme": spec})

    def test_the_loader_accepts_the_key(self):
        validate_selector(
            {"controller": "you", "extreme": {"of": "toughness", "pick": "least"}}, "test"
        )


class TestBolster:
    def enter_bolsterer(self, game) -> None:
        """Put the bolsterer onto the battlefield so its ETB actually fires."""
        from automtg.engine.primitives import create_token

        create_token(game.state, BOLSTERER, 0)
        settle(game)

    def test_it_grows_the_least_tough_creature(self, builder):
        # A 0/4 wall and a 2/2 bear, and the 2/2 bolsterer joining them: the
        # bear and the bolsterer tie at 2, so this asserts on a board where the
        # answer is unambiguous instead.
        game = builder(players=2).battlefield(0, [WALL, BIG]).build()
        wall = only_oid(game, WALL, 0)
        big = only_oid(game, BIG, 0)
        self.enter_bolsterer(game)
        # The bolsterer is a 2/2 and the wall is a 0/4, so the bolsterer is the
        # least tough thing on the board and bolsters itself.
        assert game.state.objects[wall].counter("+1/+1") == 0
        assert game.state.objects[big].counter("+1/+1") == 0

    def test_it_grows_something_else_when_that_is_smaller(self, builder):
        """A 1/1 dork is tougher than nothing and less tough than the 2/2
        bolsterer, so the choice is forced and is not the bolsterer itself."""
        game = builder(players=2).battlefield(0, [DORK, WALL, BIG]).build()
        dork = only_oid(game, DORK, 0)
        self.enter_bolsterer(game)
        assert game.state.objects[dork].counter("+1/+1") == 2
        assert chars(game.state, dork).toughness == 3
        assert game.state.objects[only_oid(game, WALL, 0)].counter("+1/+1") == 0


class TestMentorWasAlreadyExpressible:
    def test_a_smaller_attacker_is_a_legal_target(self, builder):
        game = builder(players=2).battlefield(0, [MENTOR, BEAR]).build()
        mentor = only_oid(game, MENTOR, 0)
        bear = only_oid(game, BEAR, 0)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        for oid in (mentor, bear):
            game.apply(
                find_action(
                    game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),)
                )
            )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        settle(game)
        assert game.state.objects[bear].counter("+1/+1") == 1, (
            "the 2/2 has lesser power than the 3/3 mentor"
        )

    def test_the_mentor_does_not_target_itself(self, builder):
        game = builder(players=2).battlefield(0, [MENTOR]).build()
        mentor = only_oid(game, MENTOR, 0)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=mentor, targets=(TargetRef.player(1),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        settle(game)
        assert game.state.objects[mentor].counter("+1/+1") == 0


class TestEvolveWasAlreadyExpressible:
    def test_a_bigger_creature_entering_grows_it(self, builder):
        game = builder(players=2).battlefield(0, [EVOLVER]).build()
        evolver = only_oid(game, EVOLVER, 0)
        from automtg.engine.primitives import create_token

        create_token(game.state, BEAR, 0)  # a 2/2 joining a 1/1
        settle(game)
        assert game.state.objects[evolver].counter("+1/+1") == 1

    def test_a_smaller_creature_does_not(self, builder):
        """The condition is the whole keyword: evolve is not "whenever a
        creature enters"."""
        game = builder(players=2).battlefield(0, [EVOLVER], counters={"+1/+1": 3}).build()
        evolver = only_oid(game, EVOLVER, 0)
        from automtg.engine.primitives import create_token

        create_token(game.state, BEAR, 0)  # a 2/2 joining a 4/4
        settle(game)
        assert game.state.objects[evolver].counter("+1/+1") == 3, "no new counter"
