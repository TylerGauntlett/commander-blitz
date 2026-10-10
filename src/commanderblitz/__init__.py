"""Commander Blitz - a Magic: The Gathering Commander board state engine.

Layers:
    commanderblitz.engine   pure deterministic rules engine (no I/O, no ML, no HTTP)
    commanderblitz.cards    JSON card definition loading and validation
    commanderblitz.ai       Gymnasium environment, agents, self-play trainer
    commanderblitz.server   FastAPI application exposing the engine over HTTP
"""

__version__ = "1.0.0"
