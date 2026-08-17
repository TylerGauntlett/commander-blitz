""""Whenever an opponent loses life… (Damage causes loss of life.)"

    Bloodthirsty Conqueror — "Whenever an opponent loses life, you gain that
    much life."

`LIFE_LOST` had existed since `lose_life` did, and nothing subscribed to it: the
event was in the log and had no DSL name. Giving it one is a single row in
`TRIGGER_EVENTS`, and the amount is the `amount` binding the event already
carried.

**The reminder text is the specification.** Every card of this shape prints
"(Damage causes loss of life.)", so a trigger that fires only for `lose_life`
would miss combat damage, burn, and the whole reason the card is played. So
`damage_player` fires `LIFE_LOST` too.

That created a double-count that had to be paid for rather than ignored: the
turn ledger folded `life_lost` from **both** `DAMAGE_DEALT` and `LIFE_LOST`, so
a burn spell would have been counted twice by `life_lost_this_turn`. The fold is
now only on `LIFE_LOST`, one source of truth — and doing it from `DAMAGE_DEALT`
was already wrong in the other direction, because **infect** damage to a player
becomes poison counters and costs no life at all. That is why the new `fire` sits
inside the non-poison branch.
"""

from __future__ import annotations

from automtg.engine.primitives import damage_player, gain_life, lose_life
from tests.conftest import pass_until

CONQUEROR = "t_conqueror"  # "whenever an opponent loses life, you gain that much"


def board(builder, extra=()):
    return (
        builder(players=2)
        .battlefield(0, [CONQUEROR, *extra])
        .library(0, ["swamp"] * 20)
        .build()
    )


def settle(game):
    pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)


def gained(game, fn) -> int:
    before = game.state.players[0].life
    fn()
    settle(game)
    return game.state.players[0].life - before


class TestEveryWayLifeIsLost:
    def test_a_plain_life_loss_triggers_it(self, builder):
        game = board(builder)
        assert gained(game, lambda: lose_life(game.state, 1, 3)) == 3

    def test_damage_triggers_it_too(self, builder):
        """The reminder text, and the reason the card is played."""
        game = board(builder)
        assert gained(game, lambda: damage_player(game.state, 1, 4, None)) == 4

    def test_combat_damage_triggers_it(self, builder):
        game = board(builder)
        assert (
            gained(game, lambda: damage_player(game.state, 1, 2, None, is_combat=True))
            == 2
        )

    def test_the_amount_is_the_amount(self, builder):
        game = board(builder)
        assert gained(game, lambda: lose_life(game.state, 1, 7)) == 7


class TestWhoseLifeItWas:
    def test_your_own_loss_does_not_trigger_it(self, builder):
        """"Whenever an **opponent** loses life."""
        game = board(builder)
        before = game.state.players[0].life
        lose_life(game.state, 0, 3)
        settle(game)
        assert game.state.players[0].life == before - 3, "lost 3, gained nothing"

    def test_gaining_life_does_not_trigger_it(self, builder):
        game = board(builder)
        assert gained(game, lambda: gain_life(game.state, 1, 3)) == 0


class TestTheLedgerIsNotDoubleCounted:
    """The cost of firing the event from two primitives."""

    def test_damage_counts_once(self, builder):
        game = board(builder)
        damage_player(game.state, 1, 5, None)
        assert game.state.turn_ledger.life_lost.get(1) == 5

    def test_a_plain_loss_counts_once(self, builder):
        game = board(builder)
        lose_life(game.state, 1, 5)
        assert game.state.turn_ledger.life_lost.get(1) == 5

    def test_damage_is_still_damage_in_the_ledger(self, builder):
        game = board(builder)
        damage_player(game.state, 1, 5, None)
        assert game.state.turn_ledger.damage_taken.get(1) == 5
