"""Every shipped deck, piloted by its own strategy, through whole games.

The unit tests pin one decision each; this is the check that the twelve plans
survive contact with a real game -- no strategy hook raising on a card it did
not expect, no pod that stalls -- and that a seed still replays exactly.

Run by the gate's `sim` group rather than with the other Python suites
(`scripts/verify.py`): whole games are simulation, and the Python job's time
budget is the tighter one.
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.arena import Matchup, run_game
from tests.cards.test_deck_legality import PRECONS

#: Three four-player pods, every precon seated once.
PODS = [sorted(PRECONS)[i : i + 4] for i in range(0, len(PRECONS), 4)]

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("decks", PODS, ids=[f"pod{i}" for i in range(len(PODS))])
def test_a_pod_of_precons_plays_to_the_end(decks):
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
