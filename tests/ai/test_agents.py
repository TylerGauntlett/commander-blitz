"""Agents and the arena.

The headline test is :meth:`TestHeuristicIsCompetent.test_heuristic_beats_random`
-- a real regression canary.  If a rules change quietly breaks combat or mana,
the heuristic stops converting its advantage and this test notices.
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.agents import HeuristicAgent, RandomAgent
from commanderblitz.ai.agents.base import agent_by_name, play
from commanderblitz.ai.arena import decks_for, run_matchup
from commanderblitz.ai.stats import render_markdown, summarize, wilson_interval
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.game import create_game

GATE_WIN_RATE = 0.65
ARENA_GAMES = 60
#: The canary is the pre-strategy heuristic. It exists to catch a rules change
#: that breaks combat or mana, which the classic agent shows as well as any; the
#: deck plans keep boards bigger and games several times slower to simulate, and
#: they have their own tests in `tests/ai/strategy/`.
CANARY = "heuristic_classic"


@pytest.fixture(scope="module")
def duel_results():
    return run_matchup((CANARY, "random"), pod_size=2, games=ARENA_GAMES, seed=100)


@pytest.fixture(scope="module")
def pod_results():
    return run_matchup((CANARY, "random"), pod_size=4, games=24, seed=200)


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
        """Every turn a land could be played, one is -- not necessarily first.

        A landfall deck casts its payoff before the land so the land triggers
        it (Aesi's plan does exactly that), so the question is whether the turn
        ends with the drop unused, not whether the first action was the land.
        """
        agent = HeuristicAgent(0)
        game = create_game(["aesi", "edgar"], seed=2)
        could: set[tuple[int, int]] = set()
        did: set[tuple[int, int]] = set()
        for _ in range(300):
            if game.over:
                break
            decision = game.pending()
            actions = game.legal_actions()
            turn = (game.state.turn, decision.player)
            if decision.kind is DecisionKind.PRIORITY and any(
                a.kind is ActionKind.PLAY_LAND for a in actions
            ):
                could.add(turn)
            chosen = agent.act(game, decision.player, actions)
            if chosen.kind is ActionKind.PLAY_LAND:
                did.add(turn)
            game.apply(chosen)
        current = (game.state.turn, game.state.active_player)
        assert could - did - {current} == set(), "passed up a land drop"

    def test_it_never_points_removal_at_its_own_creature(self):
        """A scoring bug here is invisible in win rates but obvious in play."""
        from commanderblitz.cards.registry import CardRegistry
        from commanderblitz.engine.sandbox import GameBuilder
        from tests.conftest import CARD_DIR, TEST_CARD_DIR

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
        from commanderblitz.cards.registry import CardRegistry
        from commanderblitz.engine.sandbox import GameBuilder
        from tests.conftest import CARD_DIR, TEST_CARD_DIR

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
        from commanderblitz.engine.structs import TargetRef
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


class TestHeuristicDoesNotSelfDestruct:
    """Activated abilities used to score a flat 5.0, beating PASS every time.

    So the agent re-activated the same ability at every priority window until
    the cost stopped being payable: Adanto Vanguard's "Pay 4 life" ran it from
    40 down to 3, and Bloodthrone Vampire ate its own board. The value function
    now asks the turn ledger whether it has already done this, and whether the
    ability is a combat trick worth using at all.
    """

    def _blocked_vanguard(self, builder, life: int = 40):
        """Seat 0's Adanto Vanguard attacking into a block, priority to seat 0."""
        from commanderblitz.engine.structs import TargetRef
        from tests.conftest import find_action, only_oid, pass_until

        game = (
            builder(players=2)
            .battlefield(0, ["adanto_vanguard"])
            .battlefield(1, ["t_big"])
            .life(0, life)
            .build()
        )
        vanguard = only_oid(game, "adanto_vanguard", 0)
        big = only_oid(game, "t_big", 1)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=vanguard, targets=(TargetRef.player(1),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_BLOCKER, source=big, targets=(TargetRef.obj(vanguard),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        return game, vanguard

    def _activations_of(self, game, agent, seat: int, oid: int, limit: int = 40) -> int:
        """How many times the agent activates ``oid`` before the turn ends."""
        turn = game.state.turn
        count = 0
        for _ in range(limit):
            decision = game.pending()
            if decision is None or game.over or game.state.turn != turn:
                break
            chosen = agent.act(game, decision.player, game.legal_actions())
            if (
                decision.player == seat
                and chosen.kind is ActionKind.ACTIVATE
                and chosen.source == oid
            ):
                count += 1
            game.apply(chosen)
        return count

    def test_it_uses_a_combat_trick_once_and_not_again_that_turn(self, builder):
        game, vanguard = self._blocked_vanguard(builder)
        agent = HeuristicAgent(0)
        used = self._activations_of(game, agent, 0, vanguard)
        assert used == 1, f"activated Adanto Vanguard {used} times in one turn"
        assert game.state.players[0].life == 36

    def test_it_does_not_pay_life_it_cannot_spare(self, builder):
        game, vanguard = self._blocked_vanguard(builder, life=12)
        agent = HeuristicAgent(0)
        assert self._activations_of(game, agent, 0, vanguard) == 0
        assert game.state.players[0].life == 12

    def test_it_does_not_pay_life_outside_combat(self, builder):
        """Indestructible until end of turn buys nothing in a main phase."""
        from tests.conftest import only_oid

        game = (
            builder(players=2)
            .battlefield(0, ["adanto_vanguard"])
            .life(0, 40)
            .build()
        )
        agent = HeuristicAgent(0)
        chosen = agent.act(game, 0, game.legal_actions())
        assert chosen.source != only_oid(game, "adanto_vanguard", 0) or (
            chosen.kind is not ActionKind.ACTIVATE
        )

    def test_it_does_not_sacrifice_its_board_for_a_pump(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["bloodthrone_vampire", "t_bear"])
            .build()
        )
        agent = HeuristicAgent(0)
        chosen = agent.act(game, 0, game.legal_actions())
        assert chosen.kind is not ActionKind.ACTIVATE, "sacrificed a creature for +2/+2"

    def test_it_never_repeats_a_non_mana_ability_in_one_turn(self):
        """The property, over a real game rather than one built position."""
        from commanderblitz.engine.characteristics import abilities_of

        game = create_game(["edgar", "aesi"], seed=5)
        agents = {0: HeuristicAgent(0), 1: HeuristicAgent(1)}
        seen: set[tuple[int, int, int]] = set()
        for _ in range(600):
            if game.over:
                break
            decision = game.pending()
            if decision is None:
                break
            chosen = agents[decision.player].act(game, decision.player, game.legal_actions())
            if chosen.kind is ActionKind.ACTIVATE and chosen.source is not None:
                abilities = abilities_of(game.state, chosen.source)
                index = chosen.ability_index
                usable = index is not None and 0 <= index < len(abilities)
                if usable and not abilities[index].is_mana_ability:
                    key = (game.state.turn, chosen.source, index)
                    assert key not in seen, f"repeated ability {key} in one turn"
                    seen.add(key)
            game.apply(chosen)


class TestHeuristicIsCompetent:
    def test_heuristic_beats_random(self, duel_results):
        summary = summarize(duel_results)[2]
        rate = summary.win_rate(CANARY)
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
        assert summary.win_rate(CANARY) > summary.win_rate("random")


class TestArenaPlumbing:
    def test_pod_seating_mirrors_the_two_decks(self):
        assert decks_for(2) == ["aesi", "edgar"]
        assert decks_for(4) == ["aesi", "edgar", "aesi", "edgar"]

    def test_seat_rotation_keeps_agents_balanced(self, duel_results):
        summary = summarize(duel_results)[2]
        assert summary.games_by_agent[CANARY] == ARENA_GAMES
        assert summary.games_by_agent["random"] == ARENA_GAMES

    def test_results_are_reproducible(self):
        first = run_matchup((CANARY, "random"), pod_size=2, games=4, seed=42)
        second = run_matchup((CANARY, "random"), pod_size=2, games=4, seed=42)
        assert [r.to_dict() for r in first] == [r.to_dict() for r in second]

    def test_markdown_report_renders(self, duel_results):
        text = render_markdown(summarize(duel_results))
        assert "# Arena results" in text
        assert "2-player pods" in text

    def test_wilson_interval_brackets_the_estimate(self):
        low, high = wilson_interval(8, 10)
        assert low < 0.8 < high
        assert wilson_interval(0, 0) == (0.0, 0.0)
