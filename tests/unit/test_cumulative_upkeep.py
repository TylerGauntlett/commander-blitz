"""Cumulative upkeep — the only mana cost that is not fixed when the card is written.

    "Cumulative upkeep {1} (At the beginning of your upkeep, put an age counter
    on this permanent, then sacrifice it unless you pay its upkeep cost for each
    age counter on it.)"

The upkeep trigger, the age counters and "sacrifice it unless you pay" all
existed — `may` has taken a `pay` since Seer's Sundial and an `else` since the
Karoo lands. What did not exist is a **price that moves**: every other cost in
the engine is settled when the card loads or when legality offers an action, and
this one is a multiple of a counter the same ability just placed.

So `pay` grew a `times`, evaluated where the cost is charged. That location is
forced: an activated ability's cost is settled by legality *before* any effect
has run, so a value expression there would have nothing to read. `may`'s `pay`
is the one cost charged mid-resolution, with an `EffectContext` in hand.

The multiplication is of **every** part of the cost, which is the thing that
would be silently wrong: `{1}{U}` at three age counters is `{3}{U}{U}{U}`, and
scaling only the generic half gives `{3}{U}` — a card that gets cheaper the
longer it lives, relative to what it prints.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, _validate_effect
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.mana import ManaCost
from tests.conftest import _default_answer, find_action, only_oid

ISLAND = "island"
WALL = "t_cumulative"


def position(builder, lands: int):
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * lands)
        .battlefield(0, [WALL])
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
        .build()
    ), None


def to_upkeep_question(game, *, until_turn: int):
    """Run until the cumulative upkeep is offered, or the turn limit passes."""
    for _ in range(800):
        decision = game.pending()
        if decision is None or game.state.turn > until_turn:
            return None
        if any(a.kind is ActionKind.YES for a in game.legal_actions()):
            return decision
        game.apply(_default_answer(game, decision))
    return None


class TestTheScaling:
    def test_one_counter_charges_once(self):
        assert ManaCost.parse("{1}").scaled(1).mana_value() == 1

    def test_three_counters_charge_three_times(self):
        assert ManaCost.parse("{1}").scaled(3).mana_value() == 3

    def test_it_multiplies_the_coloured_pips_too(self):
        """`{1}{U}` at three is `{3}{U}{U}{U}`, not `{3}{U}`."""
        scaled = ManaCost.parse("{1}{U}").scaled(3)
        assert scaled.generic == 3
        assert scaled.symbols_of("U") == 3
        assert scaled.mana_value() == 6

    def test_hybrid_pips_are_repeated_not_summed(self):
        """Each pip is its own choice of which half to pay."""
        scaled = ManaCost.parse("{G/U}").scaled(2)
        assert len(scaled.hybrid) == 2
        assert scaled.mana_value() == 2

    def test_zero_charges_nothing(self):
        assert ManaCost.parse("{1}{U}").scaled(0).mana_value() == 0


class TestOnTheBoard:
    def test_the_first_upkeep_costs_one(self, builder):
        game, _ = position(builder, lands=1)
        wall = only_oid(game, WALL)

        assert to_upkeep_question(game, until_turn=4) is not None
        game.apply(find_action(game, ActionKind.YES))

        assert game.state.objects[wall].counters.get("age") == 1
        assert game.state.objects[wall].zone is Zone.BATTLEFIELD

    def test_it_is_not_offered_when_the_price_has_outgrown_the_board(self, builder):
        """One Island cannot pay a second age counter, so it is not asked at all.

        `may` does not offer a cost the player cannot afford (rule 118.4), so the
        `else` runs and the Wall is sacrificed -- which is the printed card, and
        is only visible because the price grew past what the board can pay.
        """
        game, _ = position(builder, lands=1)
        wall = only_oid(game, WALL)
        to_upkeep_question(game, until_turn=4)
        game.apply(find_action(game, ActionKind.YES))

        # The next of your upkeeps places a second counter and charges {2}.
        assert to_upkeep_question(game, until_turn=9) is None, "cannot afford it"
        assert game.state.objects[wall].zone is Zone.GRAVEYARD

    def test_a_deeper_board_keeps_paying(self, builder):
        game, _ = position(builder, lands=6)
        wall = only_oid(game, WALL)

        for _ in range(2):
            assert to_upkeep_question(game, until_turn=9) is not None
            game.apply(find_action(game, ActionKind.YES))

        assert game.state.objects[wall].counters.get("age") == 2
        assert game.state.objects[wall].zone is Zone.BATTLEFIELD


class TestTheGuards:
    def _may(self, pay: dict) -> dict:
        return {"op": "may", "pay": pay, "else": [{"op": "draw", "player": "you"}]}

    def test_a_well_formed_times_loads(self):
        _validate_effect(
            self._may({"mana": "{1}", "times": {"const": 2}}), "test", {}
        )

    def test_times_with_no_mana_is_refused(self):
        """It multiplies the mana half, so with none it multiplies nothing."""
        with pytest.raises(DslError, match="multiplies the mana cost"):
            _validate_effect(self._may({"pay_life": 1, "times": {"const": 2}}), "test", {})

    def test_a_malformed_times_is_refused(self):
        with pytest.raises(DslError, match="unknown value keys"):
            _validate_effect(
                self._may({"mana": "{1}", "times": {"nonsense": True}}), "test", {}
            )
