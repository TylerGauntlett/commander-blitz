"""Shipped decks, piloted by their strategies, through whole games.

The unit tests pin one decision each; this is the check that the plans survive
contact with a real game -- no strategy hook raising on a card it did not
expect, no pod that stalls -- and that a seed still replays exactly.

A seeded sample of pods per run, not every deck (ADR 0024): the shelf grows by
a set at a time, and the full matrix is the arena's, which has its own runner.
The seed is the day's date unless ``DECK_GAMES_SEED`` names one, so the sample
moves across the shelf from one day to the next, and the pod's test id names
its decks, so a failing pod is rerun by its seed.

Run by the gate's `sim` group rather than with the other Python suites
(`scripts/verify.py`): whole games are simulation, and the Python job's time
budget is the tighter one.
"""

from __future__ import annotations

import datetime
import os
import random

import pytest

from commanderblitz.ai.arena import Matchup, run_game
from tests.cards.test_deck_legality import SHIPPED

#: How many four-player pods one run plays.
SAMPLE_PODS = 3

SEED = os.environ.get("DECK_GAMES_SEED") or datetime.date.today().isoformat()


def sample_pods(decks: set[str], seed: str, pods: int = SAMPLE_PODS) -> list[list[str]]:
    """``pods`` pods of four, no deck twice, drawn by ``seed``."""
    chosen = random.Random(seed).sample(sorted(decks), min(len(decks), 4 * pods))
    return [sorted(chosen[i : i + 4]) for i in range(0, len(chosen) - len(chosen) % 4, 4)]


PODS = sample_pods(SHIPPED, SEED)

pytestmark = pytest.mark.slow


def test_the_sample_is_a_function_of_the_seed():
    assert sample_pods(SHIPPED, "a") == sample_pods(SHIPPED, "a")
    seated = [deck for pod in sample_pods(SHIPPED, "a") for deck in pod]
    assert len(seated) == len(set(seated)), "no deck twice in one run"


@pytest.mark.parametrize("decks", PODS, ids=[f"{SEED}:{'+'.join(pod)}" for pod in PODS])
def test_a_pod_of_shipped_decks_plays_to_the_end(decks):
    result = run_game(Matchup(agent_names=["heuristic"], pod_size=4), seed=11, decks=decks)
    assert result.result != "unfinished"
    assert result.turns > 3, "a game that ends this early is a crash, not a win"


def test_a_seed_replays_exactly():
    """A duel rather than a pod: replay is about the strategies holding no
    hidden state, which two seats show as well as four, at a quarter the cost."""
    matchup = Matchup(agent_names=["heuristic"], pod_size=2)
    decks = ["bruvac_the_grandiloquent", "blor_the_impervious"]
    first = run_game(matchup, seed=5, decks=decks)
    again = run_game(matchup, seed=5, decks=decks)
    assert (first.winners, first.turns, first.life) == (again.winners, again.turns, again.life)
