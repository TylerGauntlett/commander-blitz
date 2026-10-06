"""Sunburst — the first card that reads how a spell was *paid for*.

    "Sunburst (This enters with a +1/+1 counter on it for each color of mana
    spent to cast it.)"

Nothing in the engine could answer this, and the reason is not that the question
is hard: it is that the answer was being **thrown away**. `ManaPool.spend`
decrements six integers in place and returns nothing, so a moment after payment
one blue mana is indistinguishable from another, and `MANA_SPENT` carried only a
total.

Every near miss reads the *cost* instead of the *payment*, and the card that
separates them is the ordinary one — a Sunburst artifact costs `{5}` and has no
coloured pip at all:

| spelling | what it would read |
|---|---|
| `{"x": true}` | the X in the cost, which sunburst cards do not have |
| `mana_symbols` (chroma) | pips printed on cards, which is zero here |
| `count` over lands | permanents, not what was tapped or what it made |

So `spend` now reports the colours it used and `pay_mana` writes them onto the
object. Two details are the keyword rather than plumbing:

- **Mana spent on the generic part counts.** That is the whole of sunburst — a
  `{5}` artifact off five different lands enters with five counters.
- **The record survives the move onto the battlefield**, because the enters
  trigger is what reads it. It follows `cast_x`'s contract, not the
  battlefield-state one that `reset_permanent_state` wipes.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind
from automtg.engine.mana import ManaCost, ManaPool
from automtg.engine.objects import PLUS_ONE
from tests.conftest import action_for_card, only_oid, pass_until

GOLEM = "t_sunburst"      # {5}
BASICS = ["plains", "island", "swamp", "mountain", "forest"]


def pool_with(**amounts) -> ManaPool:
    pool = ManaPool()
    for symbol, n in amounts.items():
        pool.add(symbol, n)
    return pool


def spend(cost: str, **amounts) -> frozenset[str]:
    """Just the colours. `spend` also reports which permanents made the mana --
    see `tests/unit/mana/test_mana_provenance.py` -- and this file is about colour."""
    return pool_with(**amounts).spend(ManaCost.parse(cost).with_x(0)).colors


class TestWhatSpendReports:
    def test_a_coloured_pip_reports_its_colour(self):
        assert spend("{U}", U=1) == {"U"}

    def test_generic_reports_whatever_paid_it(self):
        """The whole of sunburst: a cost with no coloured pip still has colours."""
        assert spend("{2}", G=1, W=1) == {"G", "W"}

    def test_the_same_colour_twice_is_one_colour(self):
        assert spend("{U}{U}", U=2) == {"U"}

    def test_colorless_mana_is_not_a_colour(self):
        assert spend("{2}", C=2) == frozenset()

    def test_a_hybrid_pip_reports_the_half_actually_paid(self):
        """Not both halves — `colors` on the cost says both, and that is a
        different question. Only one was spent."""
        assert spend("{G/U}", U=1) == {"U"}

    def test_a_free_cost_reports_nothing(self):
        assert spend("", ) == frozenset()


class TestOnACard:
    def _cast(self, lands: list[str]):
        return lands

    def test_five_colours_give_five_counters(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, BASICS)
            .hand(0, [GOLEM])
            .library(0, ["forest"] * 20)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, GOLEM))
        pass_until(game, lambda g: not g.state.stack)

        golem = only_oid(game, GOLEM)
        assert game.state.objects[golem].counters.get(PLUS_ONE) == 5

    def test_one_colour_gives_one_counter(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 5)
            .hand(0, [GOLEM])
            .library(0, ["forest"] * 20)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, GOLEM))
        pass_until(game, lambda g: not g.state.stack)

        golem = only_oid(game, GOLEM)
        assert game.state.objects[golem].counters.get(PLUS_ONE) == 1

    def test_two_colours_give_two_counters(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["island"] * 2)
            .hand(0, [GOLEM])
            .library(0, ["forest"] * 20)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, GOLEM))
        pass_until(game, lambda g: not g.state.stack)

        golem = only_oid(game, GOLEM)
        assert game.state.objects[golem].counters.get(PLUS_ONE) == 2

    def test_the_record_survives_onto_the_battlefield(self, builder):
        """The enters trigger reads it, so it must outlive the spell."""
        game = (
            builder(players=2)
            .battlefield(0, BASICS)
            .hand(0, [GOLEM])
            .library(0, ["forest"] * 20)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, GOLEM))
        pass_until(game, lambda g: not g.state.stack)

        golem = only_oid(game, GOLEM)
        assert len(game.state.objects[golem].colors_spent) == 5
