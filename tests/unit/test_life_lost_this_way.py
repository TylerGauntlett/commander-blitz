"""The life lost this way: `lose_life`'s ``as`` binding.

    "When this creature enters, each opponent loses X life, where X is your
    devotion to black. You gain life equal to the life lost this way."
    -- Gray Merchant of Asphodel

The second sentence reads a number the first one produced, and the number is
what was **actually lost**, not what was asked for. Life loss can be replaced
(614.1; Bloodletter of Aclazotz's "they lose twice that much life instead") and
a life total can be unable to change at all (Teferi's Protection), and in both
cases "the life lost this way" is the changed number. The shipped way to say the
card before this binding existed recomputed ``amount`` inside the `gain_life`
(Malakir Bloodwitch), which agrees with the printed card exactly while nothing
replaces the loss and gains the wrong amount the moment something does: X
against a doubled 2X, X against a locked 0.

`primitives.lose_life` has always returned the actual loss; `op_lose_life`
threw it away. ``as`` keeps it, summed over every player the one op hit, as a
plain int read back with ``{"binding": …}``. Extort's "you gain that much life"
is the same read.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, _validate_effect
from automtg.engine.effects import RECORDING_OPS, execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.structs import LifeLock

DOUBLER = "t_always_bloodletter"  # an opponent's life loss is doubled

GRAY_MERCHANT_DRAIN = [
    {"op": "lose_life", "player": "each_opponent", "amount": {"const": 3}, "as": "lost"},
    {"op": "gain_life", "player": "you", "amount": {"binding": "lost"}},
]


def table(builder, players: int = 3, doublers: tuple[str, ...] = ()):
    """Every seat at 40, with ``doublers`` on player 0's battlefield."""
    b = builder(players=players).battlefield(0, ["swamp"] * 3)
    if doublers:
        b = b.battlefield(0, list(doublers))
    for pid in range(players):
        b = b.life(pid, 40)
    return b.build(advance=False)


def run(game, effects, controller: int = 0) -> EffectContext:
    """Resolve a decision-free effect list and hand back its context."""
    ctx = EffectContext(state=game.state, controller=controller)
    for _ in execute(ctx, effects):  # pragma: no cover - nothing here asks
        raise AssertionError("a drain asks no questions")
    return ctx


def life(game) -> list[int]:
    return [p.life for p in game.state.players]


class TestTheBinding:
    def test_it_is_summed_over_every_player_hit(self, builder):
        """Two opponents losing 3 is 6 life lost this way, not 3."""
        game = table(builder)
        ctx = run(game, GRAY_MERCHANT_DRAIN)
        assert ctx.bindings["lost"] == 6
        assert life(game) == [46, 37, 37]

    def test_it_is_a_plain_int(self, builder):
        """The `binding` value leaf reads ints only; a list would read as 0."""
        game = table(builder)
        ctx = run(game, GRAY_MERCHANT_DRAIN[:1])
        assert isinstance(ctx.bindings["lost"], int)

    def test_a_loss_of_zero_binds_zero(self, builder):
        """Devotion 0: nobody loses anything, and the gain reads 0 rather than a
        stale or missing name."""
        game = table(builder)
        effects = [
            {"op": "lose_life", "player": "each_opponent", "amount": {"const": 0}, "as": "lost"},
            {"op": "gain_life", "player": "you", "amount": {"binding": "lost"}},
        ]
        ctx = run(game, effects)
        assert ctx.bindings["lost"] == 0
        assert life(game) == [40, 40, 40]

    def test_without_as_nothing_is_written(self, builder):
        game = table(builder)
        ctx = run(game, [{"op": "lose_life", "player": "each_opponent", "amount": {"const": 2}}])
        assert ctx.bindings == {}
        assert life(game) == [40, 38, 38]

    def test_a_second_loss_overwrites_rather_than_accumulates(self, builder):
        """"This way" is this sentence's loss, not every loss so far."""
        game = table(builder)
        ctx = run(
            game,
            [
                {"op": "lose_life", "player": "each_opponent", "amount": {"const": 2}, "as": "lost"},
                {"op": "lose_life", "player": "each_opponent", "amount": {"const": 1}, "as": "lost"},
            ],
        )
        assert ctx.bindings["lost"] == 2


class TestItReadsTheActualLoss:
    """The whole reason for the binding: recomputing `amount` gets these wrong."""

    def test_a_doubled_loss_gains_the_doubled_amount(self, builder):
        game = table(builder, doublers=(DOUBLER,))
        ctx = run(game, GRAY_MERCHANT_DRAIN)
        assert ctx.bindings["lost"] == 12
        assert life(game) == [52, 34, 34]

    def test_the_doubler_does_not_touch_its_controllers_gain(self, builder):
        """Only the loss is replaced; the gain is exactly what was lost."""
        game = table(builder, players=2, doublers=(DOUBLER,))
        run(game, GRAY_MERCHANT_DRAIN)
        assert life(game) == [46, 34]

    def test_a_locked_opponent_contributes_nothing(self, builder):
        """A life total that can't change lost no life, so it pays nothing back."""
        game = table(builder)
        game.state.life_locks.append(LifeLock(player=1))
        ctx = run(game, GRAY_MERCHANT_DRAIN)
        assert ctx.bindings["lost"] == 3
        assert life(game) == [43, 40, 37]

    def test_every_opponent_locked_gains_nothing(self, builder):
        game = table(builder, players=2)
        game.state.life_locks.append(LifeLock(player=1))
        run(game, GRAY_MERCHANT_DRAIN)
        assert life(game) == [40, 40]


class TestTheLoader:
    def test_lose_life_is_a_recording_op(self):
        assert "lose_life" in RECORDING_OPS

    def test_as_on_lose_life_loads(self):
        _validate_effect(GRAY_MERCHANT_DRAIN[0], "test", {})

    def test_a_non_string_as_is_refused(self):
        with pytest.raises(DslError):
            _validate_effect(
                {"op": "lose_life", "player": "each_opponent", "amount": {"const": 1}, "as": 3},
                "test",
                {},
            )

    def test_as_on_gain_life_is_still_refused(self):
        """Gain records nothing -- only the loss half of the sentence binds."""
        with pytest.raises(DslError):
            _validate_effect({"op": "gain_life", "player": "you", "as": "gained"}, "test", {})
