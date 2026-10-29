"""The placement that puts the Nth counter of a kind on a permanent.

    "Whenever you draw a card, put a +1/+1 counter on Shang-Chi. When **the
    tenth +1/+1 counter is put on** Shang-Chi, you draw five cards and gain 5
    life."                                 -- Shang-Chi and the Ten Rings

`counter_placed` fires on every placement, and its payload carried only the
amount. Every near miss fires on the wrong placements: a ``counters_on >= 10``
condition fires again on the eleventh counter and every one after it, and a
state trigger (603.8) fires on the count *holding*, not on the tenth counter
arriving. ``nth`` on a `counter_placed` trigger with a ``counter`` asks the
question the printed line asks: did this placement carry the count of that kind
across N? ``before < N <= before + amount``, with ``before`` the count just
before it, now on the event.

What each reading rests on, and each has a test class:

- **The crossing.** It is the comparison 714.2c makes for a Saga's chapter
  ("becomes greater than or equal to the chapter number, and ... was less ...
  before"), the only rule that defines the Nth counter arriving. One placement
  of three counters onto eight crosses ten once; a placement onto ten or more
  crosses nothing; a single placement of ten or more onto none crosses it.
  ``amount`` is what really arrived (122.6, after replacements), so Hardened
  Scales turning one into two takes eight to ten.
- **The kind.** "+1/+1 counter" counts that kind only, so the loader refuses
  ``nth`` without ``counter``: ten counters of mixed kinds are the tenth of
  none.
- **Counters removed and put back.** The count is the counters on the object
  now, not a lifetime tally: the plain reading of "the tenth +1/+1 counter is
  put on" is a placement that makes it have ten, and 714.2c triggers a chapter
  again the same way. Removed to nine and given one, it triggers again. So
  does 704.5q: a -1/-1 counter on a ten-counter Shang-Chi annihilates one
  +1/+1 counter, and the next +1/+1 counter is the tenth again. The -1/-1
  counter itself is not the kind and crosses nothing.
- **An arrival.** 122.6: counters a permanent enters with were put on it, so
  entering with ten fires it (`zones._fire_entered_with_counters` reports
  ``before`` as what it carried in, nought). A permanent that leaves and
  returns is a new object (400.7) whose count starts again.
- **No loop.** Drawing five puts five more counters on, ten to fifteen, which
  crosses nothing: one tenth counter is one trigger.

Shang-Chi and the Ten Rings is the witness; `t_ncp_rings` in
`tests/data/nth_counter_placed.cards.json` is its two triggers on a {G} 1/1, and
`t_ncp_charge` watches the third charge counter.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, draw_cards, remove_counters
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, settle

RINGS = "t_ncp_rings"  # +1/+1 counter per draw; tenth +1/+1: draw five, gain 5
RELIC = "t_ncp_charge"  # third charge counter: gain 3
SCALES = "t_rc_scales"  # +1/+1 counters on your creatures: that many plus one
PLUS = "+1/+1"


def position(builder, *, counters: int = 0, extra=()):
    """Player 0 with the Rings (``counters`` +1/+1 on it) and ``extra``.

    Returns ``(game, rings)``, in player 0's precombat main, with a library to
    draw from.
    """
    b = builder(players=2)
    b = b.battlefield(0, [RINGS], counters={PLUS: counters} if counters else None)
    b = b.battlefield(0, list(extra)).library(0, ["forest"] * 40)
    game = b.build()
    return game, only_oid(game, RINGS, 0)


def queued(game) -> int:
    return len(game.state.pending_triggers)


def plus(game, oid: int) -> int:
    return game.state.objects[oid].counter(PLUS)


class TestTheCrossing:
    def test_the_tenth_counter_triggers(self, builder):
        game, rings = position(builder, counters=9)
        add_counters(game.state, rings, PLUS, 1, by=0)
        assert queued(game) == 1

    @pytest.mark.parametrize("have", [0, 5, 8])
    def test_below_ten_does_not(self, builder, have):
        game, rings = position(builder, counters=have)
        add_counters(game.state, rings, PLUS, 9 - have, by=0)
        assert plus(game, rings) == 9
        assert queued(game) == 0

    def test_one_placement_across_ten_triggers_once(self, builder):
        game, rings = position(builder, counters=8)
        add_counters(game.state, rings, PLUS, 3, by=0)
        assert plus(game, rings) == 11
        assert queued(game) == 1

    def test_ten_at_once_onto_none_is_the_tenth(self, builder):
        game, rings = position(builder)
        add_counters(game.state, rings, PLUS, 12, by=0)
        assert queued(game) == 1

    @pytest.mark.parametrize("have", [10, 11, 15])
    def test_past_ten_crosses_nothing(self, builder, have):
        game, rings = position(builder, counters=have)
        add_counters(game.state, rings, PLUS, 1, by=0)
        add_counters(game.state, rings, PLUS, 4, by=0)
        assert queued(game) == 0

    def test_the_amount_is_what_arrived_after_replacements(self, builder):
        """Hardened Scales turns one into two (122.6), so eight becomes ten."""
        game, rings = position(builder, counters=8, extra=(SCALES,))
        add_counters(game.state, rings, PLUS, 1, by=0)
        assert plus(game, rings) == 10
        assert queued(game) == 1

    def test_it_resolves_as_printed(self, builder):
        game, rings = position(builder, counters=9)
        life = game.state.players[0].life
        hand = len(game.state.players[0].hand)
        add_counters(game.state, rings, PLUS, 1, by=0)
        settle(game)
        assert game.state.players[0].life == life + 5
        # Five drawn, and each draw put a counter on: ten to fifteen.
        assert len(game.state.players[0].hand) == hand + 5
        assert plus(game, rings) == 15


class TestTheKind:
    def test_another_kind_on_the_rings_does_not_count(self, builder):
        game, rings = position(builder, counters=9)
        add_counters(game.state, rings, "charge", 5, by=0)
        add_counters(game.state, rings, "-1/-1", 1, by=0)
        assert queued(game) == 0

    def test_the_named_kind_is_the_one_counted(self, builder):
        game = builder(players=2).battlefield(0, [RELIC]).build()
        relic = only_oid(game, RELIC, 0)
        add_counters(game.state, relic, PLUS, 5, by=0)
        add_counters(game.state, relic, "charge", 2, by=0)
        assert queued(game) == 0
        add_counters(game.state, relic, "charge", 1, by=0)
        assert queued(game) == 1

    def test_nth_without_a_counter_is_refused(self):
        card = {
            "id": "t_ncp_bad",
            "name": "Test Kindless Counter",
            "oracle_text": "When the tenth counter is put on this creature, draw a card.",
            "mana_cost": "{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "When the tenth counter is put on this creature, draw a card.",
                    "trigger": {"event": "counter_placed", "source": "self", "nth": 10},
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
        with pytest.raises(DslError, match="needs 'counter'"):
            compile_card(CardModel.model_validate(card))
        card["abilities"][0]["trigger"]["counter"] = PLUS
        compile_card(CardModel.model_validate(card))
        card["abilities"][0]["trigger"]["nth"] = 0
        with pytest.raises(DslError, match="ordinal from 1"):
            compile_card(CardModel.model_validate(card))


class TestRemovedAndPutBack:
    def test_back_below_ten_and_up_again_triggers_again(self, builder):
        game, rings = position(builder, counters=10)
        remove_counters(game.state, rings, PLUS, 1)
        add_counters(game.state, rings, PLUS, 1, by=0)
        assert queued(game) == 1

    def test_a_minus_one_counter_annihilates_one_and_the_next_is_tenth_again(self, builder):
        """704.5q: ten +1/+1 and one -1/-1 become nine and none."""
        game, rings = position(builder, counters=10)
        add_counters(game.state, rings, "-1/-1", 1, by=1)
        sba.run(game.state)
        assert plus(game, rings) == 9
        assert queued(game) == 0
        add_counters(game.state, rings, PLUS, 1, by=0)
        assert queued(game) == 1


class TestAnArrival:
    def test_entering_with_ten_is_the_tenth_put_on(self, builder):
        game, rings = position(builder)
        move_object(game.state, rings, Zone.EXILE)
        move_object(game.state, rings, Zone.BATTLEFIELD, enters_with={PLUS: 10})
        assert plus(game, rings) == 10
        assert queued(game) == 1

    def test_entering_with_nine_is_not(self, builder):
        game, rings = position(builder)
        move_object(game.state, rings, Zone.EXILE)
        move_object(game.state, rings, Zone.BATTLEFIELD, enters_with={PLUS: 9})
        assert queued(game) == 0

    def test_a_new_object_counts_again_from_nought(self, builder):
        """400.7: the counters stay behind, so the new Rings' tenth is a tenth."""
        game, rings = position(builder, counters=12)
        move_object(game.state, rings, Zone.EXILE)
        move_object(game.state, rings, Zone.BATTLEFIELD)
        assert plus(game, rings) == 0
        add_counters(game.state, rings, PLUS, 9, by=0)
        assert queued(game) == 0
        add_counters(game.state, rings, PLUS, 1, by=0)
        assert queued(game) == 1


class TestNoLoop:
    def test_the_ninth_to_tenth_draw_fires_once_and_settles(self, builder):
        """The tenth counter draws five, which puts five more on: ten to fifteen
        crosses nothing, so the chain stops after one tenth-counter trigger."""
        game, rings = position(builder, counters=9)
        life = game.state.players[0].life
        hand = len(game.state.players[0].hand)
        draw_cards(game.state, 0, 1)
        settle(game)
        assert plus(game, rings) == 15
        assert len(game.state.players[0].hand) == hand + 6
        assert game.state.players[0].life == life + 5
