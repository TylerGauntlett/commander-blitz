"""Giada's plan: Giada before the choir, the curve-setters before a three-drop."""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.engine.enums import ActionKind, Step

DECK = "giada_font_of_hope"


def chosen_card(game):
    action = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert action.kind is ActionKind.CAST, action
    return game.state.objects[action.source].def_id


def test_giada_comes_down_before_another_angel(builder):
    # Three mana: Giada or Angel of Vitality, not both. The angel scores higher on
    # its own, but cast first it is an Angel that Giada's counters never see.
    game = (
        builder()
        .deck(0, DECK)
        .commander(0, ["giada_font_of_hope"])
        .hand(0, ["angel_of_vitality"])
        .battlefield(0, ["plains"] * 3)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    classic = HeuristicAgent(0, classic=True).act(game, 0, game.legal_actions())
    assert game.state.objects[classic.source].def_id == "angel_of_vitality"
    assert chosen_card(game) == "giada_font_of_hope"


def test_with_giada_down_an_angel_beats_a_non_angel(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["giada_font_of_hope", *["plains"] * 4])
        .hand(0, ["magus_of_the_moat", "angel_of_vitality"])
        .turn(6)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    # The bigger spell on paper is the Magus; Angel of Vitality is the one Giada
    # makes a 3/3 flier.
    classic = HeuristicAgent(0, classic=True).act(game, 0, game.legal_actions())
    assert game.state.objects[classic.source].def_id == "magus_of_the_moat"
    assert chosen_card(game) == "angel_of_vitality"


def test_an_early_cost_reducer_goes_ahead_of_a_three_drop(builder):
    game = (
        builder()
        .deck(0, DECK)
        .hand(0, ["urza_s_incubator", "angel_of_vitality"])
        .battlefield(0, ["plains"] * 3)
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    assert chosen_card(game) == "urza_s_incubator"
