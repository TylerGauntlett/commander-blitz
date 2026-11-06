"""Every "+X/+Y" / "-X/-Y" counter changes power and toughness, not only +1/+1.

    "Defender. Put a **-0/-1 counter** on this creature: Add {G}. Activate
    only once each turn."                                    -- Wall of Roots

Rule 613.4c: in layer 7c, "effects from counters" are every counter of the form
+X/+Y or -X/-Y (122.1a), not just the two kinds that have names in the
engine. Without it a -0/-1 counter is an inert tally, and the wall taps for {G}
every turn at no cost at all, never shrinking and never dying. Writing it as a
-1/-1 counter instead is the near miss: power changes too and the counter
annihilates with a +1/+1 counter. 704.5q's annihilation is the one place the
pair is special, and it stays limited to exactly +1/+1 and -1/-1; a "+1/+0"
and a "-0/-1" sit side by side.

Each spelling is its own counter kind (122.1), so "-0/-1" is read off its exact
spelling and the loader refuses a near miss ("-0/-1 counter", "0/-1", a
typographic minus) the way it refuses "Shield".
"""

from __future__ import annotations

import re

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import pt_counter
from commanderblitz.engine.primitives import add_counters
from tests.conftest import only_oid, pass_until, pt

WALL = "t_ptc_wall"
BEAR = "t_ptc_bear"


def position(builder, card_id: str = WALL):
    """``card_id`` for seat 0 in a main phase, holding priority.

    The instant in hand and a Plains to cast it keep seat 0 from auto-passing,
    so `legal_actions()` is seat 0's list and the wall's ability is offered
    when it should be.
    """
    game = (
        builder(players=2)
        .battlefield(0, [card_id, "plains"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .hand(0, ["t_plain_instant"])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, card_id, 0)


def offers(game, oid) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid]


def tap_wall(game, oid) -> None:
    game.apply(offers(game, oid)[0])
    pass_until(game, lambda g: g.pending() is None or g.pending().kind is DecisionKind.PRIORITY)


def next_own_main(game) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn > turn + 1
        and g.state.active_player == 0
        and g.state.step is Step.PRECOMBAT_MAIN,
    )


class TestTheSpelling:
    @pytest.mark.parametrize(
        ("kind", "delta"),
        [("+1/+1", (1, 1)), ("-1/-1", (-1, -1)), ("-0/-1", (0, -1)), ("+1/+0", (1, 0)),
         ("+2/+2", (2, 2)), ("-2/-1", (-2, -1))],
    )
    def test_a_signed_pair_is_a_pt_counter(self, kind, delta):
        assert pt_counter(kind) == delta

    @pytest.mark.parametrize("kind", ["charge", "0/-1", "-0/-1 counter", "+1/+1/+1", "shield"])
    def test_anything_else_is_not(self, kind):
        assert pt_counter(kind) is None


class TestTheCountersLayer:
    def test_a_minus_zero_minus_one_counter_lowers_only_toughness(self, builder):
        game, oid = position(builder, BEAR)
        add_counters(game.state, oid, "-0/-1", 1)
        assert pt(game, oid) == (2, 1)

    def test_a_plus_one_plus_zero_counter_raises_only_power(self, builder):
        game, oid = position(builder, BEAR)
        add_counters(game.state, oid, "+1/+0", 2)
        assert pt(game, oid) == (4, 2)

    def test_kinds_add_up(self, builder):
        game, oid = position(builder, BEAR)
        add_counters(game.state, oid, "+1/+1", 1)
        add_counters(game.state, oid, "-0/-1", 2)
        add_counters(game.state, oid, "+2/+2", 1)
        assert pt(game, oid) == (5, 3)

    def test_a_non_pt_kind_stays_inert(self, builder):
        game, oid = position(builder, BEAR)
        add_counters(game.state, oid, "charge", 3)
        assert pt(game, oid) == (2, 2)


class TestAnnihilationIsOnlyThePair:
    """704.5q names +1/+1 and -1/-1 counters, and nothing else."""

    def test_plus_one_and_minus_one_still_annihilate(self, builder):
        game, oid = position(builder, BEAR)
        add_counters(game.state, oid, "+1/+1", 2)
        add_counters(game.state, oid, "-1/-1", 1)
        sba.run(game.state)
        counters = game.state.objects[oid].counters
        assert (counters.get("+1/+1"), counters.get("-1/-1")) == (1, None)

    def test_other_kinds_sit_side_by_side(self, builder):
        game, oid = position(builder, BEAR)
        add_counters(game.state, oid, "+1/+0", 1)
        add_counters(game.state, oid, "-0/-1", 1)
        add_counters(game.state, oid, "+1/+1", 1)
        sba.run(game.state)
        counters = game.state.objects[oid].counters
        assert (counters["+1/+0"], counters["-0/-1"], counters["+1/+1"]) == (1, 1, 1)
        assert pt(game, oid) == (4, 2)


class TestWallOfRoots:
    def test_paying_shrinks_the_wall_and_makes_green(self, builder):
        game, oid = position(builder)
        tap_wall(game, oid)
        assert pt(game, oid) == (0, 4)
        assert game.state.players[0].mana_pool.total() == 1

    def test_only_once_each_turn(self, builder):
        game, oid = position(builder)
        tap_wall(game, oid)
        assert not offers(game, oid)

    def test_the_counters_stay_across_turns(self, builder):
        game, oid = position(builder)
        tap_wall(game, oid)
        next_own_main(game)
        assert pt(game, oid) == (0, 4)
        tap_wall(game, oid)
        assert pt(game, oid) == (0, 3)

    def test_the_fifth_counter_kills_it(self, builder):
        """704.5f: toughness 0 is death, and the cost is already paid."""
        game, oid = position(builder)
        add_counters(game.state, oid, "-0/-1", 4)
        tap_wall(game, oid)
        assert game.state.objects[oid].zone is not Zone.BATTLEFIELD
        assert game.state.players[0].mana_pool.total() == 1


def _artifact(counter: str) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Probe.",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "text": "Probe.",
                    "cost": {"tap": True, "put_counters": {"counter": counter}},
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestLoaderRefusals:
    @pytest.mark.parametrize(
        ("kind", "canonical"),
        [("-0/-1 counter", "-0/-1"), ("0/-1", "+0/-1"), ("\u22120/\u22121", "-0/-1"),
         ("+1/+1 counters", "+1/+1"), ("1/1", "+1/+1")],
    )
    def test_a_near_miss_pt_counter_is_refused(self, kind, canonical):
        with pytest.raises(DslError, match=re.escape(f"write a P/T counter as '{canonical}'")):
            compile_card(_artifact(kind))

    @pytest.mark.parametrize("kind", ["-0/-1", "+1/+0", "+1/+1", "page"])
    def test_the_exact_spelling_loads(self, kind):
        compile_card(_artifact(kind))
