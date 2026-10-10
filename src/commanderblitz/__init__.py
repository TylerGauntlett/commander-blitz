"""Commander Blitz - a Magic: The Gathering Commander board state engine.

Layers:
    automtg.engine   pure deterministic rules engine (no I/O, no ML, no HTTP)
    automtg.cards    JSON card definition loading and validation
    automtg.ai       Gymnasium environment, agents, self-play trainer
    automtg.server   FastAPI application exposing the engine over HTTP
"""

__version__ = "0.1.0"
