"""Engine exception types."""

from __future__ import annotations


class CommanderBlitzError(Exception):
    """Base class for every error raised by this package."""


class IllegalActionError(CommanderBlitzError):
    """A driver submitted an action that is not in ``Game.legal_actions()``."""


class RulesLoopError(CommanderBlitzError):
    """The engine detected an unbounded loop (e.g. infinite trigger recursion).

    Arena runs count this as a draw rather than crashing a long simulation.
    """


class DslError(CommanderBlitzError):
    """A card definition references an unknown op, selector key or value form.

    Raised at *load* time, so a typo in a card JSON file fails the test suite
    instead of surfacing mid-game.
    """


class DeckError(CommanderBlitzError):
    """A deck list violates Commander construction rules."""
