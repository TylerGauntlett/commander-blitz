"""Agents and the arena.

The headline test is :meth:`TestHeuristicIsCompetent.test_heuristic_beats_random`
-- a real regression canary.  If a rules change quietly breaks combat or mana,
the heuristic stops converting its advantage and this test notices.
"""

from __future__ import annotations

import pytest

from automtg.ai.agents import HeuristicAgent, RandomAgent
from automtg.ai.agents.base import agent_by_name, play
from automtg.ai.arena import decks_for, run_matchup
from automtg.ai.stats import render_markdown, summarize, wilson_interval
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.game import create_game

GATE_WIN_RATE = 0.65
ARENA_GAMES = 60


@pytest.fixture(scope="module")
def duel_results():
    return run_matchup(("heuristic", "random"), pod_size=2, games=ARENA_GAMES, seed=100)


@pytest.fixture(scope="module")
def pod_results():
    return run_matchup(("heuristic", "random"), pod_size=4, games=24, seed=200)


class TestAgentBasics:
    def test_agents_return_a_legal_action(self):
        for agent in (RandomAgent(0), HeuristicAgent(0)):
            game = create_game(["aesi", "edgar"], seed=1)
            for _ in range(200):
                if game.over:
                    break
                actions = game.legal_actions()
                chosen = agent.act(game, game.pending().player, actions)
                assert chosen in actions
                game.apply(chosen)

    def test_agent_lookup_by_name(self):
        assert agent_by_name("random").name == "random"
        assert agent_by_name("heuristic").name == "heuristic"
        with pytest.raises(ValueError):
            agent_by_name("telepath")

    def test_agents_are_deterministic_for_a_seed(self):
        def run(seed: int) -> list[str]:
            game = create_game(["aesi", "edgar"], seed=seed)
            play(game, {0: HeuristicAgent(seed), 1: RandomAgent(seed)})
            return [e.describe() for e in game.state.events]

        assert run(3) == run(3)


class TestHeuristicBehaviour:
    def test_it_always_makes_its_land_drop(self):
        agent = HeuristicAgent(0)
        game = create_game(["aesi", "edgar"], seed=2)
        for _ in range(300):
            if game.over:
                break
            decision = game.pending()
            actions = game.legal_actions()
            lands = [a for a in actions if a.kind is ActionKind.PLAY_LAND]
            chosen = agent.act(game, decision.player, actions)
            if lands and decision.kind is DecisionKind.PRIORITY:
                assert chosen.kind is ActionKind.PLAY_LAND, "passed up a land drop"
            game.apply(chosen)

    def test_it_never_points_removal_at_its_own_creature(self):
        """A scoring bug here is invisible in win rates but obvious in play."""
        from automtg.cards.registry import CardRegistry
        from tests.conftest import CARD_DIR, TEST_CARD_DIR, GameBuilder

        paths = sorted(CARD_DIR.glob("*.cards.json")) + sorted(
            TEST_CARD_DIR.glob("*.cards.json")
        )
        registry = CardRegistry.from_paths(paths)
        game = (
            GameBuilder(registry, players=2, seed=0)
            .hand(0, ["terminate"])
            .battlefield(0, ["swamp", "mountain", "t_big"])
            .build()
        )
        agent = HeuristicAgent(0)
        chosen = agent.act(game, 0, game.legal_actions())
        assert chosen.kind is not ActionKind.CAST, "cast removal with only its own target"

    def test_it_blocks_when_blocking_is_free(self):
        from automtg.cards.registry import CardRegistry
        from tests.conftest import CARD_DIR, TEST_CARD_DIR, GameBuilder

        paths = sorted(CARD_DIR.glob("*.cards.json")) + sorted(
            TEST_CARD_DIR.glob("*.cards.json")
        )
        registry = CardRegistry.from_paths(paths)
        game = (
            GameBuilder(registry, players=2, seed=0)
            .battlefield(0, ["t_bear"])
            .battlefield(1, ["t_big"])
            .build()
        )
        agent = HeuristicAgent(0)
        # Advance to blockers with player 0 attacking into a 6/6.
        from automtg.engine.structs import TargetRef
        from tests.conftest import find_action, only_oid, pass_until

        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        bear = only_oid(game, "t_bear", 0)
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=bear, targets=(TargetRef.player(1),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS,
        )
        chosen = agent.act(game, 1, game.legal_actions())
        assert chosen.kind is ActionKind.ADD_BLOCKER, "declined a free profitable block"


class TestHeuristicIsCompetent:
    def test_heuristic_beats_random(self, duel_results):
        summary = summarize(duel_results)[2]
        rate = summary.win_rate("heuristic")
        assert rate >= GATE_WIN_RATE, (
            f"heuristic won only {rate:.1%} of {summary.games_by_agent['heuristic']} duels"
        )

    def test_duels_finish_decisively(self, duel_results):
        summary = summarize(duel_results)[2]
        assert summary.draw_rate <= 0.05, f"{summary.draw_rate:.1%} of duels were draws"

    def test_duel_length_is_reasonable(self, duel_results):
        summary = summarize(duel_results)[2]
        assert 8 <= summary.median_turns <= 40, f"median {summary.median_turns} turns"

    def test_four_player_pods_finish(self, pod_results):
        summary = summarize(pod_results)[4]
        assert summary.draw_rate <= 0.20, f"{summary.draw_rate:.1%} of pods were draws"
        assert summary.games == 24

    def test_heuristic_leads_in_four_player_pods_too(self, pod_results):
        summary = summarize(pod_results)[4]
        assert summary.win_rate("heuristic") > summary.win_rate("random")


class TestArenaPlumbing:
    def test_pod_seating_mirrors_the_two_decks(self):
        assert decks_for(2) == ["aesi", "edgar"]
        assert decks_for(4) == ["aesi", "edgar", "aesi", "edgar"]

    def test_seat_rotation_keeps_agents_balanced(self, duel_results):
        summary = summarize(duel_results)[2]
        assert summary.games_by_agent["heuristic"] == ARENA_GAMES
        assert summary.games_by_agent["random"] == ARENA_GAMES

    def test_results_are_reproducible(self):
        first = run_matchup(("heuristic", "random"), pod_size=2, games=4, seed=42)
        second = run_matchup(("heuristic", "random"), pod_size=2, games=4, seed=42)
        assert [r.to_dict() for r in first] == [r.to_dict() for r in second]

    def test_markdown_report_renders(self, duel_results):
        text = render_markdown(summarize(duel_results))
        assert "# Arena results" in text
        assert "2-player pods" in text

    def test_wilson_interval_brackets_the_estimate(self):
        low, high = wilson_interval(8, 10)
        assert low < 0.8 < high
        assert wilson_interval(0, 0) == (0.0, 0.0)
