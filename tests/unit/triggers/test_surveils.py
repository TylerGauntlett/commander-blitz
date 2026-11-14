"""Whenever you surveil -- the `surveils` trigger (701.25).

Dimir Spybug ("Whenever you surveil, put a +1/+1 counter on this creature")
and Whispering Snitch ("Whenever you surveil for the first time each turn, ...")
are the witnesses. Surveil is a keyword action, and the cards watch the action,
not the cards it moves:

- `put_into_graveyard` from the library is the near miss, and it is wrong both
  ways. It fires once per card binned, so surveil 2 that bins both would pay
  twice, and a surveil that keeps every card on top moves nothing and is still
  a surveil -- the Spybug grows on it.
- 701.25c: surveil 0 is no surveil event, so nothing triggers on it.
- `max_per_turn: 1` is the near miss for "for the first time each turn", and
  it is wrong the moment the Snitch arrives after you have already surveilled.

So `op_surveil` fires one `SURVEILLED` per surveilling player once the cards
are placed, and the event carries the surveil's ordinal for its player this
turn, counted by the ledger whether or not anything listened.

The claims this file pins:

- **One surveil, one event, after the cards are placed**, whatever was binned;
  surveil 2 is one surveil.
- **Surveil 0 is none**; a surveil of a short or empty library is still one.
- **The surveiller is `player`**: "target player surveils" is theirs, and "you"
  on the trigger is you.
- **The first time each turn is the turn's first**, not the Snitch's.
- The loader accepts `nth` on `surveils`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.events import EventType
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, plus_one_counters, settle

SPYBUG = "dimir_spybug"
SNITCH = "whispering_snitch"
BEAR = "t_bear"


def position(builder, *, mine=(SPYBUG,), library=10):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, [BEAR])
        .library(0, [BEAR] * library)
        .library(1, [BEAR] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def surveil(game, *, amount=1, player="you", controller=0, bin_all=False) -> None:
    """Resolve one surveil outside any spell, keeping every card on top unless
    ``bin_all``."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    spec = {"op": "surveil", "amount": {"const": amount}, "player": player}
    gen = OPS["surveil"](ctx, spec)
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return
        send = list(range(decision.max_count)) if bin_all else []


def resolve(game) -> None:
    """Let queued triggers reach the stack and resolve (see `test_connives`).

    Nothing queued is nothing to do: with an empty stack, passing would walk
    the game into later turns, whose ledgers start again.
    """
    if not game.state.pending_triggers and not game.state.stack:
        return
    game._advance()
    settle(game)


def surveils(game) -> list:
    return [e for e in game.state.events if e.type == EventType.SURVEILLED]


def graveyard(game, pid=0) -> int:
    return len(game.state.players[pid].graveyard)


class TestOneSurveilOneEvent:
    def test_a_surveil_that_keeps_everything_on_top_still_fires(self, builder):
        game = position(builder, mine=())
        surveil(game, amount=2)
        (event,) = surveils(game)
        assert event.player == 0
        assert (event.data["looked"], event.data["binned"]) == (2, 0)
        assert event.data["nth"] == 1
        assert graveyard(game) == 0

    def test_the_event_comes_after_the_cards_are_placed(self, builder):
        game = position(builder, mine=())
        surveil(game, amount=2, bin_all=True)
        (event,) = surveils(game)
        assert event.data["binned"] == 2
        assert graveyard(game) == 2
        kinds = [e.type for e in game.state.events]
        assert EventType.ZONE_CHANGE in kinds[: kinds.index(EventType.SURVEILLED)], (
            "the surveil is finished -- its cards binned -- when it is heard"
        )

    def test_surveil_zero_is_no_surveil(self, builder):
        game = position(builder, mine=())
        surveil(game, amount=0)
        assert surveils(game) == []

    @pytest.mark.parametrize("library", [1, 0])
    def test_a_short_library_is_still_a_surveil(self, builder, library):
        game = position(builder, mine=(), library=library)
        surveil(game, amount=2)
        (event,) = surveils(game)
        assert event.data["looked"] == library

    def test_the_ordinal_is_per_player_and_per_turn(self, builder):
        game = position(builder, mine=())
        surveil(game)
        surveil(game, player="each_opponent")
        surveil(game)
        assert [(e.player, e.data["nth"]) for e in surveils(game)] == [(0, 1), (1, 1), (0, 2)]
        game.state.turn_ledger.clear()  # what cleanup does
        surveil(game)
        assert surveils(game)[-1].data["nth"] == 1


class TestWheneverYouSurveil:
    def test_the_spybug_grows_once_per_surveil(self, builder):
        game = position(builder)
        spybug = only_oid(game, SPYBUG, 0)
        surveil(game, amount=2, bin_all=True)
        resolve(game)
        assert plus_one_counters(game, spybug) == 1, (
            "one surveil of two binned cards is one surveil, not two cards "
            "put into a graveyard"
        )
        surveil(game, amount=1)
        resolve(game)
        assert plus_one_counters(game, spybug) == 2

    def test_surveil_zero_does_not_grow_it(self, builder):
        game = position(builder)
        surveil(game, amount=0)
        resolve(game)
        assert plus_one_counters(game, only_oid(game, SPYBUG, 0)) == 0

    def test_an_opponent_surveilling_does_not_grow_it(self, builder):
        game = position(builder)
        surveil(game, player="each_opponent", controller=0)
        resolve(game)
        assert plus_one_counters(game, only_oid(game, SPYBUG, 0)) == 0


class TestTheFirstTimeEachTurn:
    def life(self, game, pid):
        return game.state.players[pid].life

    def test_the_first_surveil_triggers_and_a_later_one_does_not(self, builder):
        game = position(builder, mine=(SNITCH,))
        mine, theirs = self.life(game, 0), self.life(game, 1)
        surveil(game)
        resolve(game)
        assert (self.life(game, 0), self.life(game, 1)) == (mine + 1, theirs - 1)
        surveil(game)
        resolve(game)
        assert (self.life(game, 0), self.life(game, 1)) == (mine + 1, theirs - 1)

    def test_a_surveil_before_it_arrived_spends_the_first_time(self, builder):
        game = (
            builder(players=2)
            .hand(0, [SNITCH])
            .library(0, [BEAR] * 10)
            .library(1, [BEAR] * 10)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        theirs = self.life(game, 1)
        surveil(game)
        (card,) = game.state.players[0].hand
        move_object(game.state, card, Zone.BATTLEFIELD)
        surveil(game)
        resolve(game)
        assert self.life(game, 1) == theirs, (
            "the turn's first surveil came before the Snitch; a max_per_turn "
            "cap would have fired on the second"
        )


class TestTheLoader:
    def test_nth_loads_on_surveils(self):
        compile_card(
            CardModel.model_validate(
                {
                    "id": "t_surveil_watcher",
                    "name": "Surveil Watcher",
                    "oracle_text": "x",
                    "types": ["Creature"],
                    "power": 1,
                    "toughness": 1,
                    "abilities": [
                        {
                            "kind": "triggered",
                            "text": "x",
                            "trigger": {"event": "surveils", "controller": "you", "nth": 1},
                            "effects": [{"op": "gain_life", "amount": {"const": 1}}],
                        }
                    ],
                }
            )
        )
