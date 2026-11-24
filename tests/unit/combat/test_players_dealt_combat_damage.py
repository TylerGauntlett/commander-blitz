"""Every player dealt combat damage this turn, by any source -- Vivien's Stampede.

"At the beginning of the next main phase this turn, draw a card for each player
who was dealt combat damage this turn." A count of *players*, asked after
`state.combat` has gone (rule 510.2: the damage is an event that happened), about
damage from every source at once:

- `{"dealt_combat_damage_by": "self"}` is keyed by the ability's own source; a
  sorcery's delayed trigger has no creature to ask about.
- A union over `TurnLedger.players_dealt_combat_damage_by` would be wrong, because
  an oid's record is dropped when it re-enters the battlefield (400.7): a
  creature that hit a player and was then flickered would take that player out
  of the count, though the player was still dealt the damage.
- `{"subtypes": [...]}` over every creature type misses a creature with none.
- `damage_taken_this_turn` counts noncombat damage too, and sums amounts.

So `TurnLedger.players_dealt_combat_damage`, a seat set folded off
COMBAT_DAMAGE_TO_PLAYER and never cleared per oid, read by the
`dealt_combat_damage_by` subject `"any"`. A set of seats, so a player hit twice
is one player; it wears off with the rest of the ledger at cleanup.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import select_players
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_player
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import (
    _default_answer,
    action_for_card,
    find_action,
    keywords,
    oids_of,
    pass_until,
    settle,
)

BEAR = "t_bear"  # vanilla 2/2 Bear
BOLT = "t_bolt"  # an instant, castable off the Mountain, so priority stops in every step
STAMPEDE = "vivien_s_stampede"  # the witness
ANY = {"dealt_combat_damage_by": "any"}
COUNT = {"player_count": ANY}


def board(builder, *, players: int = 4):
    b = (
        builder(players=players)
        .battlefield(0, [BEAR, BEAR, "mountain"])
        .hand(0, [BOLT])
        .library(0, ["mountain"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid in range(1, players):
        b.battlefield(pid, [])
        b.library(pid, ["mountain"] * 10)
    game = b.build()
    first, second = oids_of(game, BEAR, 0)
    return game, first, second


def ctx(game) -> EffectContext:
    return EffectContext(state=game.state, controller=0, source_oid=None)


def count(game) -> int:
    return evaluate_value(ctx(game), COUNT)


def hit(game, pid: int, oid: int, *, combat: bool = True) -> None:
    damage_player(game.state, pid, 2, oid, is_combat=combat)


class TestTheCount:
    def test_two_players_damaged_count_two(self, builder):
        game, a, b = board(builder)
        hit(game, 1, a)
        hit(game, 3, b)
        assert select_players(ctx(game), ANY) == [1, 3]
        assert count(game) == 2

    def test_a_player_damaged_twice_counts_once(self, builder):
        game, a, b = board(builder)
        hit(game, 2, a)
        hit(game, 2, b)
        hit(game, 2, a)
        assert count(game) == 1

    def test_noncombat_damage_does_not_count(self, builder):
        game, a, _ = board(builder)
        hit(game, 1, a, combat=False)
        assert game.state.turn_ledger.damage_taken[1] == 2
        assert count(game) == 0

    def test_nobody_hit_is_nobody(self, builder):
        game, _, _ = board(builder)
        assert select_players(ctx(game), ANY) == []
        assert count(game) == 0

    def test_the_controller_hit_is_counted_too(self, builder):
        # "each player", not "each opponent": your own seat is a player.
        game, a, _ = board(builder)
        hit(game, 0, a)
        assert count(game) == 1


class TestTheSourceLeaving:
    def test_reentering_does_not_drop_the_player(self, builder):
        game, a, _ = board(builder)
        hit(game, 1, a)
        move_object(game.state, a, Zone.EXILE)
        move_object(game.state, a, Zone.BATTLEFIELD)
        # The per-oid record is the near miss: it forgets, as 400.7 says it must.
        assert game.state.turn_ledger.players_dealt_combat_damage_by.get(a, set()) == set()
        assert count(game) == 1

    def test_dying_does_not_drop_the_player(self, builder):
        game, a, _ = board(builder)
        hit(game, 2, a)
        move_object(game.state, a, Zone.GRAVEYARD)
        assert count(game) == 1


class TestAcrossTurns:
    def test_a_real_combat_records_and_the_next_turn_clears_it(self, builder):
        game, a, b = board(builder)
        started = game.state.turn
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=a,
                               targets=(TargetRef.player(1),)))
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=b,
                               targets=(TargetRef.player(2),)))
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        for _ in range(300):
            if game.state.turn_ledger.players_dealt_combat_damage or game.over:
                break
            game.apply(_default_answer(game, game.pending()))
        assert count(game) == 2
        for _ in range(300):
            if game.state.turn > started or game.over:
                break
            game.apply(_default_answer(game, game.pending()))
        assert game.state.turn > started
        assert count(game) == 0


def attack(game, attacks: dict[int, int]) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid, pid in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid,
                               targets=(TargetRef.player(pid),)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def second_main(game) -> None:
    """The postcombat main phase, with the Stampede's delayed trigger resolved."""
    for _ in range(300):
        if (game.state.step is Step.POSTCOMBAT_MAIN and not game.state.stack
                and game.pending() is not None and game.pending().player == 0
                and game.pending().kind is DecisionKind.PRIORITY):
            return
        game.apply(_default_answer(game, game.pending()))
    raise AssertionError("did not reach the second main phase")


class TestTheCard:
    def cast(self, builder):
        b = (
            builder(players=4)
            .battlefield(0, [BEAR, BEAR, BEAR] + ["forest"] * 6)
            .hand(0, [STAMPEDE])
            .library(0, ["mountain"] * 10)
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
        )
        for pid in range(1, 4):
            b.battlefield(pid, [])
            b.library(pid, ["mountain"] * 10)
        game = b.build()
        game.apply(action_for_card(game, ActionKind.CAST, STAMPEDE))
        settle(game)
        return game, oids_of(game, BEAR, 0)

    def test_it_grants_the_three_keywords(self, builder):
        game, bears = self.cast(builder)
        for oid in bears:
            assert {"vigilance", "trample", "melee"} <= keywords(game, oid)

    def test_it_draws_one_per_player_hit_not_per_hit(self, builder):
        game, (a, b, c) = self.cast(builder)
        hand = len(game.state.players[0].hand)
        attack(game, {a: 1, b: 2, c: 2})
        second_main(game)
        assert len(game.state.players[0].hand) == hand + 2

    def test_without_damage_it_draws_nothing(self, builder):
        game, _ = self.cast(builder)
        hand = len(game.state.players[0].hand)
        started = game.state.turn
        attack(game, {})
        pass_until(game, lambda g: g.state.turn > started)
        assert len(game.state.players[0].hand) == hand


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

    @pytest.mark.parametrize("subject", ["any", {"any_of": ["any", "self"]}])
    def test_any_loads(self, subject):
        compile_card(self.probe({"player_count": {"dealt_combat_damage_by": subject}}))

    @pytest.mark.parametrize("subject", ["all", "Any", {"any": True}, ["any"]])
    def test_near_misses_are_refused(self, subject):
        with pytest.raises(DslError, match="dealt_combat_damage_by"):
            compile_card(self.probe({"player_count": {"dealt_combat_damage_by": subject}}))
