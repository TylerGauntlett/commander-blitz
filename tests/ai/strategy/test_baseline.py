"""The baseline every deck gets (`DefaultStrategy`), position by position.

Each test builds the spot where the classic agent did something no competent
player would, and checks the deck-aware agent does not. A seat with no deck id
gets `DefaultStrategy`, so these need no deck at all.
"""

from __future__ import annotations

import pytest

from automtg.ai.agents.base import agent_by_name
from automtg.ai.agents.heuristic_agent import HeuristicAgent
from automtg.ai.strategy import CLASSIC, DeckPlan, DefaultStrategy
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until


def at_attacks(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    return game


def first_attack(game, seat: int = 0):
    return HeuristicAgent(0).act(game, seat, game.legal_actions())


class TestAttacks:
    def test_a_big_creature_is_not_traded_for_a_deathtoucher(self, builder):
        game = at_attacks(
            builder().battlefield(0, ["t_big"]).battlefield(1, ["typhoid_rats"]).build()
        )
        classic = HeuristicAgent(0, classic=True).act(game, 0, game.legal_actions())
        assert classic.kind is ActionKind.ADD_ATTACKER, "the old agent took this trade"
        assert first_attack(game).kind is ActionKind.FINISH_DECLARATION

    def test_it_swings_everything_when_the_opponent_is_dead_on_board(self, builder):
        game = at_attacks(
            builder()
            .battlefield(0, ["t_bear", "t_bear", "t_bear"])
            .battlefield(1, ["t_big"])
            .life(1, 4)
            .build()
        )
        # Three 2/2s, one blocker: four damage gets through, and they are on four.
        assert first_attack(game).kind is ActionKind.ADD_ATTACKER

    def test_it_holds_back_when_the_crack_back_would_kill_it(self, builder):
        game = at_attacks(
            builder()
            .battlefield(0, ["t_big"])
            .battlefield(1, ["t_big"], tapped=True)
            .life(0, 6)
            .build()
        )
        classic = HeuristicAgent(0, classic=True).act(game, 0, game.legal_actions())
        assert classic.kind is ActionKind.ADD_ATTACKER, "the old agent swung into the crack-back"
        assert first_attack(game).kind is ActionKind.FINISH_DECLARATION

    def test_it_still_attacks_when_the_attack_is_free(self, builder):
        game = at_attacks(
            builder().battlefield(0, ["t_big"]).battlefield(1, ["t_bear"], tapped=True).build()
        )
        assert first_attack(game).kind is ActionKind.ADD_ATTACKER


class TestBlocks:
    def test_it_chumps_when_the_damage_would_kill_it(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_big"])
            .battlefield(1, ["t_bear"])
            .active(0)
            .life(1, 6)
            .build()
        )
        at_attacks(game)
        big = only_oid(game, "t_big", 0)
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=big, targets=(TargetRef.player(1),))
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)
        chosen = HeuristicAgent(0).act(game, 1, game.legal_actions())
        assert chosen.kind is ActionKind.ADD_BLOCKER


class TestPlayerTargets:
    def test_mill_goes_at_the_shortest_library_and_never_at_itself(self, builder):
        game = (
            builder(players=3)
            .hand(0, ["traumatize"])
            .battlefield(0, ["island"] * 5)
            .library(0, ["island"] * 3)
            .library(1, ["island"] * 30)
            .library(2, ["island"] * 12)
            .build()
        )
        chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
        assert chosen.kind is ActionKind.CAST
        assert [ref.id for ref in chosen.targets if ref.kind == "player"] == [2]


class TestLands:
    def test_it_plays_the_colour_its_hand_needs(self, builder):
        game = (
            builder()
            .hand(0, ["mountain", "island", "counterspell"])
            .battlefield(0, ["forest"])
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
        assert chosen.kind is ActionKind.PLAY_LAND
        assert game.state.objects[chosen.source].def_id == "island"


class TestMulligans:
    @pytest.mark.parametrize(
        ("hand", "keep"),
        [
            (["island", "island", "island", "grizzly_bears", "hill_giant", "divination", "traumatize"], True),
            (["island", "island", "island", "traumatize", "traumatize", "traumatize", "traumatize"], False),
            (["island"] + ["grizzly_bears"] * 6, False),
        ],
    )
    def test_a_hand_needs_lands_and_an_early_play(self, builder, hand, keep):
        game = builder().hand(0, hand).build()
        assert DefaultStrategy().keep_hand(game.state, 0) is keep


class TestModes:
    def test_a_counter_mode_is_worthless_with_nothing_to_counter(self, builder):
        game = builder().build()
        strategy = DefaultStrategy()
        counter = strategy.mode_score(game.state, 0, [{"op": "counter"}])
        draw = strategy.mode_score(game.state, 0, [{"op": "draw", "count": 2}])
        assert draw > 0 > counter


class TestProtection:
    def test_protected_cards_are_the_last_thing_given_up(self, builder):
        game = builder().battlefield(0, ["t_bear", "t_big"]).build()
        strategy = DefaultStrategy(DeckPlan(deck_id="x", archetype="test", protect=frozenset({"t_big"})))
        big = only_oid(game, "t_big", 0)
        bear = only_oid(game, "t_bear", 0)
        assert strategy.junk_value(game.state, 0, big, 0.0) < strategy.junk_value(game.state, 0, bear, 0.0)


class TestClassic:
    def test_the_classic_agent_is_the_neutral_strategy(self, builder):
        game = builder().build()
        assert HeuristicAgent(0, classic=True).strategy_of(game.state, 0) is CLASSIC
        assert agent_by_name("heuristic_classic").strategy is CLASSIC

    def test_the_environment_can_ask_for_it(self, monkeypatch):
        monkeypatch.setenv("AUTOMTG_CPU", "classic")
        assert agent_by_name("heuristic").strategy is CLASSIC
        monkeypatch.delenv("AUTOMTG_CPU")
        assert agent_by_name("heuristic").strategy is None

    def test_an_unknown_deck_gets_the_baseline(self, builder):
        game = builder().deck(0, "somebody_s_import").build()
        assert isinstance(HeuristicAgent(0).strategy_of(game.state, 0), DefaultStrategy)
