"""One module per shipped deck, each exporting ``STRATEGY``.

Discovered rather than listed, so adding a deck is adding a file: the module
name is not significant, ``STRATEGY.plan.deck_id`` is.
"""

from __future__ import annotations

import importlib
import pkgutil

from ..base import Strategy


def _discover() -> dict[str, Strategy]:
    found: dict[str, Strategy] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{__name__}.{info.name}")
        strategy = getattr(module, "STRATEGY", None)
        if not isinstance(strategy, Strategy):
            raise TypeError(f"{module.__name__} must export STRATEGY, a Strategy")
        deck_id = strategy.plan.deck_id
        if deck_id in found:
            raise ValueError(f"two strategies claim deck {deck_id!r}")
        found[deck_id] = strategy
    return found


STRATEGIES: dict[str, Strategy] = _discover()
