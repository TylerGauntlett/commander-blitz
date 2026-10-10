"""Headless duels: run many games between agents and report what happened.

Everything here is deterministic given a seed, so an arena run is reproducible
and can be used as a regression gate rather than just a vibe check.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from commanderblitz.cards.registry import GameData, default_registry
from commanderblitz.engine.errors import RulesLoopError
from commanderblitz.engine.game import create_game
from commanderblitz.engine.sba import declare_draw

from .agents.base import Agent, agent_by_name
from .stats import GameResult, Summary, render_markdown, summarize, write_jsonl

#: Deck pairing used for a pod of any size: the two decks, mirrored.
DEFAULT_DECKS = ("aesi", "edgar")


def decks_for(pod_size: int, decks: Sequence[str] = DEFAULT_DECKS) -> list[str]:
    """Seat assignment for a pod.

    A 4-player pod mirrors the two decks (seats 0 and 2 play one, 1 and 3 the
    other) so pod-size statistics stay comparable to the duel numbers.
    """
    return [decks[i % len(decks)] for i in range(pod_size)]


@dataclass
class Matchup:
    """One agent configuration to evaluate."""

    agent_names: list[str]
    pod_size: int
    #: Checkpoint handed to any "policy" seat; without one it plays the heuristic.
    checkpoint: str | None = None

    def build(self, seed: int) -> dict[int, Agent]:
        agents: dict[int, Agent] = {}
        for pid in range(self.pod_size):
            name = self.agent_names[pid % len(self.agent_names)]
            extra = {"checkpoint": self.checkpoint} if name == "policy" else {}
            agents[pid] = agent_by_name(name, seed=seed * 97 + pid, **extra)
        return agents


def run_game(
    matchup: Matchup,
    seed: int,
    *,
    data: GameData | None = None,
    decks: Sequence[str] = DEFAULT_DECKS,
    max_steps: int = 40_000,
) -> GameResult:
    """Play one game and record what happened."""
    deck_ids = decks_for(matchup.pod_size, decks)
    game = create_game(deck_ids, data=data, seed=seed)
    agents = matchup.build(seed)

    for _ in range(max_steps):
        if game.over:
            break
        decision = game.pending()
        if decision is None:
            break
        actions = game.legal_actions()
        if not actions:
            break
        try:
            game.apply(agents[decision.player].act(game, decision.player, actions))
        except RulesLoopError:
            # A detected loop is scored as a draw so one pathological board cannot
            # abort a 10,000-game run.
            declare_draw(game.state, "rules loop")
            break
    else:  # pragma: no cover - the step cap should never be the reason a game ends
        declare_draw(game.state, "step cap")

    return GameResult(
        seed=seed,
        pod_size=matchup.pod_size,
        deck_ids=deck_ids,
        agents=[matchup.agent_names[pid % len(matchup.agent_names)] for pid in range(matchup.pod_size)],
        winners=list(game.winners),
        turns=game.state.turn,
        result=game.state.result or "unfinished",
        life=[p.life for p in game.state.players],
    )


def run_matchup(
    agent_names: Sequence[str],
    pod_size: int,
    games: int,
    *,
    seed: int = 0,
    data: GameData | None = None,
    decks: Sequence[str] = DEFAULT_DECKS,
    swap_seats: bool = True,
    checkpoint: str | None = None,
    workers: int = 1,
) -> list[GameResult]:
    """Run ``games`` games, alternating seats so seat order cannot flatter an agent.

    ``workers`` > 1 plays them across that many processes. Every game is
    already seeded on its own (``seed + i``), so the results are the same
    list in the same order either way; only the wall clock changes.
    """
    names = list(agent_names)
    games_to_play: list[tuple[Matchup, int, Sequence[str]]] = []
    for i in range(games):
        rotation = names[i % len(names) :] + names[: i % len(names)] if swap_seats else names
        matchup = Matchup(agent_names=rotation, pod_size=pod_size, checkpoint=checkpoint)
        games_to_play.append((matchup, seed + i, _deck_window(decks, pod_size, i)))

    if workers > 1:
        # Each worker loads the registry once for itself: shipping a GameData
        # to it with every game would cost more than the game.
        if data is not None and data is not default_registry():
            raise ValueError("workers > 1 plays on the default registry only")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(_play, games_to_play))

    game_data = data if data is not None else default_registry()
    return [run_game(m, s, data=game_data, decks=d) for m, s, d in games_to_play]


def _play(game: tuple[Matchup, int, Sequence[str]]) -> GameResult:
    """One game in a worker process, on that process's cached registry."""
    matchup, seed, decks = game
    return run_game(matchup, seed, data=default_registry(), decks=decks)


def _deck_window(decks: Sequence[str], pod_size: int, game: int) -> Sequence[str]:
    """The decks seated in game ``game``.

    More decks than seats -- a benchmark over every precon -- slides the window
    along by a pod each game, so every deck plays. Otherwise the list is used
    as given, which keeps the default two-deck mirror exactly as it was.
    """
    if len(decks) <= pod_size:
        return decks
    start = (game * pod_size) % len(decks)
    return [decks[(start + k) % len(decks)] for k in range(pod_size)]


def run_arena(
    agent_names: Sequence[str] = ("heuristic", "random"),
    pod_sizes: Sequence[int] = (2, 4),
    games: int = 100,
    *,
    seed: int = 0,
    out_dir: Path | None = None,
    decks: Sequence[str] = DEFAULT_DECKS,
    checkpoint: str | None = None,
    workers: int = 1,
) -> dict[int, Summary]:
    """Run the full matrix and, if ``out_dir`` is given, write the reports."""
    data = default_registry()
    results: list[GameResult] = []
    for pod_size in pod_sizes:
        results.extend(
            run_matchup(
                agent_names,
                pod_size,
                games,
                seed=seed,
                data=data,
                decks=decks,
                checkpoint=checkpoint,
                workers=workers,
            )
        )

    summaries = summarize(results)
    if out_dir is not None:
        out_dir = Path(out_dir)
        write_jsonl(results, out_dir / "stats.jsonl")
        (out_dir / "arena.md").write_text(render_markdown(summaries), encoding="utf-8")
    return summaries
