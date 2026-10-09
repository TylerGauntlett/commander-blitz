"""Isperia, Supreme Judge: cheap counters, one-sided wraths, attacks forced on their turn."""

from __future__ import annotations

from automtg.ai.agents.heuristic_agent import HeuristicAgent
from automtg.ai.strategy import DefaultStrategy
from automtg.ai.strategy.archetypes import Control
from automtg.engine.enums import ActionKind, Step
from tests.conftest import action_for_card, only_oid, pass_until

DECK = "isperia"


def make_commander(game, seat: int, card_id: str) -> int:
    oid = only_oid(game, card_id, seat)
    game.state.objects[oid].is_commander = True
    game.state.players[seat].commanders.append(oid)
    return oid


def test_it_counters_a_two_drop(builder):
    game = (
        builder()
        .deck(0, DECK)
        .hand(0, ["counterspell"])
        .battlefield(0, ["island", "island"])
        .hand(1, ["grizzly_bears"])
        .battlefield(1, ["forest", "forest"])
        .active(1)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, "grizzly_bears"))
    pass_until(game, lambda g: g.pending() and g.pending().player == 0)
    careful = HeuristicAgent(0, strategy=DefaultStrategy()).act(game, 0, game.legal_actions())
    assert careful.kind is ActionKind.PASS, "the baseline saves counters for three-drops"
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.CAST
    assert game.state.objects[chosen.source].def_id == "counterspell"


def test_a_wrath_waits_until_it_is_one_sided(builder):
    def position(theirs: list[str]):
        return (
            builder()
            .deck(0, DECK)
            .hand(0, ["wrath_of_god"])
            .battlefield(0, ["wind_drake", "serra_angel"] + ["plains"] * 4)
            .battlefield(1, theirs)
            .build()
        )

    ahead = position(["t_bear"])
    plain = HeuristicAgent(0, strategy=Control()).act(ahead, 0, ahead.legal_actions())
    assert plain.kind is ActionKind.CAST, "plain control wipes its own fliers to kill a bear"
    chosen = HeuristicAgent(0).act(ahead, 0, ahead.legal_actions())
    assert chosen.kind is ActionKind.PASS

    behind = position(["t_big", "t_big", "t_big"])
    chosen = HeuristicAgent(0).act(behind, 0, behind.legal_actions())
    assert chosen.kind is ActionKind.CAST
    assert behind.state.objects[chosen.source].def_id == "wrath_of_god"


def test_bident_forces_attacks_on_their_turn_not_ours(builder):
    def position(active: int, step: Step):
        game = (
            builder()
            .deck(0, DECK)
            .battlefield(0, ["isperia_supreme_judge", "bident_of_thassa", "island", "island"])
            .battlefield(1, ["t_bear"])
            .active(active)
            .step(step)
            .build()
        )
        make_commander(game, 0, "isperia_supreme_judge")
        return game

    ours = position(0, Step.PRECOMBAT_MAIN)
    plain = HeuristicAgent(0, strategy=Control()).act(ours, 0, ours.legal_actions())
    assert plain.kind is ActionKind.ACTIVATE, "plain control forces attacks on its own turn"
    assert HeuristicAgent(0).act(ours, 0, ours.legal_actions()).kind is ActionKind.PASS

    # Their upkeep: the bear has to attack, and Isperia draws when it does.
    theirs = position(1, Step.UPKEEP)
    assert theirs.pending().player == 0
    chosen = HeuristicAgent(0).act(theirs, 0, theirs.legal_actions())
    assert chosen.kind is ActionKind.ACTIVATE
    assert theirs.state.objects[chosen.source].def_id == "bident_of_thassa"
