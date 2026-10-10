"""A Gymnasium environment wrapping the engine.

The env owns exactly one seat.  Every other seat is driven inside ``step`` by its
own :class:`~commanderblitz.ai.agents.base.Agent` until control comes back, so from the
policy's point of view the game is a normal single-agent MDP.

The action mask lives *in the observation* rather than in ``info`` so it survives
vectorization and any wrapper that only forwards observations.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from commanderblitz.cards.registry import GameData, default_registry
from commanderblitz.engine.errors import RulesLoopError
from commanderblitz.engine.game import create_game
from commanderblitz.engine.sba import declare_draw

from . import action_space, encoding
from .agents.base import Agent, agent_by_name
from .agents.random_agent import RandomAgent

#: Per-step shaping coefficient, used only when ``reward_shaping`` is on.
SHAPING_SCALE = 0.001


class MtgEnv(gym.Env):
    """One seat at a Commander table."""

    metadata = {"render_modes": ["ansi"]}

    def __init__(
        self,
        deck_ids: Sequence[str] = ("aesi", "edgar"),
        *,
        seat: int = 0,
        opponents: Sequence[Agent] | None = None,
        seed: int | None = None,
        max_turns: int | None = None,
        reward_shaping: bool = False,
        data: GameData | None = None,
        strict: bool = False,
    ) -> None:
        super().__init__()
        self.deck_ids = list(deck_ids)
        self.seat = seat
        self.max_turns = max_turns
        self.reward_shaping = reward_shaping
        self.strict = strict
        self.data = data if data is not None else default_registry()
        self.vocab = encoding.CardVocabulary(self.data.registry)

        self._seed = 0 if seed is None else int(seed)
        self._episode = 0
        self.game = None
        self.table: action_space.ActionTable | None = None

        self.opponents: dict[int, Agent] = {}
        self.set_opponents(opponents)

        self.observation_space = spaces.Dict(
            {
                "scalar": spaces.Box(-1.0, 1.0, (encoding.OBS_DIM,), dtype=np.float32),
                "card_ids": spaces.Box(
                    0, len(self.vocab), (encoding.CARD_SLOTS,), dtype=np.int32
                ),
                "action_mask": spaces.MultiBinary(action_space.ACTION_SPACE_SIZE),
            }
        )
        self.action_space = spaces.Discrete(action_space.ACTION_SPACE_SIZE)

    # ------------------------------------------------------------------

    @property
    def num_players(self) -> int:
        return len(self.deck_ids)

    def set_opponents(self, agents: Sequence[Agent] | None) -> None:
        """Seat one agent per non-controlled seat, in seat order.

        Self-play resamples opponents between episodes, so this takes the flat
        list a sampler produces and keys it by seat id.
        """
        others = list(agents) if agents else []
        self.opponents = {}
        index = 0
        for pid in range(self.num_players):
            if pid == self.seat:
                continue
            self.opponents[pid] = (
                others[index] if index < len(others) else RandomAgent(self._seed + pid)
            )
            index += 1

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        if seed is not None:
            self._seed = int(seed)
        game_seed = self._seed + self._episode
        self._episode += 1

        self.game = create_game(
            self.deck_ids, data=self.data, seed=game_seed, max_turns=self.max_turns
        )
        self._prev_margin = self._margin()
        self._advance_others()
        return self._observe(), {"seed": game_seed}

    def step(self, action: int):
        assert self.game is not None, "call reset() before step()"
        info: dict[str, Any] = {}

        if not self.game.over and self._is_our_turn():
            table = self.table or action_space.build(self.game.state)
            try:
                chosen = table.decode(int(action))
            except KeyError:
                # An illegal index means the policy ignored the mask.  Fall back to
                # the first legal action rather than corrupting the episode.
                if self.strict:
                    raise
                legal = table.legal_indices
                info["illegal_action"] = int(action)
                chosen = table.decode(legal[0])
            try:
                self.game.apply(chosen)
            except RulesLoopError as exc:
                info["rules_loop"] = str(exc)

                declare_draw(self.game.state, "rules loop")
            self._advance_others()

        reward, terminated = self._reward()
        truncated = False
        if self.game.over and self.game.state.result == "draw":
            info["draw"] = True
        info["turns"] = self.game.state.turn
        info["winners"] = list(self.game.winners)
        return self._observe(), reward, terminated, truncated, info

    def render(self):  # pragma: no cover - debug helper
        return self.game.state.describe() if self.game else ""

    # ------------------------------------------------------------------

    def _is_our_turn(self) -> bool:
        decision = self.game.pending()
        return decision is not None and decision.player == self.seat

    def _advance_others(self) -> None:
        """Let the other seats act until it is our turn or the game ends."""
        guard = 0
        while not self.game.over:
            decision = self.game.pending()
            if decision is None or decision.player == self.seat:
                break
            actions = self.game.legal_actions()
            if not actions:
                break
            agent = self.opponents[decision.player]
            try:
                self.game.apply(agent.act(self.game, decision.player, actions))
            except RulesLoopError:
                declare_draw(self.game.state, "rules loop")
                break
            guard += 1
            if guard > 50_000:  # pragma: no cover - safety valve

                declare_draw(self.game.state, "opponent loop")
                break
        self.table = (
            action_space.build(self.game.state)
            if not self.game.over and self._is_our_turn()
            else None
        )

    def _observe(self) -> dict[str, np.ndarray]:
        state = self.game.state
        obs = encoding.encode(state, self.seat, self.vocab)
        table = self.table
        mask = table.mask if table is not None else np.zeros(
            action_space.ACTION_SPACE_SIZE, dtype=np.int8
        )
        if not mask.any():
            # A terminal (or opponent-controlled) state still needs a valid mask,
            # otherwise a sampler downstream has nothing to choose from.
            mask = mask.copy()
            mask[action_space.IDX_PASS] = 1
        obs["action_mask"] = mask.astype(np.int8)
        return obs

    def _margin(self) -> float:
        state = self.game.state
        opponents = [p for p in state.players if p.pid != self.seat and not p.has_lost]
        if not opponents:
            return 0.0
        mean_opponent = sum(p.life for p in opponents) / len(opponents)
        return state.players[self.seat].life - mean_opponent

    def _reward(self) -> tuple[float, bool]:
        game = self.game
        if not game.over:
            if not self.reward_shaping:
                return 0.0, False
            margin = self._margin()
            delta = margin - self._prev_margin
            self._prev_margin = margin
            return SHAPING_SCALE * delta, False

        winners = game.winners
        if not winners:
            return 0.0, True
        if self.seat in winners:
            return 1.0, True
        # Split the loss across the losing seats so a pod's rewards sum to zero.
        losers = max(1, self.num_players - len(winners))
        return -1.0 / losers, True


def make_env(
    deck_ids: Sequence[str] = ("aesi", "edgar"),
    *,
    seat: int = 0,
    opponent: str = "random",
    seed: int = 0,
    **kwargs,
) -> MtgEnv:
    """Convenience constructor used by the trainer and the tests."""

    opponents = [
        agent_by_name(opponent, seed=seed + pid)
        for pid in range(len(deck_ids))
        if pid != seat
    ]
    return MtgEnv(deck_ids, seat=seat, opponents=opponents, seed=seed, **kwargs)
