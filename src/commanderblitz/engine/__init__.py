"""The rules engine.

The engine is a pure, deterministic state machine that advances until it needs a
decision from a player.  Every driver -- HTTP, the RL environment, the CLI --
answers those decisions through the same :class:`commanderblitz.engine.game.Game` facade,
so there is exactly one code path for "a player did something".
"""
