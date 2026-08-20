"""Goldvein Hydra: "equal to its power", asked about a creature that just died.

"When this creature dies, create a number of tapped Treasure tokens equal to
**its power**."

`power_of {"self": true}` cannot answer it. By the time the death trigger
resolves the object is a card in a graveyard: `reset_permanent_state` has
emptied its counters and no anthem applies to it any more, so `chars()` returns
the printed line — and Goldvein Hydra's printed line is 0/0. A Hydra that died
as a 7/7 would make nothing at all.

`counters_had` is the near miss and recovers only the +1/+1 counters. That is a
different number the moment anything else touched the creature: an anthem, a
pump spell, a -1/-1 counter. The two agree exactly on the one board state where
neither matters.

So this is the fourth instance of the pattern `test_counters_had.py` describes —
`was_creature`, `was_attacking` and `had_counters` are the first three —
snapshotted in `zones.move_object` before the wipe and read back through
`power_had`. Deliberately **not** a global last-known-information system: that
is a decision recorded in rules-coverage.md, and the explicit form is what the
`snapshot` op already does everywhere a card can reach. This is the one place it
cannot, because an op runs at resolution and by then the creature is gone.
"""

from __future__ import annotations

from automtg.engine.enums import Zone
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, only_oid

HYDRA = "t_dying_payout"  # printed 2/2, "Treasures equal to its power" on death
ANTHEM = "t_anthem_for_hydras"  # creatures you control get +2/+2


def settle(game, limit: int = 60) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the death trigger never resolved")


def treasures(game, pid: int = 0) -> int:
    return sum(
        1
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id == "treasure_token"
        and game.state.objects[oid].controller == pid
    )


def kill(game, oid) -> None:
    move_object(game.state, oid, Zone.GRAVEYARD)
    settle(game)


class TestItReadsThePowerItDiedWith:
    def test_the_printed_power(self, builder):
        """A plain 2/2 makes two."""
        game = builder(players=2).battlefield(0, [HYDRA]).build()
        kill(game, only_oid(game, HYDRA, 0))
        assert treasures(game) == 2

    def test_counters_are_included(self, builder):
        """Three +1/+1 counters on a 2/2 is a 5/5, so five Treasures."""
        game = (
            builder(players=2)
            .battlefield(0, [HYDRA], counters={"+1/+1": 3})
            .build()
        )
        kill(game, only_oid(game, HYDRA, 0))
        assert treasures(game) == 5

    def test_an_anthem_is_included_and_counters_had_would_miss_it(self, builder):
        """The case that separates this from `counters_had`.

        A 2/2 under a +2/+2 anthem dies as a 4/4 with no counters at all. Read
        through `counters_had` the answer would be 0; read off the object after
        death it would be 2, the printed line. Both are wrong.
        """
        game = builder(players=2).battlefield(0, [HYDRA, ANTHEM]).build()
        hydra = only_oid(game, HYDRA, 0)
        kill(game, hydra)
        assert treasures(game) == 4

    def test_a_shrinking_effect_is_included(self, builder):
        """-1/-1 counters cut the payout, rather than being ignored."""
        game = (
            builder(players=2)
            .battlefield(0, [HYDRA], counters={"-1/-1": 1})
            .build()
        )
        kill(game, only_oid(game, HYDRA, 0))
        assert treasures(game) == 1


class TestTheSnapshotIsTakenOnTheWayOut:
    def test_it_does_not_read_the_graveyard_card(self, builder):
        """The object really is back to its printed line once it has left."""
        from automtg.engine.characteristics import chars

        game = (
            builder(players=2)
            .battlefield(0, [HYDRA], counters={"+1/+1": 3})
            .build()
        )
        oid = only_oid(game, HYDRA, 0)
        assert chars(game.state, oid).power == 5, "a 5/5 while it is alive"
        kill(game, oid)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert chars(game.state, oid).power == 2, (
            "back to the printed line in the graveyard -- which is exactly why "
            "the value has to come off the event"
        )
        assert treasures(game) == 5, "and the payout used the live value"
