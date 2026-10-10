"""The policy network and the self-play trainer.

Skipped entirely when torch is absent, so the base install stays light.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="requires the [train] extra")

from commanderblitz.ai import action_space, encoding  # noqa: E402
from commanderblitz.ai.agents.base import play  # noqa: E402
from commanderblitz.ai.agents.policy_agent import PolicyAgent  # noqa: E402
from commanderblitz.ai.agents.random_agent import RandomAgent  # noqa: E402
from commanderblitz.ai.env import make_env  # noqa: E402
from commanderblitz.ai.model import (  # noqa: E402
    ModelConfig,
    build_model,
    load,
    load_vocab_ids,
    save,
    to_batch,
)
from commanderblitz.ai.train import TrainConfig, train  # noqa: E402
from commanderblitz.engine.game import create_game  # noqa: E402


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


class TestACheckpointRemembersItsCardList:
    """Why the vocabulary travels with the weights.

    `CardVocabulary` indexes `sorted(registry.ids())`. Adding a card that sorts
    early -- which shipping a new precon does a hundred times over -- shifts the
    index of every card after it. The checkpoint then loads *without complaint*
    and reads the wrong embedding for most of the pool, which is a far worse
    failure than the loud one of running off the end of the table.
    """

    def test_the_ids_are_saved_alongside_the_weights(self, model, vocab, tmp_path: Path):
        path = tmp_path / "policy.pt"
        save(model, path, ModelConfig(n_cards=len(vocab)), vocab.ids)
        assert load_vocab_ids(path) == vocab.ids

    def test_an_older_checkpoint_without_them_is_not_an_error(self, model, vocab, tmp_path: Path):
        # `load` must keep working on every checkpoint written before this
        # existed, which is why the ids sit beside `config` and not inside it.
        path = tmp_path / "old.pt"
        save(model, path, ModelConfig(n_cards=len(vocab)))
        assert load_vocab_ids(path) is None
        assert load(path)[1].n_cards == len(vocab)

    def test_a_saved_list_survives_the_registry_growing(self, model, vocab, tmp_path: Path):
        path = tmp_path / "policy.pt"
        save(model, path, ModelConfig(n_cards=len(vocab)), vocab.ids)
        agent = PolicyAgent(str(path))
        # Built from the checkpoint's list, not from today's registry, so every
        # card keeps the index it was trained under.
        assert agent.vocab.ids == vocab.ids
        assert agent.model is not None

    def test_an_older_checkpoint_against_a_grown_registry_falls_back_loudly(
        self, model, vocab, tmp_path: Path
    ):
        # No saved list and a size mismatch means the mapping is unrecoverable.
        # The heuristic is a worse player but a correct one; guessing is an
        # IndexError at best and nonsense at worst.
        #
        # Built at the smaller size, not merely labelled with it: this is a
        # checkpoint from before five cards were added, which is exactly what
        # every existing `runs/*.pt` becomes when a precon ships.
        stale_config = ModelConfig(n_cards=len(vocab) - 5)
        path = tmp_path / "stale.pt"
        save(build_model(stale_config), path, stale_config)
        with pytest.warns(RuntimeWarning, match="[Rr]etrain"):
            agent = PolicyAgent(str(path))
        assert agent.model is None


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
