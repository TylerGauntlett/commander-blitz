"""A trigger doubler whose cause is "a creature you control **being dealt damage**".

    Wayta, Trainer Prodigy -- "If a creature you control being dealt damage
    causes a triggered ability of a permanent you control to trigger, that
    ability triggers an additional time."

Two things had to hold, and each has a class below.

- **The half.** `dealt_damage` is the permanent half of `DAMAGE_DEALT`, and
  `_cause_matches` never asked which half it had: on the player half -- your
  creature dealing damage to a player -- `_subject_oid` fell through to the
  dealer, a creature you control, so the doubler doubled triggers the card never
  names. It now asks `_half_matches` as a trigger does.
- **A batched trigger triggers again.** The Veloci-Ramp-Tor deck pairs Wayta
  with Wrathful Raptors, whose trigger is batched per damaged Dinosaur. A
  doubler queues the same firing a second time, and `_queue`'s "this batch
  already fired" check -- there for a *later* event of the batch -- swallowed
  the copy. The copy now passes it (`again`), and a firing that did not queue
  is not copied either.

`t_wy_doubler` is Wayta's line on an enchantment; `t_dps_watcher` and
`t_dps_brute` come from tests/data/dealt_damage_per_subject.cards.json.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import pass_until, plus_one_counters

DOUBLER = "t_wy_doubler"
PINGER = "t_wy_pinger"  # gain 1 whenever a creature you control deals damage to a player
WATCHER = "t_dps_watcher"  # per-Dinosaur "that many" +1/+1 counters
BRUTE = "t_dps_brute"  # 2/6 Dinosaur
QUAKE = "t_dps_quake"  # 1 damage to each creature
BEAR = "t_bear"


def quaked(builder, *extra) -> list[int]:
    game = (
        builder(players=2)
        .battlefield(0, [WATCHER, *extra, BRUTE, BRUTE, "mountain"])
        .hand(0, [QUAKE])
        .library(0, ["forest"] * 10)
        .active(0)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == QUAKE
        )
    )
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return [
        plus_one_counters(game, o.oid)
        for o in game.state.battlefield_objects(0)
        if o.def_id == BRUTE
    ]


def swung(builder, *extra) -> int:
    game = (
        builder(players=2)
        .battlefield(0, [PINGER, *extra, BEAR])
        .library(0, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    for obj in game.state.battlefield_objects(0):
        obj.entered_turn = 0
    before = game.state.players[0].life
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    bear = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER and a.source == bear)
    )
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)
    return game.state.players[0].life - before


class TestABatchedTriggerTriggersAgain:
    def test_each_dinosaur_fires_twice(self, builder):
        assert quaked(builder, DOUBLER) == [2, 2]

    def test_without_the_doubler_once(self, builder):
        assert quaked(builder) == [1, 1]


class TestOnlyBeingDealtDamage:
    def test_your_creature_dealing_damage_is_not_the_cause(self, builder):
        assert swung(builder, DOUBLER) == 1

    def test_the_pinger_alone_gains_one(self, builder):
        assert swung(builder) == 1
