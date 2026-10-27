"""Dethrone (702.105) -- a keyword whose whole content is a rules-supplied trigger.

    "Dethrone (Whenever this creature attacks the player with the most life or
    tied for most life, put a +1/+1 counter on it.)"
                                        -- Enraged Revolutionary, Scourge of the Throne

The ability is a trigger *event* with a condition built into it, not an
intervening-if: 702.105a has no "if", so the life totals are compared as the
creature attacks and never again (603.4 re-checks only an "if" clause). The
near miss is an `attacks` trigger with a `condition` comparing `{"life_of":
{"binding": "defender"}}` with `{"max_life_of": "each_player"}`, and it fails
twice: re-checked on resolution, it puts no counter on the creature once the
defender has been drained below somebody else in response; and `defender` is a
planeswalker's or battle's *controller*, so it would fire on an attack at the
top-life player's planeswalker, which is attacking the permanent and not the
player (506.2).

So the trigger's `defending: "most_life"` clause, read off the ATTACKS event's
`defender` and `attacked_permanent`, and a `Keyword` -- exalted's shape --
because Marchesa, the Black Rose *grants* dethrone. The trigger itself is
`carddef.DETHRONE_TRIGGER`, yielded for every permanent whose derived keywords
include it.

The rules points, each with a test:

- most life, or tied for it, among the players still in the game -- the
  attacker's controller included, and a player who has left not;
- a player, not a planeswalker or battle that player controls;
- part of the event, so a change of life totals before resolution does not
  take the counter away;
- a granted dethrone triggers, each creature for itself;
- the loader refuses `most_life` on an event that cannot tell a player attack
  from a planeswalker attack.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, keywords, only_oid, pass_until, plus_one_counters, settle

REBEL = "t_dt_rebel"  # 2/1, printed dethrone
MARCHESA = "t_dt_marchesa"  # 3/3, "other creatures you control have dethrone"
BEAR = "t_bear"  # 2/2, no abilities
WALKER = "t_walker"  # loyalty 4
BOLT = "t_bolt"  # {R} instant, so priority stops while a trigger is on the stack


def position(builder, *, mine=(REBEL,), life=(20, 20, 20), theirs=None):
    b = (
        builder(players=len(life))
        .battlefield(0, ["mountain", *mine])
        .hand(0, [BOLT])
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid, total in enumerate(life):
        b.life(pid, total)
    for pid, cards in (theirs or {}).items():
        b.battlefield(pid, cards)
    game = b.build()
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    return game


def declare(game, attacks: dict[int, TargetRef]) -> None:
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def at(pid: int) -> TargetRef:
    return TargetRef.player(pid)


class TestTheMostLife:
    def test_attacking_the_player_with_the_most_life_puts_a_counter_on(self, builder):
        game = position(builder, life=(20, 30, 25))
        rebel = only_oid(game, REBEL, 0)
        declare(game, {rebel: at(1)})
        settle(game)
        assert plus_one_counters(game, rebel) == 1

    def test_tied_for_the_most_life_counts(self, builder):
        game = position(builder, life=(20, 30, 30))
        rebel = only_oid(game, REBEL, 0)
        declare(game, {rebel: at(2)})
        settle(game)
        assert plus_one_counters(game, rebel) == 1

    def test_attacking_a_player_with_less_life_does_not_trigger(self, builder):
        game = position(builder, life=(20, 30, 25))
        rebel = only_oid(game, REBEL, 0)
        declare(game, {rebel: at(2)})
        assert not game.state.stack
        settle(game)
        assert plus_one_counters(game, rebel) == 0

    def test_the_attackers_own_controller_is_one_of_the_players(self, builder):
        """"The player with the most life" is asked of the whole table, you included."""
        game = position(builder, life=(40, 30, 25))
        rebel = only_oid(game, REBEL, 0)
        declare(game, {rebel: at(1)})
        assert not game.state.stack
        settle(game)
        assert plus_one_counters(game, rebel) == 0

    def test_a_player_who_has_left_the_game_is_not_compared(self, builder):
        game = position(builder, life=(20, 25, 40, 10))
        game.state.players[2].has_lost = True
        rebel = only_oid(game, REBEL, 0)
        assert game.state.has_most_life(1)
        assert not game.state.has_most_life(2)
        declare(game, {rebel: at(1)})
        settle(game)
        assert plus_one_counters(game, rebel) == 1


class TestAPlayerNotAPermanent:
    def test_attacking_the_top_life_players_planeswalker_does_not_trigger(self, builder):
        """506.2: an attack on a planeswalker attacks the walker, not its controller."""
        game = position(builder, life=(20, 30, 25), theirs={1: [WALKER]})
        rebel = only_oid(game, REBEL, 0)
        declare(game, {rebel: TargetRef.obj(only_oid(game, WALKER, 1))})
        assert not game.state.stack
        settle(game)
        assert plus_one_counters(game, rebel) == 0


class TestItIsPartOfTheEvent:
    def test_a_change_of_life_before_resolution_keeps_the_counter(self, builder):
        """No intervening-if: the comparison is made as it attacks and never again."""
        game = position(builder, life=(20, 30, 25))
        rebel = only_oid(game, REBEL, 0)
        declare(game, {rebel: at(1)})
        assert game.state.stack, "the trigger is waiting to resolve"
        game.state.players[1].life = 10
        settle(game)
        assert plus_one_counters(game, rebel) == 1


class TestGrantedDethrone:
    def test_a_granted_dethrone_triggers_for_each_creature(self, builder):
        game = position(builder, mine=(MARCHESA, BEAR, BEAR), life=(20, 30, 25))
        bears = [o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR]
        assert all("dethrone" in keywords(game, b) for b in bears)
        marchesa = only_oid(game, MARCHESA, 0)
        assert "dethrone" not in keywords(game, marchesa), "'other creatures'"
        declare(game, {bears[0]: at(1), bears[1]: at(1), marchesa: at(1)})
        settle(game)
        assert [plus_one_counters(game, b) for b in bears] == [1, 1]
        assert plus_one_counters(game, marchesa) == 0

    def test_without_the_grant_a_bear_is_silent(self, builder):
        game = position(builder, mine=(BEAR,), life=(20, 30, 25))
        bear = only_oid(game, BEAR, 0)
        declare(game, {bear: at(1)})
        assert not game.state.stack


def _trigger(**trigger) -> dict:
    return {
        "id": "t_most_life_probe",
        "name": "Most Life Probe",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "triggered",
                "trigger": trigger,
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        ],
    }


class TestTheLoaderGuard:
    def test_most_life_loads_on_attacks(self):
        compile_card(CardModel.model_validate(_trigger(event="attacks", source="self", defending="most_life")))

    @pytest.mark.parametrize("event", ["creatures_attack_player", "deals_damage_to_player"])
    def test_most_life_is_refused_where_the_event_cannot_tell_a_player_from_a_walker(self, event):
        with pytest.raises(DslError, match="most_life"):
            compile_card(CardModel.model_validate(_trigger(event=event, defending="most_life")))
