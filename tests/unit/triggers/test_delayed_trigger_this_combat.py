""""Whenever … this combat" -- a delayed trigger on the combat phase's clock.

    "Whenever you attack with exactly two creatures, those creatures gain first
    strike until end of turn, then draw a card. Whenever either of those
    creatures deals combat damage to a player **this combat**, put a +1/+1
    counter on it."                         -- Love on the Battlefield

The second sentence is a delayed triggered ability (603.7) created by the
resolving attack trigger, and its lifetime is the combat phase it was made in
(506.1: a turn can have more than one). Every earlier `delayed_trigger` duration
is a different card. `this_turn` keeps watching through an extra combat later in
the turn, where the printed card gives no counter; `once_this_turn` and
`until_it_fires` are spent by the first of the two creatures to connect, where
the printed "whenever either" fires for each. `this_combat` is `this_turn`'s
repeating subscription, dropped by `combat.end_combat` as the end of combat step
begins -- the hook that already ends an AttackRestriction's "this combat".

What is pinned below:

1. **Exactly two.** Attacking with two gives both first strike and draws one
   card; one attacker or three does nothing at all, subscription included.
2. **Either of those creatures, each time.** Each attacker that deals combat
   damage to a player gets one counter, and its counter is its own (the event's
   subject, not the pair). A blocked one deals no damage to a player and gets
   none. A double striker connects in both combat damage steps (510.4) and gets
   two.
3. **This combat.** The subscription is gone once the combat ends, so an extra
   combat later that turn gives no counter off it; attacking with both again
   there is a new trigger and a new subscription, one counter each, not two.
4. **Only inside a combat.** Outside a combat phase there is no "this combat",
   and the op installs nothing.
5. The loader takes the duration, and the authoring packet advertises it
   beside the delayed-trigger keys (`subject` is on no printed trigger).

`t_dtc_love` in `tests/data/delayed_this_combat.cards.json` is the card on a {W}
enchantment; the vigilant 2/2s attack twice in a turn without help.
"""

from __future__ import annotations

import json
from pathlib import Path

from commanderblitz.cards.authoring.packet import reference
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute, execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.structs import TargetRef
from tests.conftest import (
    attack_with,
    find_action,
    keywords,
    oids_of,
    pass_until,
    plus_one_counters,
)

LOVE = "t_dtc_love"
VIGILANT = "t_vigilant"  # 2/2 vigilance
DOUBLE_STRIKER = "t_double_striker"  # 2/2 double strike
BEAR = "t_bear"  # 2/2
WALL = "t_wall"  # 0/4 defender


def position(builder, attackers: list[str], blockers: tuple[str, ...] = ()):
    """Player 0 has Love on the Battlefield and ``attackers``; player 1 ``blockers``.

    Returns ``(game, oids)``, ``oids`` being player 0's creatures in order.
    """
    b = (
        builder(players=2)
        .battlefield(0, [LOVE, *attackers])
        .library(0, ["mountain"] * 10)
        .library(1, ["mountain"] * 10)
    )
    if blockers:
        b = b.battlefield(1, list(blockers))
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build()
    mine = [o.oid for o in game.state.battlefield_objects(0) if o.def_id != LOVE]
    return game, sorted(mine)


