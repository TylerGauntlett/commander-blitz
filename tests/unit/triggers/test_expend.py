"""Expend: "Whenever you expend 4, …"

    Pyreswipe Hawk — "Whenever you expend 4, this creature gets +1/+0 and gains
    flying until end of turn. (You expend 4 as you spend your fourth total mana
    to cast spells during a turn.)"

The reminder text is the specification, and every word of it is a boundary:

- **"your fourth total mana"** — a running total for the turn, so one 5-mana
  spell expends 4, and so do a 2-mana spell followed by another. The trigger is
  the *crossing*: the payment that takes the total from below N to N or more.
  It fires at most once a turn per N, however much more is spent after.
- **"to cast spells"** — every payment toward a cast counts, the kicker
  included (601.2f folds additional costs into the total cost), and nothing
  else does: an activated ability's {4} expends nothing.
- **"during a turn"** — the total starts again each turn.

A spell cast without paying its mana cost spends no mana, so it expends
nothing. Trailtracker Scout's "expend 8" is the same trigger with a larger N.

The near misses are both wrong. A `condition` on a per-turn total would be
re-asked on resolution (603.4) after a later spell had moved the total; and a
trigger on every spell with `max_per_turn: 1` would fire for a permanent that
arrived *after* the fourth mana was spent. So `expend` is a queue-time crossing,
read off the MANA_SPENT a cast's payment fires — the comparison `nth` already
makes on `counter_placed`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.suspend import cast_for_free
from commanderblitz.engine.zones import move_object
from tests.conftest import (
    activations,
    find_action,
    only_oid,
    pass_until,
    plus_one_counters,
    settle_completely,
)

FOUR = "t_expend_four"  # whenever you expend 4, a +1/+1 counter
EIGHT = "t_expend_eight"  # whenever you expend 8, a +1/+1 counter
TWO = "t_expend_two"  # {2} instant
FIVE = "t_expend_five"  # {5} instant
KICKED = "t_expend_kicked"  # {1} instant, kicker {3}
ROCK = "t_expend_rock"  # artifact, "{4}: you gain 1 life"
ANCHOR = "t_plain_instant"  # {W}; a reason for priority to stop before cleanup


def position(builder, watcher=FOUR, *, hand=(), extra=(), mountains=14):
    """``watcher`` and a pile of mountains on your side, ``hand`` in hand.

    The opponent holds `ANCHOR` with a Plains to cast it, so auto-pass stops at
    their priority instead of running the turn out to cleanup -- which clears
    the ledger this test reads.
    """
    game = (
        builder(players=2)
        .battlefield(0, [watcher, *extra, *["mountain"] * mountains])
        .battlefield(1, ["plains"])
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .hand(0, list(hand))
        .hand(1, [ANCHOR])
        .build()
    )
    return game, only_oid(game, watcher, 0)


def cast(game, card_id: str, *, kicked: bool = False) -> None:
    """Cast the first ``card_id`` in hand and let everything resolve."""
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)
    game.apply(find_action(game, ActionKind.CAST, source=oid, kicked=kicked))
    settle_completely(game)


def spent(game) -> int:
    return game.state.turn_ledger.mana_spent_on_spells.get(0, 0)


class TestTheCrossing:
    def test_one_spell_that_crosses_four_fires_it(self, builder):
        """2 -> 5 is not "the fourth mana" by itself; 0 -> 5 includes it."""
        game, hawk = position(builder, hand=[FIVE])
        cast(game, FIVE)
        assert spent(game) == 5
        assert plus_one_counters(game, hawk) == 1

    def test_two_spells_together_cross_it(self, builder):
        game, hawk = position(builder, hand=[TWO, TWO])
        cast(game, TWO)
        assert plus_one_counters(game, hawk) == 0, "two mana is not four"
        cast(game, TWO)
        assert plus_one_counters(game, hawk) == 1, "the second spell spends the fourth"

    def test_it_fires_once_a_turn_however_much_more_is_spent(self, builder):
        game, hawk = position(builder, hand=[FIVE, FIVE, TWO])
        cast(game, FIVE)
        cast(game, FIVE)
        cast(game, TWO)
        assert spent(game) == 12
        assert plus_one_counters(game, hawk) == 1

    def test_expend_eight_waits_for_the_eighth(self, builder):
        """Trailtracker Scout's N. Five, then five more: 5 -> 10 crosses 8."""
        game, scout = position(builder, EIGHT, hand=[FIVE, FIVE])
        cast(game, FIVE)
        assert plus_one_counters(game, scout) == 0
        cast(game, FIVE)
        assert plus_one_counters(game, scout) == 1

    def test_two_ns_on_one_payment_each_fire(self, builder):
        """One payment can cross several N at once; each is its own trigger."""
        game, hawk = position(builder, hand=[FIVE, FIVE], extra=[EIGHT])
        scout = only_oid(game, EIGHT, 0)
        cast(game, FIVE)
        cast(game, FIVE)
        assert plus_one_counters(game, hawk) == 1
        assert plus_one_counters(game, scout) == 1


