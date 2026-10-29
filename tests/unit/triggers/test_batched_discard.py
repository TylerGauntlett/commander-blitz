""""Whenever you discard **one or more** land cards" -- Doctor Doom, King of Latveria.

Rule 603.2c: an ability that triggers on "one or more" of something triggers
once for an event that does several of them at once. A discard of several cards
is one event, but `primitives.discard_cards` fires `DISCARD` once per card, so
without a batch on the event Doom's "each opponent loses 2 life" drained 4 for
two lands discarded together -- the card printed for a hand-size or connive
discard paying out per card.

`replacements.discard` is the one discard event: it opens its own
`state.event_batch` and every `DISCARD` it fires carries it, so a `batched`
trigger queues once per call. What that has to mean, each a different card if
it is wrong:

- **Two lands at once is one trigger**, not two.
- **After the filter.** "Land cards" is asked of each card first, so a nonland
  beside a land is still one trigger and two nonlands none: batching before the
  filter would let the nonland spend the batch.
- **Not once a turn.** A later, separate discard triggers again.
- **The cleanup discard is its own event** (514.1), with no effect op around it
  to borrow a batch from.

`t_greedy_land_discard_drainer` is the counterfactual, the same trigger without
`batched`, so each claim is measured against the card that lacks it.
"""

from __future__ import annotations

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step
from commanderblitz.engine.player import MAX_HAND_SIZE
from commanderblitz.engine.primitives import draw_cards
from tests.conftest import pass_until

DOOM = "t_land_discard_drainer"
GREEDY = "t_greedy_land_discard_drainer"
START = 40  # the sandbox's starting life


def board(builder, watcher: str, hand):
    return (
        builder(players=2)
        .battlefield(0, [watcher])
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def discard(game, amount: int, *, controller: int = 0) -> None:
    """One `discard` op -- "discard N cards" -- the way a resolving effect runs it.

    Called with ``amount`` equal to the hand size, so nobody is asked which.
    """
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    spec = {"op": "discard", "player": "you", "amount": {"const": amount}}
    for _ in execute(ctx, [spec]):
        raise AssertionError("an all-of-the-hand discard asks nothing")


def settle(game) -> None:
    game._advance()
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def drained(game) -> int:
    return START - game.state.players[1].life


def queued(game) -> int:
    return len(game.state.pending_triggers)


class TestOneDiscardIsOneTrigger:
    def test_two_lands_at_once_drain_two(self, builder):
        game = board(builder, DOOM, ["forest", "forest"])
        discard(game, 2)
        assert queued(game) == 1
        settle(game)
        assert drained(game) == 2
        assert not game.state.players[0].hand

    def test_without_batched_the_same_discard_drains_four(self, builder):
        game = board(builder, GREEDY, ["forest", "forest"])
        discard(game, 2)
        settle(game)
        assert drained(game) == 4

    def test_two_separate_discards_drain_twice(self, builder):
        """Not `max_per_turn: 1`: a later discard is a new event."""
        game = (
            builder(players=2)
            .battlefield(0, [DOOM])
            .hand(0, ["forest"])
            .library(0, ["forest"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        discard(game, 1)
        settle(game)
        draw_cards(game.state, 0, 1)
        discard(game, 1)
        settle(game)
        assert drained(game) == 4

    def test_an_opponents_discard_does_not(self, builder):
        """"Whenever **you** discard" -- the discarding player."""
        game = (
            builder(players=2)
            .battlefield(0, [DOOM])
            .hand(1, ["forest", "forest"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        discard(game, 2, controller=1)
        settle(game)
        assert game.state.players[0].life == START
        assert drained(game) == 0


class TestTheFilterComesFirst:
    def test_a_nonland_and_a_land_drain_two(self, builder):
        """The nonland goes first and must not spend the batch."""
        game = board(builder, DOOM, ["t_bear", "forest"])
        discard(game, 2)
        assert queued(game) == 1
        settle(game)
        assert drained(game) == 2

    def test_only_nonlands_drain_nothing(self, builder):
        game = board(builder, DOOM, ["t_bear", "t_bear"])
        discard(game, 2)
        settle(game)
        assert drained(game) == 0


class TestTheCleanupDiscard:
    def test_two_lands_trimmed_at_cleanup_drain_two(self, builder):
        """514.1: one discard down to seven, with no effect op to batch it."""
        game = (
            builder(players=2)
            .battlefield(0, [DOOM])
            .hand(0, ["forest"] * (MAX_HAND_SIZE + 2))
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        pass_until(game, lambda g: g.state.turn == 2)
        assert len(game.state.players[0].hand) == MAX_HAND_SIZE, "the trim happened"
        assert drained(game) == 2


class TestTheLoader:
    def test_batched_loads_on_discard(self):
        model = CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "Probe.",
                        "trigger": {"event": "discard", "batched": True},
                        "effects": [
                            {"op": "gain_life", "player": "you", "amount": {"const": 1}}
                        ],
                    }
                ],
            }
        )
        assert compile_card(model).abilities[0].trigger.batched
