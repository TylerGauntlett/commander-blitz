"""The Gymnasium environment and the observation encoder."""

from __future__ import annotations

import numpy as np
import pytest

from commanderblitz.ai import action_space, encoding
from commanderblitz.ai.env import MtgEnv, make_env


def rollout(env: MtgEnv, seed: int, limit: int = 4000) -> dict:
    obs, _ = env.reset(seed=seed)
    steps = 0
    total = 0.0
    rng = np.random.default_rng(seed)
    while steps < limit:
        mask = obs["action_mask"]
        legal = np.flatnonzero(mask)
        assert legal.size >= 1
        action = int(rng.choice(legal))
        obs, reward, terminated, truncated, info = env.step(action)
        total += reward
        steps += 1
        if terminated or truncated:
            return {"steps": steps, "reward": total, "info": info}
    raise AssertionError("episode did not terminate")


class TestSpaces:
    def test_observation_matches_its_space(self):
        env = make_env(seed=0)
        obs, _ = env.reset()
        assert env.observation_space.contains(obs), "observation is outside its declared space"

    def test_scalar_vector_is_finite_and_bounded(self):
        env = make_env(seed=1)
        obs, _ = env.reset()
        scalar = obs["scalar"]
        assert scalar.shape == (encoding.OBS_DIM,)
        assert scalar.dtype == np.float32
        assert np.isfinite(scalar).all()
        assert (scalar >= -1.0).all() and (scalar <= 1.0).all()

    def test_card_ids_are_within_the_vocabulary(self):
        env = make_env(seed=2)
        obs, _ = env.reset()
        cards = obs["card_ids"]
        assert cards.shape == (encoding.CARD_SLOTS,)
        assert (cards >= 0).all() and (cards < len(env.vocab)).all()

    def test_action_space_is_a_fixed_discrete(self):
        env = make_env()
        assert env.action_space.n == action_space.ACTION_SPACE_SIZE


class TestEpisodes:
    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    def test_two_player_episodes_terminate(self, seed):
        env = make_env(seed=seed)
        result = rollout(env, seed)
        assert result["info"]["turns"] >= 1

    @pytest.mark.parametrize("seed", [0, 1])
    def test_four_player_episodes_terminate(self, seed):
        env = make_env(["aesi", "edgar", "aesi", "edgar"], seed=seed)
        result = rollout(env, seed)
        assert result["info"]["turns"] >= 1

    def test_terminal_reward_is_win_loss_or_draw(self):
        env = make_env(seed=5)
        result = rollout(env, 5)
        assert result["reward"] in (1.0, -1.0, 0.0)

    def test_four_player_loss_is_split(self):
        """Rewards in a pod sum to zero so no seat is intrinsically favoured."""
        env = make_env(["aesi", "edgar", "aesi", "edgar"], seed=9)
        result = rollout(env, 9)
        assert result["reward"] in (1.0, -1.0 / 3.0, 0.0)

    def test_mask_only_offers_legal_actions_during_a_rollout(self):
        env = make_env(seed=3, strict=True)
        obs, _ = env.reset()
        rng = np.random.default_rng(3)
        for _ in range(300):
            legal = np.flatnonzero(obs["action_mask"])
            obs, _, terminated, truncated, info = env.step(int(rng.choice(legal)))
            assert "illegal_action" not in info
            if terminated or truncated:
                break


class TestDeterminism:
    def test_same_seed_gives_the_same_game(self):
        first = make_env(seed=11)
        second = make_env(seed=11)
        a, _ = first.reset()
        b, _ = second.reset()
        assert np.array_equal(a["scalar"], b["scalar"])
        assert np.array_equal(a["card_ids"], b["card_ids"])

    def test_event_logs_match_for_identical_seeds(self):
        from commanderblitz.ai.agents import RandomAgent
        from commanderblitz.ai.agents.base import play
        from commanderblitz.engine.game import create_game

        def fingerprint(seed: int) -> list[str]:
            game = create_game(["aesi", "edgar"], seed=seed)
            play(game, {0: RandomAgent(seed), 1: RandomAgent(seed + 1)})
            return [e.describe() for e in game.state.events]

        assert fingerprint(4) == fingerprint(4)

    def test_different_seeds_give_different_games(self):
        from commanderblitz.ai.agents import RandomAgent
        from commanderblitz.ai.agents.base import play
        from commanderblitz.engine.game import create_game

        def fingerprint(seed: int) -> list[str]:
            game = create_game(["aesi", "edgar"], seed=seed)
            play(game, {0: RandomAgent(seed), 1: RandomAgent(seed + 1)})
            return [e.describe() for e in game.state.events]

        assert fingerprint(4) != fingerprint(5)


class TestEncoderLayout:
    def test_declared_dimension_matches_what_is_written(self):
        """The encoder asserts this internally; this makes the failure explicit."""
        env = make_env(seed=0)
        env.reset()
        obs = encoding.encode(env.game.state, 0, env.vocab)
        assert obs["scalar"].shape[0] == encoding.OBS_DIM

    def test_seat_features_are_relative_to_the_viewer(self):
        env = make_env(["aesi", "edgar", "aesi", "edgar"], seed=1)
        env.reset()
        state = env.game.state
        from_seat_0 = encoding.encode(state, 0, env.vocab)["scalar"]
        from_seat_1 = encoding.encode(state, 1, env.vocab)["scalar"]
        # Slot 0 is always "me", so the two views cannot be identical.
        assert not np.array_equal(from_seat_0, from_seat_1)
