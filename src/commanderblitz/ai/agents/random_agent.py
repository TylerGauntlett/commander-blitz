"""A uniformly random legal player -- the floor every other agent must beat."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from automtg.engine.actions import Action
from automtg.engine.rng import Rng

if TYPE_CHECKING:  # pragma: no cover
    from automtg.engine.game import Game


class RandomAgent:
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self.rng = Rng(seed)

    def act(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        return self.rng.choice(actions)