def declare(game, *attackers: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid in attackers:
        attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def block(game, blocker: int, attacker: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    game.apply(
        find_action(
            game, ActionKind.ADD_BLOCKER, source=blocker, targets=(TargetRef.obj(attacker),)
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def settled(g) -> bool:
    return not g.state.stack and not g.state.pending_triggers and not g.state.armed_delays


def through_combat(game) -> None:
    """Play this combat out, everything resolved, stopping before the next one.

    Stops at this combat's end of combat step, or at an extra combat's
    declaration after it, whichever the walk reaches first -- declaring blockers
    can carry the walk straight into the next combat.
    """
    pass_until(
        game,
        lambda g: settled(g)
        and (
            g.state.step >= Step.END_OF_COMBAT
            or (g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        ),
    )


def after_declaration(game) -> None:
    """Let the attack trigger resolve, still in the declare attackers step."""
    pass_until(game, lambda g: settled(g) and g.state.step >= Step.DECLARE_ATTACKERS)


def by_card(builder, cards: list[str]):
    """``position``, with player 0's creatures in the order ``cards`` names them."""
    game, _ = position(builder, cards)
    return game, tuple(oids_of(game, card, 0)[0] for card in cards)


def hand_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def grant_extra_combat(game) -> None:
    ctx = EffectContext(state=game.state, controller=0, targets={})
    list(execute_one(ctx, {"op": "extra_combat"}))


def love_model() -> dict:
    """The fixture card's model, for the loader and for running its op directly."""
    path = Path(__file__).parents[2] / "data" / "delayed_this_combat.cards.json"
    return json.loads(path.read_text())["cards"][0]


def this_combat_watches(game) -> list:
    return [d for d in game.state.delayed_triggers if d.duration == "this_combat"]


class TestExactlyTwo:
    def test_both_gain_first_strike_and_you_draw_one(self, builder):
        game, (a, b) = position(builder, [VIGILANT, VIGILANT])
        before = hand_size(game)
        declare(game, a, b)
        after_declaration(game)
        assert "first_strike" in keywords(game, a)
        assert "first_strike" in keywords(game, b)
        assert hand_size(game) == before + 1
        assert len(this_combat_watches(game)) == 1

    def test_one_attacker_does_nothing(self, builder):
        game, (a, _) = position(builder, [VIGILANT, VIGILANT])
        before = hand_size(game)
        declare(game, a)
        through_combat(game)
        assert "first_strike" not in keywords(game, a)
        assert hand_size(game) == before
        assert plus_one_counters(game, a) == 0

    def test_three_attackers_do_nothing(self, builder):
        game, oids = position(builder, [VIGILANT, VIGILANT, VIGILANT])
        before = hand_size(game)
        declare(game, *oids)
        after_declaration(game)
        assert this_combat_watches(game) == []
        through_combat(game)
        assert hand_size(game) == before
        assert [plus_one_counters(game, o) for o in oids] == [0, 0, 0]


class TestEitherOfThoseCreatures:
    def test_each_that_connects_gets_its_own_counter(self, builder):
        game, (a, b) = position(builder, [VIGILANT, VIGILANT])
        declare(game, a, b)
        through_combat(game)
        assert plus_one_counters(game, a) == 1
        assert plus_one_counters(game, b) == 1

    def test_a_blocked_one_gets_none(self, builder):
        game, (a, b) = position(builder, [VIGILANT, VIGILANT], blockers=(WALL,))
        wall = oids_of(game, WALL, 1)[0]
        declare(game, a, b)
        block(game, wall, a)
        through_combat(game)
        assert plus_one_counters(game, a) == 0
        assert plus_one_counters(game, b) == 1

    def test_the_scope_is_the_two_attackers(self, builder):
        """The attackers bound when the trigger resolved, and nothing else."""
        game, (a, b) = position(builder, [VIGILANT, VIGILANT])
        declare(game, a, b)
        after_declaration(game)
        assert this_combat_watches(game)[0].subject_oids == (a, b)

    def test_a_double_striker_connects_in_both_steps(self, builder):
        """510.4: two combat damage steps, two hits, and "whenever" is each."""
        game, (striker, vigilant) = by_card(builder, [DOUBLE_STRIKER, VIGILANT])
        declare(game, striker, vigilant)
        through_combat(game)
        assert plus_one_counters(game, striker) == 2
        assert plus_one_counters(game, vigilant) == 1


class TestThisCombat:
    def test_the_watch_ends_with_the_combat(self, builder):
        game, (a, b) = position(builder, [VIGILANT, VIGILANT])
        declare(game, a, b)
        through_combat(game)
        assert this_combat_watches(game) == []

    def test_an_extra_combat_later_gives_no_counter(self, builder):
        game, (a, b) = position(builder, [VIGILANT, VIGILANT], blockers=(WALL,))
        wall = oids_of(game, WALL, 1)[0]
        declare(game, a, b)
        grant_extra_combat(game)
        block(game, wall, a)  # a deals no damage to a player this combat
        through_combat(game)
        assert (plus_one_counters(game, a), plus_one_counters(game, b)) == (0, 1)
        declare(game, a)  # alone: no new trigger, so only the old watch could fire
        through_combat(game)
        assert game.state.turn_ledger.combats == 2
        assert plus_one_counters(game, a) == 0

    def test_both_again_is_a_new_trigger_and_one_counter_each(self, builder):
        """A `this_turn` watch would still be live and give the second counter."""
        game, (a, b) = position(builder, [VIGILANT, VIGILANT])
        before = hand_size(game)
        declare(game, a, b)
        grant_extra_combat(game)
        through_combat(game)
        declare(game, a, b)
        through_combat(game)
        assert game.state.turn_ledger.combats == 2
        assert plus_one_counters(game, a) == 2
        assert plus_one_counters(game, b) == 2
        assert hand_size(game) == before + 2


class TestOutsideACombat:
    def test_it_installs_nothing(self, builder):
        """A held instant stops the walk in the precombat main phase."""
        game = (
            builder(players=2)
            .battlefield(0, [LOVE, VIGILANT, VIGILANT, "mountain"])
            .hand(0, ["t_bolt"])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        a, b = sorted(oids_of(game, VIGILANT, 0))
        assert game.state.step is Step.PRECOMBAT_MAIN and game.state.combat is None
        ctx = EffectContext(
            state=game.state, controller=0, targets={}, bindings={"attackers": [a, b]}
        )
        watch = love_model()["abilities"][0]["effects"][2]
        list(execute(ctx, [watch]))
        assert game.state.delayed_triggers == []


class TestTheLoader:
    def test_the_duration_loads(self):
        compile_card(CardModel.model_validate(love_model()))

    def test_the_packet_advertises_it(self):
        vocabulary = reference()
        assert "this_combat" in vocabulary["delayed_durations"]
        assert "subject" in vocabulary["delayed_trigger_keys"]