class TestWhatCountsAsSpendingToCast:
    def test_the_kicker_counts(self, builder):
        """{1} plus kicker {3} is four mana spent to cast one spell."""
        game, hawk = position(builder, hand=[KICKED])
        cast(game, KICKED, kicked=True)
        assert spent(game) == 4
        assert plus_one_counters(game, hawk) == 1

    def test_unkicked_it_is_one_mana(self, builder):
        game, hawk = position(builder, hand=[KICKED])
        cast(game, KICKED)
        assert spent(game) == 1
        assert plus_one_counters(game, hawk) == 0

    def test_an_activated_ability_expends_nothing(self, builder):
        """"…to cast spells": the rock's {4} is spent on an ability."""
        game, hawk = position(builder, extra=[ROCK])
        rock = only_oid(game, ROCK, 0)
        game.apply(activations(game, rock)[0])
        settle_completely(game)
        assert spent(game) == 0
        assert plus_one_counters(game, hawk) == 0

    def test_ability_mana_does_not_start_the_count(self, builder):
        """After the rock's {4}, a {2} spell is still only the second mana."""
        game, hawk = position(builder, hand=[TWO], extra=[ROCK])
        game.apply(activations(game, only_oid(game, ROCK, 0))[0])
        settle_completely(game)
        cast(game, TWO)
        assert spent(game) == 2
        assert plus_one_counters(game, hawk) == 0

    def test_a_free_cast_spends_nothing(self, builder):
        """Cast without paying its mana cost: a cast, and zero mana."""
        game, hawk = position(builder, hand=[FIVE])
        state = game.state
        oid = state.players[0].hand[0]
        move_object(state, oid, Zone.EXILE)
        assert cast_for_free(state, 0, oid)
        settle_completely(game)
        assert any(e.type == "spell_cast" for e in state.events)
        assert spent(game) == 0
        assert plus_one_counters(game, hawk) == 0


class TestWhoseMana:
    def test_an_opponents_spells_do_not_expend_yours(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOUR, "plains"])
            .battlefield(1, ["mountain"] * 6)
            .library(0, ["mountain"] * 20)
            .library(1, ["mountain"] * 20)
            .hand(0, [ANCHOR])
            .hand(1, [FIVE])
            .build()
        )
        hawk = only_oid(game, FOUR, 0)
        pass_until(
            game,
            lambda g: g.pending() is not None
            and g.pending().player == 1
            and any(a.kind is ActionKind.CAST for a in g.legal_actions()),
        )
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CAST))
        settle_completely(game)
        assert game.state.turn_ledger.mana_spent_on_spells.get(1) == 5
        assert plus_one_counters(game, hawk) == 0


class TestTheTurnBoundary:
    def test_the_total_starts_again_next_turn(self, builder):
        """"During a turn": four on this turn, four more on the next one."""
        game, hawk = position(builder, hand=[FIVE, FIVE])
        cast(game, FIVE)
        assert plus_one_counters(game, hawk) == 1
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.turn > turn
            and g.pending() is not None
            and g.pending().kind is DecisionKind.PRIORITY
            and g.pending().player == 0
            and any(a.kind is ActionKind.CAST for a in g.legal_actions()),
        )
        assert spent(game) == 0, "the ledger is cleared at cleanup"
        cast(game, FIVE)
        assert plus_one_counters(game, hawk) == 2


class TestTheLoader:
    """The N is the whole trigger, so a card without one is refused at load."""

    def _card(self, **trigger):
        return {
            "id": "t_expend_probe",
            "name": "Expend Probe",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "expend", **trigger},
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }

    def test_expend_with_an_n_loads(self):
        card = compile_card(CardModel.model_validate(self._card(nth=4)))
        assert card.abilities[0].trigger.nth == 4

    def test_expend_without_an_n_is_refused(self):
        with pytest.raises(DslError, match="needs 'nth'"):
            compile_card(CardModel.model_validate(self._card()))

    def test_a_zeroth_mana_is_refused(self):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(self._card(nth=0)))

    def test_a_filter_is_refused(self):
        """A payment has no subject, so the filter would never match."""
        with pytest.raises(DslError, match="no subject"):
            compile_card(
                CardModel.model_validate(self._card(nth=4, filter={"types": ["Creature"]}))
            )
