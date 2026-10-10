""""Whenever this creature deals combat damage" -- to anything, once per step.

    "+1: Choose up to two target creatures. Until your next turn, whenever
    either of those creatures deals combat damage, you draw a card."
                                            -- Tamiyo, Field Researcher

The engine had three combat damage triggers and each is one kind of recipient:
`deals_combat_damage_to_player`, `deals_combat_damage_to_planeswalker`, and
`dealt_damage` (the *victim's* event, per recipient). None hears a blocked
creature hitting its blocker, and composing them is not the printed ability
either: 510.2 makes a step's combat damage one simultaneous event, so a trampler
that hits its blocker and the player "deals combat damage" **once**, where three
per-recipient triggers would draw twice.

`deals_combat_damage` is fired by `combat._fire_per_source` once per dealing
permanent per combat damage step, from the amounts actually dealt (after
prevention), with the dealer as its subject.

What is pinned below:

1. An unblocked creature hitting the player fires it once.
2. A **blocked** creature hitting only its blocker fires it -- the case no
   existing event could hear.
3. A trampler hitting both its blocker and the player fires it **once**.
4. A creature that dealt no damage fires nothing.
5. A delayed trigger may watch it through a `subject` (Tamiyo's shape).
"""

from __future__ import annotations

from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from tests.conftest import only_oid, pass_until

SCOUT = "t_dcd_scout"  # 2/2, draws whenever it deals combat damage
TRAMPLER = "t_dcd_trampler"  # 5/5 trample, the same trigger
WALL = "t_dcd_wall"  # 0/3
BEAR = "t_bear"  # 2/2, no trigger


def board(builder, *, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 3 + list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def swing(game, attacker: int, *, blocker: int | None = None) -> None:
    """Attack the opponent with ``attacker``; block it with ``blocker`` if given.

    Settled at the first decision at or after this turn's postcombat main, the
    reading `test_batched_combat_damage.py` explains.
    """
    pass_until(game, lambda g: g.state.step is Step.DECLARE_ATTACKERS)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER
            and a.source == attacker
            and any(r.kind == "player" for r in a.targets)
        )
    )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    if blocker is not None:
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.DECLARE_BLOCKERS,
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_BLOCKER and a.source == blocker
            )
        )
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
    mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
    pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)


def firings(game, oid: int) -> int:
    return sum(
        1
        for e in game.state.events
        if e.type == EventType.CREATURE_DEALT_COMBAT_DAMAGE and e.source == oid
    )


def hand(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


class TestWhatItHears:
    def test_an_unblocked_hit_fires_it_once(self, builder):
        game = board(builder, mine=[SCOUT])
        scout = only_oid(game, SCOUT, 0)
        before = hand(game)
        swing(game, scout)
        assert firings(game, scout) == 1
        assert hand(game) == before + 1

    def test_a_blocked_creature_hitting_only_its_blocker_fires_it(self, builder):
        """The case none of the per-recipient player/planeswalker events hears."""
        game = board(builder, mine=[SCOUT], theirs=[WALL])
        scout, wall = only_oid(game, SCOUT, 0), only_oid(game, WALL, 1)
        life = game.state.players[1].life
        before = hand(game)
        swing(game, scout, blocker=wall)
        assert game.state.players[1].life == life, "the blocker took it all"
        assert firings(game, scout) == 1
        assert hand(game) == before + 1

    def test_a_trampler_hitting_two_things_fires_it_once(self, builder):
        """510.2: one simultaneous event. Per-recipient triggers would draw two."""
        game = board(builder, mine=[TRAMPLER], theirs=[WALL])
        trampler, wall = only_oid(game, TRAMPLER, 0), only_oid(game, WALL, 1)
        life = game.state.players[1].life
        before = hand(game)
        swing(game, trampler, blocker=wall)
        assert game.state.players[1].life < life, "the excess trampled over"
        assert firings(game, trampler) == 1
        assert hand(game) == before + 1

    def test_a_blocker_with_no_power_fires_nothing(self, builder):
        """Dealing zero is not dealing damage."""
        game = board(builder, mine=[SCOUT], theirs=[WALL])
        scout, wall = only_oid(game, SCOUT, 0), only_oid(game, WALL, 1)
        swing(game, scout, blocker=wall)
        assert firings(game, wall) == 0


class TestTamiyosShape:
    """A delayed trigger watching two chosen creatures through `subject`."""

    def test_either_watched_creature_draws_blocked_or_not(self, builder):
        game = board(builder, mine=[BEAR], theirs=[WALL])
        bear, wall = only_oid(game, BEAR, 0), only_oid(game, WALL, 1)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            targets={"t1": (TargetRef.obj(bear), TargetRef.obj(wall))},
        )
        list(
            execute(
                ctx,
                [
                    {
                        "op": "delayed_trigger",
                        "duration": "until_your_next_turn",
                        "trigger": {
                            "event": "deals_combat_damage",
                            "controller": "any",
                            "subject": {"target": "t1"},
                        },
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ],
            )
        )
        before = hand(game)
        swing(game, bear, blocker=wall)
        assert hand(game) == before + 1
