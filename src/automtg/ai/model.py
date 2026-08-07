"""The policy network.

Small on purpose. The interesting part is the card embedding: the observation
carries a card id per hand, battlefield and stack slot, so the model can learn
"Legion Lieutenant is worth protecting" rather than only "a 2/2 is on the board".
With a couple of hundred distinct cards that table is cheap and it is where most
of the model's usable signal comes from.

``torch`` is imported lazily so the engine, server and arena all run without it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .action_space import ACTION_SPACE_SIZE
from .encoding import BF_CAP, CARD_SLOTS, HAND_CAP, OBS_DIM

#: Width of the per-card embedding.
EMBED_DIM = 32
HIDDEN = (1024, 512)


@dataclass
class ModelConfig:
    n_cards: int
    obs_dim: int = OBS_DIM
    card_slots: int = CARD_SLOTS
    embed_dim: int = EMBED_DIM
    action_dim: int = ACTION_SPACE_SIZE
    hidden: tuple[int, ...] = HIDDEN


def build_model(config: ModelConfig):
    """Construct the actor-critic network.  Requires the ``train`` extra."""
    import torch
    from torch import nn

    class ActorCritic(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.config = config
            self.embed = nn.Embedding(config.n_cards, config.embed_dim, padding_idx=0)
            # Hand, battlefield and stack are pooled separately: "what is in my
            # hand" and "what is on the board" are different questions, and a
            # single pool over all slots would blur them together.
            pooled = config.embed_dim * 3
            layers: list[nn.Module] = []
            width = config.obs_dim + pooled
            for size in config.hidden:
                layers += [nn.Linear(width, size), nn.ReLU()]
                width = size
            self.trunk = nn.Sequential(*layers)
            self.policy = nn.Linear(width, config.action_dim)
            self.value = nn.Linear(width, 1)

        def features(self, scalar, card_ids):
            embedded = self.embed(card_ids)
            hand = embedded[:, :HAND_CAP].mean(dim=1)
            battlefield = embedded[:, HAND_CAP : HAND_CAP + BF_CAP].mean(dim=1)
            stack = embedded[:, HAND_CAP + BF_CAP :].mean(dim=1)
            joined = torch.cat([scalar, hand, battlefield, stack], dim=-1)
            return self.trunk(joined)

        def forward(self, scalar, card_ids, mask):
            hidden = self.features(scalar, card_ids)
            logits = self.policy(hidden)
            # Masking with -inf is what makes the policy incapable of proposing
            # an illegal action, rather than merely unlikely to.
            logits = logits.masked_fill(mask <= 0, float("-inf"))
            return logits, self.value(hidden).squeeze(-1)

        @torch.no_grad()
        def act(self, scalar, card_ids, mask, *, greedy: bool = False):
            logits, value = self.forward(scalar, card_ids, mask)
            distribution = torch.distributions.Categorical(logits=logits)
            action = logits.argmax(dim=-1) if greedy else distribution.sample()
            return action, distribution.log_prob(action), value

        def evaluate(self, scalar, card_ids, mask, actions):
            logits, value = self.forward(scalar, card_ids, mask)
            distribution = torch.distributions.Categorical(logits=logits)
            return distribution.log_prob(actions), distribution.entropy(), value

    return ActorCritic()


def to_batch(observations: list[dict[str, np.ndarray]]):
    """Stack a list of observations into tensors."""
    import torch

    scalar = torch.as_tensor(np.stack([o["scalar"] for o in observations]))
    card_ids = torch.as_tensor(np.stack([o["card_ids"] for o in observations])).long()
    mask = torch.as_tensor(np.stack([o["action_mask"] for o in observations])).float()
    return scalar, card_ids, mask


def save(model, path, config: ModelConfig) -> None:
    import torch

    torch.save({"state_dict": model.state_dict(), "config": config.__dict__}, path)


def load(path):
    """Load a checkpoint, rebuilding the network from the config it was saved with."""
    import torch

    blob = torch.load(path, map_location="cpu", weights_only=False)
    config = ModelConfig(**blob["config"])
    model = build_model(config)
    model.load_state_dict(blob["state_dict"])
    model.eval()
    return model, config
