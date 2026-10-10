"""The Ur-Dragon's plan: rocks and dorks are ramp, and fast mana is a keep."""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.ai.strategy import DefaultStrategy, strategy_for
from commanderblitz.engine.enums import ActionKind, Step

DECK = "the_ur_dragon"


def test_an_early_rock_goes_ahead_of_a_three_drop(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["plateau", "savannah", "taiga"])
        .hand(0, ["arcane_signet", "sylvia_brightspear"])
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    classic = HeuristicAgent(0, classic=True).act(game, 0, game.legal_actions())
    assert game.state.objects[classic.source].def_id == "sylvia_brightspear"
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.CAST
    assert game.state.objects[chosen.source].def_id == "arcane_signet"


def test_late_in_the_game_a_dragon_beats_a_rock(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["plateau", "taiga", "badlands", "volcanic_island", "mountain"])
        .hand(0, ["arcane_signet", "scourge_of_valkas"])
        .turn(10)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert game.state.objects[chosen.source].def_id == "scourge_of_valkas"


def test_one_land_and_fast_mana_is_a_keep(builder):
    hand = [
        "command_tower",
        "sol_ring",
        "birds_of_paradise",
        "goldspan_dragon",
        "terror_of_the_peaks",
        "lathliss_dragon_queen",
        "demonic_tutor",
    ]
    game = builder().deck(0, DECK).hand(0, hand).build(advance=False)
    assert DefaultStrategy().keep_hand(game.state, 0) is False
    assert strategy_for(DECK).keep_hand(game.state, 0) is True
