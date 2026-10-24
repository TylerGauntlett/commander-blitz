"""Deck-aware CPU play: one :class:`Strategy` per deck, layered on the heuristic.

Lookup, in order:

1. the deck id -- every favorite has a module in ``decks/``;
2. the commander -- so a player's own import of Bruvac is still piloted as a
   mill deck;
3. the deck file's ``archetype`` -- how a precon without a module of its own
   is piloted (ADR 0024);
4. :class:`DefaultStrategy` -- the baseline every other deck gets.

``CLASSIC`` is the neutral base class, the agent as it was before any of this,
kept for seeded tests (``COMMANDERBLITZ_CPU=classic``) and as a benchmark opponent.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from commanderblitz.cards.registry import load_decks

from .archetypes import ARCHETYPES
from .base import Combo, DeckPlan, Strategy
from .decks import STRATEGIES
from .default import DefaultStrategy

CLASSIC = Strategy()


@lru_cache(maxsize=1)
def deck_archetypes() -> dict[str, str]:
    """``deck id -> archetype`` for every shipped deck that names one.

    Read from the authored deck files rather than passed in, because the agent
    that asks only has a game state, and a seat there knows its deck id and
    nothing of the file it came from.
    """
    return {deck.id: deck.archetype for deck in load_decks().values() if deck.archetype}


def strategy_for(deck_id: str, commanders: Iterable[str] = ()) -> Strategy:
    """The strategy that pilots this deck."""
    if deck_id in STRATEGIES:
        return STRATEGIES[deck_id]
    wanted = frozenset(commanders)
    if wanted:
        for strategy in STRATEGIES.values():
            if strategy.plan.commanders and strategy.plan.commanders == wanted:
                return strategy
    archetype = ARCHETYPES.get(deck_archetypes().get(deck_id, ""))
    if archetype is not None:
        return archetype()
    return DefaultStrategy()


__all__ = [
    "ARCHETYPES",
    "CLASSIC",
    "STRATEGIES",
    "Combo",
    "DeckPlan",
    "DefaultStrategy",
    "Strategy",
    "deck_archetypes",
    "strategy_for",
]
