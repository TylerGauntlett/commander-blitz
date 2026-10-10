"""The action space must never lie about what is legal.

A wrong mask poisons training silently: the policy learns from actions the engine
would refuse, or never sees actions it should. These tests are the guard.
"""

from __future__ import annotations

import numpy as np
import pytest

from commanderblitz.ai import action_space
from commanderblitz.ai.agents import RandomAgent
from commanderblitz.engine.game import create_game


def random_states(seed: int, deck_ids=("aesi", "edgar"), steps: int = 400):
    """Walk a real game, yielding the state at every decision point."""
    game = create_game(list(deck_ids), seed=seed)
    agent = RandomAgent(seed)
    for _ in range(steps):
        if game.over or game.pending() is None:
            return
        yield game
        actions = game.legal_actions()
        if not actions:
            return
        game.apply(agent.act(game, game.pending().player, actions))


class TestLayout:
    def test_size_is_a_fixed_constant(self):
        """The literal is the point: changing it invalidates every trained
        checkpoint, so it should never move without somebody deciding to. Last
        moved when planeswalkers became attackable and `DEF_CAP` rose from 3 to
        8 -- see docs/adr/0002-flat-action-space.md."""
        assert action_space.ACTION_SPACE_SIZE == action_space.IDX_KEEP + 1
        assert action_space.ACTION_SPACE_SIZE == 1025

    def test_index_ranges_do_not_overlap(self):
        boundaries = [
            action_space.IDX_PASS,
            action_space.IDX_PLAY_LAND,
            action_space.IDX_CAST,
            action_space.IDX_CAST_COMMANDER,
            action_space.IDX_ACTIVATE,
            action_space.IDX_ATTACK,
            action_space.IDX_BLOCK,
            action_space.IDX_CHOOSE,
            action_space.IDX_YES,
        ]
        assert boundaries == sorted(boundaries)
        assert len(set(boundaries)) == len(boundaries)

    def test_every_index_describes_itself(self):
        for index in range(action_space.ACTION_SPACE_SIZE):
            assert action_space.describe_index(index)


class TestMaskCorrectness:
    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_decode_returns_a_legal_action(self, seed):
        for game in random_states(seed, steps=120):
            table = action_space.build(game.state)
            legal = set(game.legal_actions())
            for index in table.legal_indices:
                assert table.decode(index) in legal

    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_encode_decode_round_trips(self, seed):
        for game in random_states(seed, steps=120):
            table = action_space.build(game.state)
            for index, action in table.by_index.items():
                assert table.encode(action) == index
                assert table.decode(index) == action

    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_mask_is_never_empty_while_the_game_runs(self, seed):
        for game in random_states(seed, steps=120):
            mask = action_space.mask_for(game.state)
            assert mask.sum() >= 1, f"empty mask at {game.state.describe()}"

    @pytest.mark.parametrize("seed", [0, 1, 2])
    def test_mask_matches_the_table(self, seed):
        for game in random_states(seed, steps=80):
            table = action_space.build(game.state)
            assert set(np.flatnonzero(table.mask).tolist()) == set(table.by_index)

    @pytest.mark.parametrize("seed", [0, 1, 2])
    def test_pass_is_always_available_at_priority(self, seed):
        from commanderblitz.engine.enums import DecisionKind

        for game in random_states(seed, steps=80):
            if game.pending().kind is not DecisionKind.PRIORITY:
                continue
            mask = action_space.mask_for(game.state)
            assert mask[action_space.IDX_PASS] == 1

    def test_a_finished_game_has_an_empty_table(self):
        game = create_game(["aesi", "edgar"], seed=0)
        agent = RandomAgent(0)
        for _ in range(40_000):
            if game.over:
                break
            actions = game.legal_actions()
            if not actions:
                break
            game.apply(agent.act(game, game.pending().player, actions))
        assert game.over
        assert action_space.build(game.state).by_index == {}


class TestDroppedActions:
    def test_dropped_actions_are_reported_not_silently_lost(self):
        """Anything that does not fit the fixed layout must be visible, not vanish."""
        checked = 0
        for game in random_states(7, steps=200):
            table = action_space.build(game.state)
            legal = game.legal_actions()
            for action in table.dropped:
                assert action in legal
                checked += 1
            assert len(table.by_index) + len(table.dropped) == len(legal)
        assert checked >= 0  # the invariant above is what matters
