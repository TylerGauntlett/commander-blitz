"""The agent protocol.

An agent answers one decision at a time.  It receives the ``Game`` and the list
of legal actions and returns one of them -- the same interface a human driver
uses over HTTP, so agents and humans are interchangeable in every seat.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from commanderblitz.engine.actions import Action

from .heuristic_agent import HeuristicAgent
from .policy_agent import PolicyAgent
from .random_agent import RandomAgent

if TYPE_CHECKING:  # pragma: no cover
    from commanderblitz.engine.game import Game


class Agent(Protocol):
    """Anything that can choose an action."""

    name: str

    def act(self, game: Game, seat: int, actions: Sequence[Action]) -> Action:
        """Pick one of ``actions``.  Must return a member of the list."""
        ...


def play(game: Game, agents: dict[int, Agent], *, max_steps: int = 20_000) -> Game:
    """Drive a game to completion with one agent per seat."""
    for _ in range(max_steps):
        if game.over:
            return game
        decision = game.pending()
        if decision is None:
            return game
        actions = game.legal_actions()
        if not actions:
            return game
        agent = agents[decision.player]
        choice = agent.act(game, decision.player, actions)
        game.apply(choice)
    return game


def agent_by_name(name: str, *, seed: int = 0, **kwargs):
    """Build an agent from its short name, for CLI flags and the HTTP API.

    ``heuristic`` is deck-aware: it plays each seat with that deck's strategy.
    ``heuristic_classic`` is the agent from before strategies, and
    ``COMMANDERBLITZ_CPU=classic`` makes plain ``heuristic`` mean it too -- the
    Playwright server sets it, so seeded browser games stay the games their
    specs were written against.
    """

    if name == "random":
        return RandomAgent(seed=seed)
    if name == "heuristic":
        return HeuristicAgent(seed=seed, classic=os.environ.get("COMMANDERBLITZ_CPU") == "classic")
    if name == "heuristic_classic":
        return HeuristicAgent(seed=seed, classic=True)
    if name == "policy":
        return PolicyAgent(seed=seed, **kwargs)
    raise ValueError(
        f"unknown agent {name!r} (known: random, heuristic, heuristic_classic, policy)"
    )
