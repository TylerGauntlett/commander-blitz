"""How many creatures you controlled dealt combat damage to a player this turn --
Indulge // Excess.

Excess: "Create a Treasure token for each creature you controlled that dealt
combat damage to a player this turn." A count of *creatures*, asked in a main
phase after `state.combat` has gone (rule 510.2: the damage is an event that
happened), of objects that may no longer be on the battlefield -- "you
controlled", past tense, includes a creature that hit and then died. Every near
miss is wrong in a way this card shows:

- `{"player_count": {"dealt_combat_damage_by": "any"}}` counts the **players**
  hit, so two creatures through to one opponent read 1.
- `{"count": …}` over the battlefield has forgotten every dealer that died or
  was bounced after combat.
- The keys of `TurnLedger.players_dealt_combat_damage_by` drop a creature that
  re-entered the battlefield (400.7), whose damage was still dealt.
- `damage_taken_this_turn` counts noncombat damage and sums amounts.

So `TurnLedger.combat_damagers_by_controller`, the seat that controlled each
dealer as its combat damage was dealt (120.1) -> the distinct dealers, folded
off COMBAT_DAMAGE_TO_PLAYER and re-keyed rather than dropped by
`retire_combat_damager` when a dealer re-enters: the old object's damage counts
once, and the new object is a second creature only if it hits too. Combat damage
to a creature or a planeswalker is not damage to a player (510.1). It wears off
with the rest of the ledger at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent, damage_player
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import (
    _default_answer,
    action_for_card,
    find_action,
    oids_of,
    pass_until,
    settle,
)

BEAR = "t_bear"  # vanilla 2/2 Bear
WALKER = "t_walker"  # a 4-loyalty planeswalker
BOLT = "t_bolt"  # an instant, castable off the Mountain, so priority stops in every step
INDULGE = "indulge_excess"  # the witness
CITIZEN = "citizen_1_1_gw"
TREASURE = "treasure_token"
KEY = "creatures_dealt_combat_damage_to_player_this_turn"


def board(builder, *, players: int = 3):
    b = (
        builder(players=players)
        .battlefield(0, [BEAR, BEAR, "mountain"])
        .hand(0, [BOLT])
        .library(0, ["mountain"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
    )
    b.battlefield(1, [BEAR, WALKER])
    b.library(1, ["mountain"] * 10)
    for pid in range(2, players):
        b.battlefield(pid, [])
        b.library(pid, ["mountain"] * 10)
    game = b.build()
    first, second = oids_of(game, BEAR, 0)
    return game, first, second


def ctx(game) -> EffectContext:
    return EffectContext(state=game.state, controller=0, source_oid=None)


def count(game, spec="you") -> int:
    return evaluate_value(ctx(game), {KEY: spec})


def hit(game, pid: int, oid: int, *, combat: bool = True) -> None:
    damage_player(game.state, pid, 2, oid, is_combat=combat)


class TestTheCount:
    def test_two_creatures_hitting_count_two(self, builder):
        game, a, b = board(builder)
        hit(game, 1, a)
        hit(game, 1, b)
        assert count(game) == 2
        # The near miss counts the one player they hit.
        players = {"player_count": {"dealt_combat_damage_by": "any"}}
        assert evaluate_value(ctx(game), players) == 1

    def test_one_creature_hitting_two_players_counts_once(self, builder):
        game, a, _ = board(builder)
        hit(game, 1, a)
        hit(game, 2, a)
        hit(game, 1, a)
        assert count(game) == 1

    def test_nobody_hit_is_nothing(self, builder):
        game, _, _ = board(builder)
        assert count(game) == 0

    def test_noncombat_damage_does_not_count(self, builder):
        game, a, _ = board(builder)
        hit(game, 1, a, combat=False)
        assert count(game) == 0


class TestOnlyDamageToAPlayer:
    def test_combat_damage_to_a_creature_does_not_count(self, builder):
        game, a, _ = board(builder)
        (theirs,) = oids_of(game, BEAR, 1)
        damage_permanent(game.state, theirs, 2, a, is_combat=True)
        assert count(game) == 0

    def test_combat_damage_to_a_planeswalker_does_not_count(self, builder):
        game, a, _ = board(builder)
        (walker,) = oids_of(game, WALKER, 1)
        damage_permanent(game.state, walker, 2, a, is_combat=True)
        assert count(game) == 0


class TestWhoseCreature:
    def test_an_opponents_creature_does_not_count_for_you(self, builder):
        game, a, _ = board(builder)
        (theirs,) = oids_of(game, BEAR, 1)
        hit(game, 0, theirs)
        assert count(game, "you") == 0
        assert count(game, "opponent") == 1
        hit(game, 1, a)
        assert count(game, "you") == 1
        assert count(game, "all") == 2


class TestTheDealerLeaving:
    def test_a_creature_that_died_still_counts(self, builder):
        game, a, b = board(builder)
        hit(game, 1, a)
        hit(game, 1, b)
        move_object(game.state, a, Zone.GRAVEYARD)
        assert count(game) == 2

    def test_a_creature_that_reentered_still_counts_once(self, builder):
        game, a, _ = board(builder)
        hit(game, 1, a)
        move_object(game.state, a, Zone.EXILE)
        move_object(game.state, a, Zone.BATTLEFIELD)
        # The per-oid record forgets, as 400.7 says it must; this one does not.
        assert game.state.turn_ledger.players_dealt_combat_damage_by.get(a, set()) == set()
        assert count(game) == 1

    def test_the_new_object_hitting_again_is_a_second_creature(self, builder):
        game, a, _ = board(builder)
        hit(game, 1, a)
        move_object(game.state, a, Zone.EXILE)
        move_object(game.state, a, Zone.BATTLEFIELD)
        hit(game, 2, a)
        assert count(game) == 2


def attack(game, attacks: dict[int, int]) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid, pid in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid,
                               targets=(TargetRef.player(pid),)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def second_main(game) -> None:
    for _ in range(300):
        if (game.state.step is Step.POSTCOMBAT_MAIN and not game.state.stack
                and game.pending() is not None and game.pending().player == 0
                and game.pending().kind is DecisionKind.PRIORITY):
            return
        game.apply(_default_answer(game, game.pending()))
    raise AssertionError("did not reach the second main phase")


class TestAcrossTurns:
    def test_a_real_combat_records_and_the_next_turn_clears_it(self, builder):
        game, a, b = board(builder)
        started = game.state.turn
        attack(game, {a: 2, b: 2})
        second_main(game)
        assert count(game) == 2
        pass_until(game, lambda g: g.state.turn > started)
        assert game.state.turn > started
        assert count(game) == 0


class TestTheCard:
    def cast(self, builder):
        b = (
            builder(players=3)
            .battlefield(0, [BEAR, BEAR] + ["mountain"] * 5)
            .hand(0, [INDULGE])
            .library(0, ["mountain"] * 10)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
        )
        for pid in (1, 2):
            b.battlefield(pid, [])
            b.library(pid, ["mountain"] * 10)
        game = b.build()
        game.apply(action_for_card(game, ActionKind.CAST, INDULGE))
        settle(game)
        return game, oids_of(game, BEAR, 0)

    def cast_excess(self, game) -> None:
        action = next(
            a for a in game.legal_actions()
            if a.kind is ActionKind.CAST and "Excess" in (a.base_label or "")
        )
        game.apply(action)
        settle(game)

    def test_each_attack_makes_a_citizen_and_every_hitter_a_treasure(self, builder):
        game, (a, b) = self.cast(builder)
        attack(game, {a: 1, b: 2})
        second_main(game)
        citizens = oids_of(game, CITIZEN, 0)
        assert len(citizens) == 2
        # Two Bears and two Citizens, unblocked: four creatures, two players.
        assert count(game) == 4
        self.cast_excess(game)
        assert len(oids_of(game, TREASURE, 0)) == 4

    def test_a_dealer_gone_by_the_second_main_phase_still_pays(self, builder):
        game, (a, b) = self.cast(builder)
        attack(game, {a: 1, b: 1})
        second_main(game)
        move_object(game.state, a, Zone.GRAVEYARD)
        self.cast_excess(game)
        assert len(oids_of(game, TREASURE, 0)) == 4


class TestTheLoader:
    def probe(self, amount) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "Probe.",
                "mana_cost": "{G}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Probe.",
                        "cost": {"mana": "{1}"},
                        "effects": [{"op": "draw", "player": "you", "amount": amount}],
                    }
                ],
            }
        )

    @pytest.mark.parametrize("who", ["you", "opponent", "all"])
    def test_a_player_spec_loads(self, who):
        compile_card(self.probe({KEY: who}))

    @pytest.mark.parametrize("who", [True, 3, "yours", ["you"]])
    def test_near_misses_are_refused(self, who):
        with pytest.raises(DslError, match=KEY):
            compile_card(self.probe({KEY: who}))
