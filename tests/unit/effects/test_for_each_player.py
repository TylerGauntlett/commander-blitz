""""Each opponent sacrifices…" — a loop over players, not objects.

    Soul Shatter — "Each opponent sacrifices a creature or planeswalker with
    the greatest mana value among creatures and planeswalkers they control."

`for_each` iterates objects and binds one as `each`. There was no player-shaped
loop, so the only way to write this sentence was a single `sacrifice` over
`{"controller": "opponent"}` — which removes **one** permanent across the union
of every opponent's board rather than one from each. In a duel that is right by
accident; at a pod it is a third of the card.

**The binding is the point, not the iteration.** Running a body three times is
easy; what the body needs is a way to say "they". A nested selector writes
`{"controller": {"binding": "each_player"}}` and is scoped to that one player,
so `extreme` takes *their* maximum. With `"opponent"` instead, `extreme`
computes one global maximum over the merged pool, and the opponent whose best
creature is smaller keeps everything — the printed card takes something from
everyone.

That is why `controller` now accepts a player spec as well as its three words,
and why the test below uses two opponents with different-sized boards: at one
opponent every wrong implementation looks right.
"""

from __future__ import annotations

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool

BEAR = "t_bear"  # {1}{G} 2/2
DORK = "t_dork"  # {G} 1/1 -- cheaper, so never the greatest


def ctx_for(game, controller: int = 0) -> EffectContext:
    return EffectContext(state=game.state, controller=controller, source_oid=None)


GREATEST = {
    "zone": "battlefield",
    "any_types": ["Creature"],
    "extreme": {"of": "mana_value", "pick": "greatest"},
}


class TestTheBindingScopesTheSelector:
    def test_a_bound_player_narrows_the_pool_to_theirs(self, builder):
        game = builder(players=3).battlefield(1, [BEAR]).battlefield(2, [DORK]).build()
        ctx = ctx_for(game)

        ctx.bindings["each_player"] = 1
        first = resolve_pool(ctx, {**GREATEST, "controller": {"binding": "each_player"}})
        ctx.bindings["each_player"] = 2
        second = resolve_pool(ctx, {**GREATEST, "controller": {"binding": "each_player"}})

        assert len(first) == 1 and len(second) == 1
        assert first != second, "two players, two different answers"

    def test_opponent_merges_them_and_takes_one_maximum(self, builder):
        """The wrong implementation, pinned so the difference is on the record.

        Player 1 has a 2-drop and player 2 a 1-drop. `controller: "opponent"`
        ranks them together, so only player 1's creature is ever picked and
        player 2 loses nothing.
        """
        game = builder(players=3).battlefield(1, [BEAR]).battlefield(2, [DORK]).build()
        ctx = ctx_for(game)

        merged = resolve_pool(ctx, {**GREATEST, "controller": "opponent"})

        assert len(merged) == 1, "one global maximum, not one each"
        assert game.state.objects[merged[0]].controller == 1

    def test_each_players_own_maximum_is_their_own(self, builder):
        """Scoped, player 2's 1-drop *is* their greatest and is taken."""
        game = (
            builder(players=3)
            .battlefield(1, [BEAR, DORK])
            .battlefield(2, [DORK])
            .build()
        )
        ctx = ctx_for(game)

        ctx.bindings["each_player"] = 2
        theirs = resolve_pool(ctx, {**GREATEST, "controller": {"binding": "each_player"}})

        assert len(theirs) == 1
        assert game.state.card_of(game.state.objects[theirs[0]]).id == DORK


#: A body that is observable per player: each one it runs for loses a life.
#: `lose_life`'s player spec goes through `select_players`, which is the same
#: resolver the selector's `controller` uses -- so this exercises the binding
#: rather than just the iteration count.
DRAIN = {
    "op": "for_each_player",
    "players": "each_opponent",
    "effects": [
        {"op": "lose_life", "player": {"binding": "each_player"}, "amount": {"const": 1}}
    ],
}


def run(ctx, spec) -> None:
    from commanderblitz.engine.effects import execute

    for _ in execute(ctx, [spec]):
        raise AssertionError("this body asks nothing")


class TestTheLoopItself:
    def test_every_opponent_is_reached(self, builder):
        game = builder(players=3).build()
        before = [p.life for p in game.state.players]

        run(ctx_for(game), DRAIN)

        after = [p.life for p in game.state.players]
        assert after[1] == before[1] - 1
        assert after[2] == before[2] - 1

    def test_the_loops_own_controller_is_not_one_of_them(self, builder):
        game = builder(players=3).build()
        before = game.state.players[0].life

        run(ctx_for(game), DRAIN)

        assert game.state.players[0].life == before

    def test_each_player_may_be_the_whole_table(self, builder):
        game = builder(players=3).build()
        before = [p.life for p in game.state.players]

        run(ctx_for(game), {**DRAIN, "players": "each_player"})

        assert [p.life for p in game.state.players] == [n - 1 for n in before]

    def test_the_binding_is_restored_afterwards(self, builder):
        """A nested loop must not leak into the outer one."""
        game = builder(players=3).build()
        ctx = ctx_for(game)
        ctx.bindings["each_player"] = 99

        run(ctx, DRAIN)

        assert ctx.bindings["each_player"] == 99

    def test_the_binding_is_cleared_when_there_was_none(self, builder):
        game = builder(players=3).build()
        ctx = ctx_for(game)

        run(ctx, DRAIN)

        assert "each_player" not in ctx.bindings
