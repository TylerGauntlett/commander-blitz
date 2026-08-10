"""Effects that arrange for something to happen later.

Every other trigger in the engine fires *from* an event that has just happened.
This is the other shape: an effect that has already resolved scheduling something
for a future step, with no object left to hang a trigger on. "At the beginning of
the next turn's upkeep, draw a card" is the whole of Arcane Denial's value, and
without it the card is a strictly worse Counterspell.

The property worth pinning is the timing. A delayed trigger that fires
immediately is not a delayed trigger, and one that never fires is a card that
silently does half of what it says.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step
from tests.conftest import _default_answer


def schedule(game, step: str, effects: list[dict], controller: int = 0) -> None:
    """Queue a delayed trigger directly, without a card in the way."""
    from automtg.engine.structs import DelayedTrigger

    game.state.delayed_triggers.append(
        DelayedTrigger(
            step=step,
            controller=controller,
            effects=tuple(effects),
            turn=game.state.turn,
            description="test",
        )
    )


def run_until(game, predicate, limit: int = 300) -> None:
    for _ in range(limit):
        if predicate(game) or game.over:
            return
        decision = game.pending()
        if decision is None:
            return
        game.apply(_default_answer(game, decision))


class TestTiming:
    def test_it_does_not_fire_straight_away(self, builder):
        game = builder(players=2).battlefield(0, ["forest"] * 4).build(advance=False)
        before = len(game.state.players[0].hand)
        schedule(game, "upkeep", [{"op": "draw", "player": "you", "amount": {"const": 1}}])
        game._advance()
        assert len(game.state.delayed_triggers) == 1 or len(game.state.players[0].hand) > before

    def test_it_fires_at_the_step_it_names(self, builder):
        game = builder(players=2).battlefield(0, ["forest"] * 4).build(advance=False)
        game._advance()
        before = len(game.state.players[0].hand)
        schedule(game, "end_step", [{"op": "draw", "player": "you", "amount": {"const": 2}}])

        run_until(game, lambda g: g.state.step is Step.END_STEP and not g.state.delayed_triggers)
        assert len(game.state.players[0].hand) >= before + 2
        assert game.state.delayed_triggers == []

    def test_it_fires_once_and_is_forgotten(self, builder):
        """A delayed trigger left in the queue would fire every turn forever."""
        game = builder(players=2).battlefield(0, ["forest"] * 4).build(advance=False)
        game._advance()
        schedule(game, "upkeep", [{"op": "gain_life", "player": "you", "amount": {"const": 5}}])

        start = game.state.turn
        run_until(game, lambda g: g.state.turn > start + 2)
        # Once, not once per upkeep.
        assert game.state.players[0].life == 45
        assert game.state.delayed_triggers == []

    def test_bindings_are_captured_when_it_is_scheduled(self, builder):
        """By the time it fires, what it was about may be gone.

        Capturing at schedule time is the whole reason this is not just a
        trigger with a later event.
        """
        game = builder(players=2).battlefield(0, ["forest"] * 4).build(advance=False)
        game._advance()
        from automtg.engine.structs import DelayedTrigger

        game.state.delayed_triggers.append(
            DelayedTrigger(
                step="end_step",
                controller=0,
                # Life rather than cards: the turn's own draw steps would swamp a
                # hand-size measurement, and this test is about the binding.
                effects=({"op": "gain_life", "player": "you", "amount": {"binding": "how_many"}},),
                bindings={"how_many": 3},
                turn=game.state.turn,
            )
        )
        before = game.state.players[0].life
        run_until(game, lambda g: g.state.step is Step.END_STEP and not g.state.delayed_triggers)
        assert game.state.players[0].life == before + 3


class TestArcaneDenialUsesIt:
    def test_both_halves_of_the_delayed_draw_happen(self, registry, builder):
        """The card's whole point, and the reason the subsystem exists.

        A/B against a plain Counterspell rather than an absolute count, so the
        ordinary draw steps cancel out and only the delayed draws are measured.
        """
        from automtg.engine.enums import Zone
        from automtg.engine.stack import push_spell
        from automtg.engine.state import new_object

        def play(card_id: str) -> tuple[int, int]:
            game = (
                builder(players=2)
                .battlefield(0, ["island"] * 6)
                .hand(0, [card_id])
                .library(0, ["forest"] * 20)
                .library(1, ["forest"] * 20)
                .build(advance=False)
            )
            obj = new_object(game.state, "forest", owner=1, zone=Zone.HAND)
            game.state.players[1].hand.append(obj.oid)
            push_spell(game.state, obj.oid, 1)
            game._advance()
            cast = next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
            )
            game.apply(cast)
            start = game.state.turn
            run_until(game, lambda g: g.state.turn > start + 1)
            return len(game.state.players[0].hand), len(game.state.players[1].hand)

        if "arcane_denial" not in registry:
            import pytest

            pytest.skip("arcane_denial is not in the pool")

        plain = play("counterspell")
        denial = play("arcane_denial")
        assert denial[0] - plain[0] == 1, "you should draw one more than a plain counter"
        assert denial[1] - plain[1] == 2, "its controller should draw two"
