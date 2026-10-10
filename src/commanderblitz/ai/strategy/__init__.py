"""Deck-aware CPU play: one :class:`Strategy` per deck, layered on the heuristic.

Lookup, in order:

1. the deck id -- every shipped precon has a module in ``decks/``;
2. the commander -- so a player's own import of Bruvac is still piloted as a
   mill deck;
3. :class:`DefaultStrategy` -- the baseline every other deck gets.

``CLASSIC`` is the neutral base class, the agent as it was before any of this,
kept for seeded tests (``AUTOMTG_CPU=classic``) and as a benchmark opponent.
"""

from __future__ import annotations

from collections.abc import Iterable

from .base import Combo, DeckPlan, Strategy
from .decks import STRATEGIES
from .default import DefaultStrategy

CLASSIC = Strategy()


def strategy_for(deck_id: str, commanders: Iterable[str] = ()) -> Strategy:
    """The strategy that pilots this deck."""
    if deck_id in STRATEGIES:
        return STRATEGIES[deck_id]
    wanted = frozenset(commanders)
    if wanted:
        for strategy in STRATEGIES.values():
            if strategy.plan.commanders and strategy.plan.commanders == wanted:
                return strategy
    return DefaultStrategy()


__all__ = [
    "CLASSIC",
    "STRATEGIES",
    "Combo",
    "DeckPlan",
    "DefaultStrategy",
    "Strategy",
    "strategy_for",
]
