"""Aggregating arena results.

Results are segmented by **pod size** because the spec is explicit that player
count changes how the game should be played: a duel rewards emptying your hand
early, a four-player pod rewards not being the biggest threat on the table.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GameResult:
    """One completed game."""

    seed: int
    pod_size: int
    deck_ids: list[str]
    agents: list[str]
    winners: list[int]
    turns: int
    result: str
    life: list[int] = field(default_factory=list)
    cards_cast: Counter = field(default_factory=Counter)

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "pod_size": self.pod_size,
            "deck_ids": self.deck_ids,
            "agents": self.agents,
            "winners": self.winners,
            "turns": self.turns,
            "result": self.result,
            "life": self.life,
        }


def wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a win rate.

    Wilson rather than normal approximation: arena runs are often small enough
    that the normal interval would run past 0 or 1 and mislead.
    """
    if total == 0:
        return (0.0, 0.0)
    p = wins / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


@dataclass
class Summary:
    pod_size: int
    games: int = 0
    draws: int = 0
    wins_by_seat: Counter = field(default_factory=Counter)
    wins_by_agent: Counter = field(default_factory=Counter)
    wins_by_deck: Counter = field(default_factory=Counter)
    games_by_agent: Counter = field(default_factory=Counter)
    games_by_deck: Counter = field(default_factory=Counter)
    turns: list[int] = field(default_factory=list)

    @property
    def draw_rate(self) -> float:
        return self.draws / self.games if self.games else 0.0

    @property
    def median_turns(self) -> int:
        if not self.turns:
            return 0
        ordered = sorted(self.turns)
        return ordered[len(ordered) // 2]

    def win_rate(self, agent: str) -> float:
        played = self.games_by_agent[agent]
        return self.wins_by_agent[agent] / played if played else 0.0

    def interval(self, agent: str) -> tuple[float, float]:
        return wilson_interval(self.wins_by_agent[agent], self.games_by_agent[agent])


def summarize(results: Iterable[GameResult]) -> dict[int, Summary]:
    """Group results by pod size."""
    out: dict[int, Summary] = {}
    for result in results:
        summary = out.setdefault(result.pod_size, Summary(pod_size=result.pod_size))
        summary.games += 1
        summary.turns.append(result.turns)
        if not result.winners:
            summary.draws += 1
        for agent in result.agents:
            summary.games_by_agent[agent] += 1
        for deck in result.deck_ids:
            summary.games_by_deck[deck] += 1
        for winner in result.winners:
            summary.wins_by_seat[winner] += 1
            if winner < len(result.agents):
                summary.wins_by_agent[result.agents[winner]] += 1
            if winner < len(result.deck_ids):
                summary.wins_by_deck[result.deck_ids[winner]] += 1
    return out


def write_jsonl(results: Iterable[GameResult], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_dict()) + "\n")
    return path


def render_markdown(summaries: dict[int, Summary]) -> str:
    """A human-readable report, segmented by pod size."""
    lines = ["# Arena results", ""]
    for pod_size in sorted(summaries):
        summary = summaries[pod_size]
        lines.append(f"## {pod_size}-player pods")
        lines.append("")
        lines.append(f"- games: **{summary.games}**")
        lines.append(f"- draws: **{summary.draws}** ({summary.draw_rate:.1%})")
        lines.append(f"- median turns: **{summary.median_turns}**")
        lines.append("")
        lines.append("| agent | games | wins | win rate | 95% CI |")
        lines.append("|---|---|---|---|---|")
        for agent in sorted(summary.games_by_agent):
            low, high = summary.interval(agent)
            lines.append(
                f"| {agent} | {summary.games_by_agent[agent]} | "
                f"{summary.wins_by_agent[agent]} | {summary.win_rate(agent):.1%} | "
                f"{low:.1%}-{high:.1%} |"
            )
        lines.append("")
        lines.append("| deck | games | wins | win rate |")
        lines.append("|---|---|---|---|")
        for deck in sorted(summary.games_by_deck):
            played = summary.games_by_deck[deck]
            won = summary.wins_by_deck[deck]
            lines.append(f"| {deck} | {played} | {won} | {won / played:.1%} |")
        lines.append("")
        lines.append("| seat | wins |")
        lines.append("|---|---|")
        for seat in range(pod_size):
            lines.append(f"| {seat} | {summary.wins_by_seat[seat]} |")
        lines.append("")
    return "\n".join(lines)
