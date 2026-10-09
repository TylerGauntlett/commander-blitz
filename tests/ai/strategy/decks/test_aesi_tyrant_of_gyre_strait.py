"""Aesi's plan: payoffs before the land drop, big land hands kept, overruns saved."""

from __future__ import annotations

from automtg.ai.agents.heuristic_agent import HeuristicAgent
from automtg.ai.strategy import strategy_for
from automtg.engine.enums import ActionKind, Step

DECK = "aesi_tyrant_of_gyre_strait"
LANDS = ["forest", "forest", "forest", "island", "island"]


def test_a_landfall_payoff_is_cast_before_the_land_it_would_see(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, LANDS)
        .hand(0, ["tatyova_benthic_druid", "forest"])
        .turn(5)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    classic = HeuristicAgent(0, classic=True).act(game, 0, game.legal_actions())
    assert classic.kind is ActionKind.PLAY_LAND, "the old agent played the land first"
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.CAST
    assert game.state.objects[chosen.source].def_id == "tatyova_benthic_druid"


def test_the_land_still_goes_down_when_no_payoff_is_affordable(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, LANDS[:2])
        .hand(0, ["tatyova_benthic_druid", "forest"])
        .turn(2)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    assert HeuristicAgent(0).act(game, 0, game.legal_actions()).kind is ActionKind.PLAY_LAND


def test_six_lands_and_an_exploration_is_a_keep(builder):
    hand = ["forest", "forest", "forest", "island", "island", "island", "exploration"]
    game = builder().deck(0, DECK).hand(0, hand).build(advance=False)
    assert strategy_for(DECK).keep_hand(game.state, 0) is True


def test_overwhelming_stampede_waits_for_a_board(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, [*LANDS, "t_bear"])
        .hand(0, ["overwhelming_stampede"])
        .turn(6)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    # One bear is not an overrun. The classic agent fired it anyway.
    assert game.state.step is Step.PRECOMBAT_MAIN
    classic = HeuristicAgent(0, classic=True).act(game, 0, game.legal_actions())
    assert classic.kind is ActionKind.CAST
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.PASS
