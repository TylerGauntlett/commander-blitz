"""The single source of randomness in the engine.

Every shuffle, coin flip and random choice routes through :class:`Rng`.  Nothing
else in ``automtg`` may call :mod:`random` or ``numpy.random`` directly -- a test
in ``tests/unit/test_determinism_hygiene.py`` enforces this by scanning the
source.  Determinism is what makes golden replays, undo-by-replay and
reproducible training runs possible.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any, TypeVar

T = TypeVar("T")


class Rng:
    """A seeded random source with an explicit, serializable state."""

    __slots__ = ("_r", "seed")

    def __init__(self, seed: int | None = None) -> None:
        self.seed = 0 if seed is None else int(seed)
        self._r = random.Random(self.seed)

    def shuffle(self, seq: list[Any]) -> None:
        """Shuffle ``seq`` in place."""
        self._r.shuffle(seq)

    def shuffled(self, seq: Sequence[T]) -> list[T]:
        out = list(seq)
        self._r.shuffle(out)
        return out

    def choice(self, seq: Sequence[T]) -> T:
        return seq[self._r.randrange(len(seq))]

    def randint(self, a: int, b: int) -> int:
        """Inclusive on both ends, matching ``random.randint``."""
        return self._r.randint(a, b)

    def random(self) -> float:
        return self._r.random()

    # -- state management, used by replay and by cloning tests ---------------

    def getstate(self) -> tuple:
        return self._r.getstate()

    def setstate(self, state: tuple) -> None:
        self._r.setstate(state)

    def spawn(self, salt: int) -> Rng:
        """Derive an independent stream (used to give each seat its own agent RNG)."""
        return Rng(self.seed * 1_000_003 + salt)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Rng(seed={self.seed})"
