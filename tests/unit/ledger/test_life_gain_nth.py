""""Whenever you gain life for the first time each turn" -- `nth` on `you_gain_life`.

    Vanguard Seraph -- "Flying. Whenever you gain life for the first time each
    turn, surveil 1."

The ordinal is the same tool as "your second card each turn" on `draw` and
"their first spell" on `spell_cast`: a queue-time restriction read off the
event. `LIFE_GAINED` now carries ``nth``, folded off `TurnLedger.life_gains`
(a count of gain *events*, not of life) in the same ledger pass that stamps a
cast's ordinal.

The two near misses each fail a test below. `max_per_turn: 1` is counted per
permanent from when it arrived, so a Seraph that entered after the turn's first
gain would trigger on the second. A condition on `life_gained_this_turn` reads
a total after the gain, which cannot tell one gain of 4 from four gains of 1.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import gain_life
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until, settle

SERAPH = "t_flg_seraph"


def board(builder, mine=(SERAPH,)):
    return builder(players=2).battlefield(0, list(mine)).library(0, ["plains"] * 20).build()


def drawn(game, *amounts: int, pid: int = 0) -> int:
    before = len(game.state.players[0].hand)
    for amount in amounts:
        gain_life(game.state, pid, amount)
        settle(game)
    return len(game.state.players[0].hand) - before


class TestTheFirstGainOnly:
    def test_the_first_gain_triggers_it(self, builder):
        game = board(builder)
        assert drawn(game, 3) == 1

    def test_later_gains_the_same_turn_do_not(self, builder):
        game = board(builder)
        assert drawn(game, 1, 1, 1) == 1

    def test_an_opponents_gain_does_not(self, builder):
        game = board(builder)
        assert drawn(game, 3, pid=1) == 0

    def test_it_resets_on_the_next_turn(self, builder):
        game = board(builder)
        assert drawn(game, 1) == 1
        pass_until(game, lambda g: g.state.active_player == 1)
        assert drawn(game, 1) == 1


class TestTheFirstGainIsTheTurnsNotThePermanents:
    def test_a_seraph_arriving_after_the_first_gain_waits_for_next_turn(self, builder):
        """The case `max_per_turn: 1` gets wrong: the turn's first gain has gone."""
        game = builder(players=2).hand(0, [SERAPH]).library(0, ["plains"] * 20).build()
        gain_life(game.state, 0, 2)
        settle(game)
        move_object(game.state, only_oid_in_hand(game, SERAPH), Zone.BATTLEFIELD)
        settle(game)
        assert drawn(game, 2) == 0


class TestTheLoader:
    def _card(self, event: str) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {"kind": "triggered", "text": "probe", "trigger": {"event": event, "nth": 1},
                     "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}]}
                ],
            }
        )

    def test_nth_loads_on_you_gain_life(self):
        compile_card(self._card("you_gain_life"))

    def test_nth_is_still_refused_on_an_event_with_no_ordinal(self):
        with pytest.raises(DslError, match="nth"):
            compile_card(self._card("upkeep"))


def only_oid_in_hand(game, card_id: str) -> int:
    return next(oid for oid in game.state.players[0].hand if game.state.objects[oid].def_id == card_id)
