"""Zurgo Stormrender: trades accepted, tokens thrown in, only tokens fed to the outlets."""

from __future__ import annotations

from automtg.ai.agents.heuristic_agent import HeuristicAgent
from automtg.ai.strategy import DefaultStrategy
from automtg.ai.strategy.archetypes import Aristocrats
from automtg.engine.enums import ActionKind, DecisionKind
from tests.conftest import only_oid, pass_until

DECK = "zurgo"


def make_commander(game, seat: int, card_id: str) -> int:
    oid = only_oid(game, card_id, seat)
    game.state.objects[oid].is_commander = True
    game.state.players[seat].commanders.append(oid)
    return oid


def at_attacks(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    return game


def test_it_takes_an_even_trade(builder):
    game = at_attacks(
        builder().deck(0, DECK).battlefield(0, ["t_bear"]).battlefield(1, ["t_bear"]).build()
    )
    careful = HeuristicAgent(0, strategy=DefaultStrategy()).act(game, 0, game.legal_actions())
    assert careful.kind is ActionKind.FINISH_DECLARATION
    assert HeuristicAgent(0).act(game, 0, game.legal_actions()).kind is ActionKind.ADD_ATTACKER


def test_a_token_attacks_into_a_blocker_while_zurgo_is_out(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["zurgo_stormrender"], tapped=True)
        .battlefield(0, ["warrior_1_1_r"])
        .battlefield(1, ["t_big"])
        .build()
    )
    make_commander(game, 0, "zurgo_stormrender")
    at_attacks(game)
    token = only_oid(game, "warrior_1_1_r", 0)
    # A blocked token is a card off Zurgo; plain aristocrats sees a 1/1 dying.
    plain = HeuristicAgent(0, strategy=Aristocrats()).act(game, 0, game.legal_actions())
    assert plain.kind is ActionKind.FINISH_DECLARATION
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.ADD_ATTACKER
    assert chosen.source == token


def test_sacrifice_outlets_eat_tokens_not_cards(builder):
    def position(creature: str):
        return (
            builder()
            .deck(0, DECK)
            .battlefield(0, ["vampiric_rites", creature, "swamp", "swamp"])
            .build()
        )

    with_token = position("warrior_1_1_r")
    chosen = HeuristicAgent(0).act(with_token, 0, with_token.legal_actions())
    assert chosen.kind is ActionKind.ACTIVATE
    assert with_token.state.objects[chosen.source].def_id == "vampiric_rites"

    without = position("t_bear")
    plain = HeuristicAgent(0, strategy=Aristocrats()).act(without, 0, without.legal_actions())
    assert plain.kind is ActionKind.ACTIVATE, "plain aristocrats sacrifices the bear"
    chosen = HeuristicAgent(0).act(without, 0, without.legal_actions())
    assert chosen.kind is ActionKind.PASS
