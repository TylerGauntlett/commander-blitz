"""Staff of the Storyteller -- "Whenever you create **one or more** creature tokens".

Rule 603.2c: an ability that triggers on "one or more" of something triggers
once for an event that does several of them at once. Tokens are created one
object at a time, so `TOKEN_CREATED` fires once per token, and `batched` is
what makes the *ability* queue once per creation. It groups by the event's
``batch``, which `primitives.create_token` did not write: the flag loaded and
was ignored, and a three-token creation put three story counters on the Staff
where the card prints one.

Three things a "creation" has to mean, each a different card if it is wrong:

- **Everything one `create_token` makes**, however many. A doubler
  (Doubling Season, Mondrak) makes "twice that many" *in the same event*
  (614.1), so it is still one trigger, not two.
- **After the filter.** "Creature tokens" is asked of each token first: a
  Treasure beside a Spirit is still one trigger, and a lone Treasure none.
  Batching before the filter would let the Treasure spend the batch.
- **Not once a turn.** A later, separate creation triggers again -- the line
  between `batched` and `max_per_turn: 1`.

`t_greedy_storyteller` is the counterfactual, the same trigger without
`batched`, so each claim is measured against the card that lacks it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from tests.conftest import oids_of, only_oid

STAFF = "t_storyteller"
GREEDY = "t_greedy_storyteller"
SPIRIT = "spirit_1_1_w_flying"
TREASURE = "treasure_token"


def board(builder, *mine, theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    return game, only_oid(game, mine[0])


def settle(game) -> None:
    """Let the queued triggers resolve (the board is built without advancing)."""
    game._advance()
    for _ in range(40):
        if not game.state.stack and game.pending() is None:
            return
        actions = game.legal_actions()
        if not actions:
            return
        game.apply(actions[0])


def create(game, token: str, amount: int = 1, *, controller: int = 0) -> None:
    """One `create_token` op, run the way a resolving effect runs it."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    spec = {"op": "create_token", "token": token, "amount": {"const": amount}}
    for _ in execute(ctx, [spec]):
        raise AssertionError("create_token asks nothing here")


def story(game, oid: int) -> int:
    return game.state.objects[oid].counter("story")


def queued(game, oid: int) -> int:
    return sum(1 for t in game.state.pending_triggers if t.source_oid == oid)


class TestOneCreationIsOneTrigger:
    def test_three_tokens_at_once_is_one_counter(self, builder):
        game, oid = board(builder, STAFF)
        create(game, SPIRIT, 3)
        assert queued(game, oid) == 1
        settle(game)
        assert story(game, oid) == 1
        assert len(oids_of(game, SPIRIT, 0)) == 3

    def test_without_batched_the_same_creation_counts_three(self, builder):
        game, oid = board(builder, GREEDY)
        create(game, SPIRIT, 3)
        settle(game)
        assert story(game, oid) == 3

    def test_two_separate_creations_trigger_twice(self, builder):
        """Not `max_per_turn: 1`: a later creation is a new event."""
        game, oid = board(builder, STAFF)
        create(game, SPIRIT)
        settle(game)
        create(game, SPIRIT, 2)
        settle(game)
        assert story(game, oid) == 2

    def test_each_staff_hears_the_creation(self, builder):
        """Keyed by permanent too, so the batch is not spent by the first."""
        game = (
            builder(players=2).battlefield(0, [STAFF, STAFF]).build(advance=False)
        )
        create(game, SPIRIT, 2)
        settle(game)
        assert [story(game, oid) for oid in oids_of(game, STAFF, 0)] == [1, 1]

    def test_an_opponents_creation_does_not(self, builder):
        """"Whenever **you** create" -- the creator, not the Staff's owner."""
        game, oid = board(builder, STAFF)
        create(game, SPIRIT, 2, controller=1)
        settle(game)
        assert story(game, oid) == 0


class TestADoubledCreationIsStillOne:
    """614.1: "twice that many" replaces the one event; it adds no second one."""

    def test_doubling_season(self, builder):
        game, oid = board(builder, STAFF, "doubling_season")
        create(game, SPIRIT, 2)
        assert len(oids_of(game, SPIRIT, 0)) == 4
        assert queued(game, oid) == 1

    def test_doubling_season_without_batched(self, builder):
        game, oid = board(builder, GREEDY, "doubling_season")
        create(game, SPIRIT, 2)
        assert queued(game, oid) == 4

    def test_a_token_only_doubler_leaves_one_counter(self, builder):
        """Mondrak doubles tokens and not counters, so the count is readable."""
        game, oid = board(builder, STAFF, "mondrak_glory_dominus")
        create(game, SPIRIT)
        settle(game)
        assert len(oids_of(game, SPIRIT, 0)) == 2
        assert story(game, oid) == 1


class TestTheFilterComesFirst:
    def test_a_lone_treasure_does_not_trigger(self, builder):
        game, oid = board(builder, STAFF)
        create(game, TREASURE, 2)
        settle(game)
        assert story(game, oid) == 0

    def test_a_treasure_then_a_spirit_in_one_event_is_one(self, builder):
        """The Treasure is made first and must not spend the batch.

        One simultaneous event of both, the way one effect creating "a Treasure
        and a 1/1 Spirit" is: one batch over separate `create_token` calls.
        """
        game, oid = board(builder, STAFF)
        game.state.event_batch += 1
        create_token(game.state, TREASURE, 0)
        create_token(game.state, SPIRIT, 0)
        create_token(game.state, SPIRIT, 0)
        assert queued(game, oid) == 1
        settle(game)
        assert story(game, oid) == 1


def _probe(event: str) -> CardModel:
    return CardModel.model_validate(
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
                    "trigger": {"event": event, "batched": True},
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestTheLoaderGuard:
    @pytest.mark.parametrize("event", ["token_created", "permanent_enters", "leaves_graveyard"])
    def test_an_event_that_carries_a_batch_loads(self, event):
        card = compile_card(_probe(event))
        assert card.abilities[0].trigger.batched

    @pytest.mark.parametrize("event", ["creature_dies", "draw", "creatures_deal_combat_damage"])
    def test_an_event_without_one_is_refused(self, event):
        """It would load and count every event it was printed to count once."""
        with pytest.raises(DslError, match="'batched' groups"):
            compile_card(_probe(event))
