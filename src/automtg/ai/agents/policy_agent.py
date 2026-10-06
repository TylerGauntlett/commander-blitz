"""An agent driven by a trained policy.

Falls back to the heuristic agent when no checkpoint is supplied, so
``agent_by_name("policy")`` always produces something that can hold a seat --
useful before the first training run has finished.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from automtg.cards.registry import default_registry
from automtg.engine.actions import Action

from .. import action_space, encoding
from ..model import load, load_vocab_ids
from .heuristic_agent import HeuristicAgent

if TYPE_CHECKING:  # pragma: no cover
    from automtg.engine.game import Game


class PolicyAgent:
    name = "policy"

    def __init__(
        self,
        checkpoint: str | None = None,
        *,
        seed: int = 0,
        greedy: bool = True,
        vocab: encoding.CardVocabulary | None = None,
    ) -> None:
        self.greedy = greedy
        self.fallback = HeuristicAgent(seed)
        self.model = None
        self.vocab = vocab
        if checkpoint:
            self.model, config = load(checkpoint)
            if self.vocab is None:
                registry = default_registry().registry
                saved = load_vocab_ids(checkpoint)
                if saved is not None:
                    # The card list this network was actually trained on. Using
                    # today's registry instead would shift every index the
                    # moment a card is added that sorts early -- and the model
                    # would load cleanly and quietly read the wrong embeddings.
                    self.vocab = encoding.CardVocabulary(registry, saved)
                else:
                    self.vocab = encoding.CardVocabulary(registry)
                    if len(self.vocab) != config.n_cards:
                        # An older checkpoint against a registry that has since
                        # grown. There is no way to recover the mapping, and
                        # guessing would be an IndexError at best. Fall back to
                        # the heuristic, which is a worse player but a correct
                        # one, and say so.
                        warnings.warn(
                            f"{checkpoint} was trained on {config.n_cards} cards but the "
                            f"registry now holds {len(self.vocab)}; falling back to the "
                            "heuristic agent. Retrain with scripts/train.py.",
                            RuntimeWarning,
                            stacklevel=2,
                        )
                        self.model = None

    def act(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        if self.model is None or self.vocab is None:
            return self.fallback.act(game, seat, actions)

        # torch is optional (the `train` extra), so it loads only when used.
        import torch

        table = action_space.build(game.state)
        if not table.by_index:
            return actions[0]

        observation = encoding.encode(game.state, seat, self.vocab)
        mask = table.mask.astype(np.float32)
        scalar = torch.as_tensor(observation["scalar"]).unsqueeze(0)
        card_ids = torch.as_tensor(observation["card_ids"]).long().unsqueeze(0)
        mask_tensor = torch.as_tensor(mask).unsqueeze(0)

        index, _, _ = self.model.act(scalar, card_ids, mask_tensor, greedy=self.greedy)
        try:
            return table.decode(int(index.item()))
        except KeyError:  # pragma: no cover - the mask should prevent this
            return actions[0]
