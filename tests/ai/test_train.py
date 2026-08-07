"""The policy network and the self-play trainer.

Skipped entirely when torch is absent, so the base install stays light.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="requires the [train] extra")

from automtg.ai import action_space, encoding  # noqa: E402
from automtg.ai.agents.base import play  # noqa: E402
from automtg.ai.agents.policy_agent import PolicyAgent  # noqa: E402
from automtg.ai.agents.random_agent import RandomAgent  # noqa: E402
from automtg.ai.env import make_env  # noqa: E402
from automtg.ai.model import ModelConfig, build_model, load, save, to_batch  # noqa: E402
from automtg.ai.train import TrainConfig, train  # noqa: E402
from automtg.engine.game import create_game  # noqa: E402


@pytest.fixture(scope="module")
def vocab(real_registry):
    return encoding.CardVocabulary(real_registry)


@pytest.fixture(scope="module")
def model(vocab):
    return build_model(ModelConfig(n_cards=len(vocab)))


def sample_batch(seed: int = 0, count: int = 4):
    env = make_env(seed=seed)
    observation, _ = env.reset()
    observations = [observation]
    rng = np.random.default_rng(seed)
    for _ in range(count - 1):
        legal = np.flatnonzero(observation["action_mask"])
        observation, _, terminated, _, _ = env.step(int(rng.choice(legal)))
        observations.append(observation)
        if terminated:
            break
    return observations


class TestModel:
    def test_forward_produces_a_logit_per_action(self, model):
        scalar, card_ids, mask = to_batch(sample_batch())
        logits, values = model(scalar, card_ids, mask)
        assert logits.shape == (scalar.shape[0], action_space.ACTION_SPACE_SIZE)
        assert values.shape == (scalar.shape[0],)

    def test_illegal_actions_get_negative_infinity(self, model):
        scalar, card_ids, mask = to_batch(sample_batch())
        logits, _ = model(scalar, card_ids, mask)
        assert torch.isinf(logits[mask <= 0]).all()
        assert torch.isfinite(logits[mask > 0]).all()

    def test_sampling_only_ever_picks_a_legal_action(self, model):
        observations = sample_batch(seed=3, count=6)
        scalar, card_ids, mask = to_batch(observations)
        for _ in range(20):
            actions, _, _ = model.act(scalar, card_ids, mask)
            for row, action in enumerate(actions.tolist()):
                assert mask[row, action] > 0

    def test_greedy_is_deterministic(self, model):
        scalar, card_ids, mask = to_batch(sample_batch(seed=5))
        first, _, _ = model.act(scalar, card_ids, mask, greedy=True)
        second, _, _ = model.act(scalar, card_ids, mask, greedy=True)
        assert torch.equal(first, second)

    def test_checkpoints_round_trip(self, model, vocab, tmp_path: Path):
        path = tmp_path / "policy.pt"
        save(model, path, ModelConfig(n_cards=len(vocab)))
        restored, config = load(path)
        assert config.n_cards == len(vocab)
        scalar, card_ids, mask = to_batch(sample_batch(seed=7))
        original, _ = model(scalar, card_ids, mask)
        reloaded, _ = restored(scalar, card_ids, mask)
        assert torch.allclose(original, reloaded, atol=1e-6)


class TestPolicyAgent:
    def test_falls_back_to_the_heuristic_without_a_checkpoint(self):
        agent = PolicyAgent()
        game = create_game(["aesi", "edgar"], seed=1)
        for _ in range(60):
            if game.over:
                break
            actions = game.legal_actions()
            chosen = agent.act(game, game.pending().player, actions)
            assert chosen in actions
            game.apply(chosen)

    def test_a_trained_policy_plays_legal_actions(self, model, vocab, tmp_path: Path):
        path = tmp_path / "policy.pt"
        save(model, path, ModelConfig(n_cards=len(vocab)))
        agent = PolicyAgent(str(path), vocab=vocab)
        game = create_game(["aesi", "edgar"], seed=2)
        for _ in range(200):
            if game.over:
                break
            actions = game.legal_actions()
            chosen = agent.act(game, game.pending().player, actions)
            assert chosen in actions
            game.apply(chosen)

    def test_an_untrained_policy_can_finish_a_game(self, model, vocab, tmp_path: Path):
        path = tmp_path / "policy.pt"
        save(model, path, ModelConfig(n_cards=len(vocab)))
        game = create_game(["aesi", "edgar"], seed=4)
        play(game, {0: PolicyAgent(str(path), vocab=vocab), 1: RandomAgent(1)})
        assert game.over


class TestTraining:
    @pytest.mark.slow
    def test_a_short_run_completes_and_writes_a_checkpoint(self, tmp_path: Path):
        config = TrainConfig(
            pod_size=2, updates=2, steps_per_update=64, minibatch=32, out_dir=tmp_path
        )
        path = train(config)
        assert path.exists()
        assert (tmp_path / "pod2" / "history.json").exists()
        restored, _ = load(path)
        assert restored is not None

    @pytest.mark.slow
    def test_four_player_training_uses_a_separate_checkpoint(self, tmp_path: Path):
        config = TrainConfig(
            pod_size=4, updates=1, steps_per_update=48, minibatch=16, out_dir=tmp_path
        )
        path = train(config)
        assert path.parent.name == "pod4"
