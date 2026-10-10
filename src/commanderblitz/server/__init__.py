"""The HTTP layer.

A thin driver over the engine.  It holds no rules logic: it creates games, serves
the legal-action list, applies the action a client echoes back, and drives the AI
seats until a human has to decide again.
"""

from .app import create_app

__all__ = ["create_app"]
