"""Engine exception types."""

from __future__ import annotations


class AutoMtgError(Exception):
    """Base class for every error raised by this package."""


class IllegalActionError(AutoMtgError):
    """A driver submitted an action that is not in ``Game.legal_actions()``."""


class RulesLoopError(AutoMtgError):
    """The engine detected an unbounded loop (e.g. infinite trigger recursion).

    Arena runs count this as a draw rather than crashing a long simulation.
    """


class DslError(AutoMtgError):
    """A card definition references an unknown op, selector key or value form.

    Raised at *load* time, so a typo in a card JSON file fails the test suite
    instead of surfacing mid-game.
    """


class DeckError(AutoMtgError):
    """A deck list violates Commander construction rules."""
