"""Masked PPO self-play.

Two choices are worth explaining:

* **The mask is applied to the logits, not to the sampling.** An action the
  engine would refuse gets probability zero and contributes nothing to the
  gradient, so the policy never has to learn legality -- only strategy.
* **Opponents come from a snapshot pool, not from the live policy.** Training
  purely against your current self collapses into a narrow strategy that beats
  only itself; mixing in older snapshots plus the heuristic and random agents
  keeps the objective honest.

A separate checkpoint is trained per pod size, because the spec is explicit that
player count changes how the game should be played.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from commanderblitz.cards.registry import default_registry

from . import encoding
from .agents.base import Agent
from .agents.heuristic_agent import HeuristicAgent
from .agents.policy_agent import PolicyAgent
from .agents.random_agent import RandomAgent
from .arena import decks_for
from .env import MtgEnv
from .model import ModelConfig, build_model, save, to_batch


@dataclass
class TrainConfig:
    pod_size: int = 2
    updates: int = 100
    steps_per_update: int = 512
    epochs: int = 4
    minibatch: int = 128
    gamma: float = 0.999  # episodes are long; future reward barely discounts
    gae_lambda: float = 0.95
    clip: float = 0.2
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    lr: float = 3e-4
    max_grad_norm: float = 0.5
    seed: int = 0
    snapshot_every: int = 25
    #: How often an opponent is drawn from each pool, rather than a snapshot.
    heuristic_share: float = 0.35
    random_share: float = 0.15
    out_dir: Path = field(default_factory=lambda: Path("runs"))


def train(config: TrainConfig) -> Path:
    # torch is optional (the `train` extra), so it loads only when used.
    import torch
    from torch import nn, optim

    torch.manual_seed(config.seed)
    rng = random.Random(config.seed)

    data = default_registry()
    vocab = encoding.CardVocabulary(data.registry)
    model_config = ModelConfig(n_cards=len(vocab))
    model = build_model(model_config)
    optimizer = optim.Adam(model.parameters(), lr=config.lr)

    out_dir = Path(config.out_dir) / f"pod{config.pod_size}"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshots: list[Path] = []
    history: list[dict] = []

    env = MtgEnv(
        decks_for(config.pod_size),
        seat=0,
        opponents=_opponents(config, rng, snapshots, vocab),
        seed=config.seed,
        data=data,
    )
    observation, _ = env.reset()
    episode_returns: list[float] = []
    running = 0.0
    started = time.time()

    for update in range(1, config.updates + 1):
        buffer = _Rollout()
        for _ in range(config.steps_per_update):
            scalar, card_ids, mask = to_batch([observation])
            with torch.no_grad():
                action, log_prob, value = model.act(scalar, card_ids, mask)
            index = int(action.item())
            next_observation, reward, terminated, truncated, _ = env.step(index)
            buffer.add(observation, index, float(log_prob.item()), float(value.item()), reward,
                       terminated or truncated)
            running += reward
            observation = next_observation
            if terminated or truncated:
                episode_returns.append(running)
                running = 0.0
                env.set_opponents(_opponents(config, rng, snapshots, vocab))
                observation, _ = env.reset()

        scalar, card_ids, mask = to_batch([observation])
        with torch.no_grad():
            _, _, last_value = model.act(scalar, card_ids, mask)
        advantages, returns = buffer.finish(float(last_value.item()), config)

        stats = _optimize(
            model, optimizer, buffer, advantages, returns, config, nn, torch
        )
        stats.update(
            {
                "update": update,
                "episodes": len(episode_returns),
                "mean_return": float(np.mean(episode_returns[-50:])) if episode_returns else 0.0,
                "elapsed": round(time.time() - started, 1),
            }
        )
        history.append(stats)
        print(
            f"update {update:4d}  loss {stats['loss']:+.4f}  "
            f"entropy {stats['entropy']:.3f}  return {stats['mean_return']:+.3f}  "
            f"episodes {stats['episodes']}"
        )

        if update % config.snapshot_every == 0 or update == config.updates:
            path = out_dir / f"snapshot_{update:04d}.pt"
            save(model, path, model_config, vocab.ids)
            snapshots.append(path)

    final = out_dir / "policy.pt"
    save(model, final, model_config, vocab.ids)
    (out_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    return final


def _opponents(
    config: TrainConfig,
    rng: random.Random,
    snapshots: Sequence[Path],
    vocab: encoding.CardVocabulary,
) -> list[Agent]:
    """Sample one opponent per other seat from the mixed pool."""
    out: list[Agent] = []
    for seat in range(1, config.pod_size):
        roll = rng.random()
        if roll < config.random_share or not snapshots:
            out.append(RandomAgent(rng.randrange(10_000)) if roll < config.random_share else HeuristicAgent(seat))
        elif roll < config.random_share + config.heuristic_share:
            out.append(HeuristicAgent(rng.randrange(10_000)))
        else:
            recent = list(snapshots)[-5:]
            out.append(
                PolicyAgent(
                    str(rng.choice(recent)),
                    seed=rng.randrange(10_000),
                    greedy=False,
                    vocab=vocab,
                )
            )
    return out


class _Rollout:
    """A flat on-policy buffer for one update."""

    def __init__(self) -> None:
        self.observations: list[dict] = []
        self.actions: list[int] = []
        self.log_probs: list[float] = []
        self.values: list[float] = []
        self.rewards: list[float] = []
        self.dones: list[bool] = []

    def add(self, observation, action, log_prob, value, reward, done) -> None:
        self.observations.append(observation)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.values.append(value)
        self.rewards.append(reward)
        self.dones.append(done)

    def __len__(self) -> int:
        return len(self.actions)

    def finish(self, last_value: float, config: TrainConfig):
        """Generalised advantage estimation."""
        size = len(self)
        advantages = np.zeros(size, dtype=np.float32)
        running = 0.0
        for t in reversed(range(size)):
            next_value = last_value if t == size - 1 else self.values[t + 1]
            next_non_terminal = 0.0 if self.dones[t] else 1.0
            delta = (
                self.rewards[t]
                + config.gamma * next_value * next_non_terminal
                - self.values[t]
            )
            running = delta + config.gamma * config.gae_lambda * next_non_terminal * running
            advantages[t] = running
        returns = advantages + np.array(self.values, dtype=np.float32)
        return advantages, returns


def _optimize(model, optimizer, buffer, advantages, returns, config, nn, torch) -> dict:
    scalar, card_ids, mask = to_batch(buffer.observations)
    actions = torch.as_tensor(buffer.actions).long()
    old_log_probs = torch.as_tensor(buffer.log_probs).float()
    advantage_tensor = torch.as_tensor(advantages).float()
    return_tensor = torch.as_tensor(returns).float()
    advantage_tensor = (advantage_tensor - advantage_tensor.mean()) / (
        advantage_tensor.std() + 1e-8
    )

    size = len(buffer)
    indices = np.arange(size)
    last: dict[str, float] = {}

    for _ in range(config.epochs):
        np.random.default_rng(config.seed).shuffle(indices)
        for start in range(0, size, config.minibatch):
            batch = indices[start : start + config.minibatch]
            log_probs, entropy, values = model.evaluate(
                scalar[batch], card_ids[batch], mask[batch], actions[batch]
            )
            ratio = (log_probs - old_log_probs[batch]).exp()
            surrogate = ratio * advantage_tensor[batch]
            clipped = (
                ratio.clamp(1 - config.clip, 1 + config.clip) * advantage_tensor[batch]
            )
            policy_loss = -torch.min(surrogate, clipped).mean()
            value_loss = nn.functional.mse_loss(values, return_tensor[batch])
            entropy_loss = -entropy.mean()
            loss = (
                policy_loss
                + config.value_coef * value_loss
                + config.entropy_coef * entropy_loss
            )

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()

            last = {
                "loss": float(loss.item()),
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.mean().item()),
            }
    return last
