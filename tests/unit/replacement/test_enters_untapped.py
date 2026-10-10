"""A trigger that reads how a permanent *arrived* — "enters untapped".

Charismatic Conqueror: "Whenever an artifact or creature an opponent controls
enters **untapped**, they may tap that permanent. If they don't, you create a
1/1 white Vampire creature token with lifelink."

This is the one clause in `matches_card_filter` that reads object *state* rather
than a printed characteristic, and it is sound for the reason the rest of that
function is not: a trigger filter is evaluated **once, when the ability is
collected**, and `zones._enter_battlefield` writes `obj.tapped` before it fires
ENTERS_BATTLEFIELD. At match time the flag is the permanent's arrival state,
which is exactly what the printed line asks about.

**Before this, the key loaded and was silently dropped.** `validate_selector`
accepts `tapped` because it is in `SELECTOR_KEYS`, and `matches_card_filter`
read controller, zone, types, colors, keywords, power, toughness and several
relationships — but never `tapped`. So a card written the obvious way compiled
clean, printed its "untapped" clause, and triggered on permanents entering
tapped as well: strictly wider than printed, which is the dangerous direction,
and invisible to every authoring gate. `t_loose_conqueror` is that card, kept
here so the pair proves the clause is doing work.

**Why not a trigger `condition`.** It reads the right state at queue time, but
603.4 re-checks a condition on resolution, which inverts the card's own ruling:
an opponent who taps the fresh artifact in response would make the ability do
nothing, when the printed card gives you the token precisely when they cannot
tap it.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

UNTAPPED = "t_untapped_conqueror"  # fires only on an untapped arrival
LOOSE = "t_loose_conqueror"  # no `tapped` clause -- fires on either
TAPPED = "t_tapped_conqueror"  # the opposite question
ARRIVAL = "t_bear"  # a creature for the opponent to play


def board(builder, watcher: str):
    """``watcher`` on your battlefield; the opponent has a creature in hand."""
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 4 + [watcher])
        .hand(1, [ARRIVAL])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def arrive(game, *, tapped: bool) -> None:
    """Put the opponent's creature onto the battlefield, tapped or not.

    `move_object` rather than casting it: the card under test is about *how* a
    permanent arrived, and this is the one lever that sets that directly. It is
    the same path a cast goes through -- `_enter_battlefield` writes `tapped`
    and then fires ENTERS_BATTLEFIELD, which is where the filter is asked.
    """
    oid = game.state.players[1].hand[0]
    move_object(game.state, oid, Zone.BATTLEFIELD, to_player=1, tapped=tapped)
    # Not `pass_until(not stack)`: the arrival only *queues* the trigger, so the
    # stack is still empty when that predicate is first checked and `pass_until`
    # returns before anything has happened. Waiting for the queue to drain AND
    # the stack to empty is the state where the ability has either resolved or
    # was never collected -- which is exactly the distinction under test.
    pass_until(
        game, lambda g: not g.state.pending_triggers and not g.state.stack, limit=40
    )


def life_gained(game, before: int) -> int:
    return game.state.players[0].life - before


class TestTheClauseIsRead:
    def test_an_untapped_arrival_triggers(self, builder):
        game = board(builder, UNTAPPED)
        before = game.state.players[0].life
        arrive(game, tapped=False)
        assert life_gained(game, before) == 1

    def test_a_tapped_arrival_does_not(self, builder):
        """The whole card. Before the fix this gained 1 as well."""
        game = board(builder, UNTAPPED)
        before = game.state.players[0].life
        arrive(game, tapped=True)
        assert life_gained(game, before) == 0


class TestThePairThatProvesIt:
    """Without these, the test above passes if nothing ever triggers."""

    @pytest.mark.parametrize("tapped", [False, True])
    def test_without_the_clause_both_arrivals_trigger(self, builder, tapped):
        game = board(builder, LOOSE)
        before = game.state.players[0].life
        arrive(game, tapped=tapped)
        assert life_gained(game, before) == 1

    def test_the_opposite_clause_reads_the_opposite_way(self, builder):
        """`tapped: true` is a value, not a presence check."""
        game = board(builder, TAPPED)
        before = game.state.players[0].life
        arrive(game, tapped=True)
        assert life_gained(game, before) == 1

    def test_the_opposite_clause_rejects_an_untapped_arrival(self, builder):
        game = board(builder, TAPPED)
        before = game.state.players[0].life
        arrive(game, tapped=False)
        assert life_gained(game, before) == 0
