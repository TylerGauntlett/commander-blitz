"""Edgar Markov: Vampires first, the Conqueror loop on sight, tokens into the grinder."""

from __future__ import annotations

from automtg.ai.agents.heuristic_agent import HeuristicAgent
from automtg.ai.strategy.decks.edgar_markov import STRATEGY
from tests.conftest import only_oid

DECK = "edgar_markov"


def chosen_card(game) -> str:
    action = HeuristicAgent(0).act(game, 0, game.legal_actions())
    return game.state.objects[action.source].def_id


def test_a_vampire_one_drop_beats_a_zombie_one_drop(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["swamp"])
        .hand(0, ["carrion_feeder", "vampire_of_the_dire_moon"])
        .build()
    )
    assert chosen_card(game) == "vampire_of_the_dire_moon"


def test_vito_completes_the_loop_ahead_of_a_bigger_creature(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["bloodthirsty_conqueror"])
        .battlefield(0, ["swamp"] * 5)
        .hand(0, ["anowon_the_ruin_sage", "vito_thorn_of_the_dusk_rose"])
        .build()
    )
    assert chosen_card(game) == "vito_thorn_of_the_dusk_rose"


def test_olivia_s_wrath_waits_for_a_one_sided_board(builder):
    def position(their_board):
        return (
            builder()
            .deck(0, DECK)
            .battlefield(0, ["swamp"] * 5 + ["vampire_of_the_dire_moon", "grizzly_bears"])
            .battlefield(1, their_board)
            .hand(0, ["olivia_s_wrath"])
            .build()
        )

    even = position(["grizzly_bears", "grizzly_bears"])
    assert HeuristicAgent(0).act(even, 0, even.legal_actions()).source is None
    lopsided = position(["grizzly_bears"] * 5)
    assert chosen_card(lopsided) == "olivia_s_wrath"


def test_tokens_are_sacrificed_before_real_cards_and_outsiders_first(builder):
    game = builder().battlefield(0, ["vampire_of_the_dire_moon", "grizzly_bears", "blood_artist"]).build()
    vampire = only_oid(game, "vampire_of_the_dire_moon", 0)
    bear = only_oid(game, "grizzly_bears", 0)
    artist = only_oid(game, "blood_artist", 0)
    game.state.objects[vampire].is_token = True
    game.state.objects[bear].is_token = True

    def junk(oid):
        return STRATEGY.junk_value(game.state, 0, oid, 0.0)

    assert junk(bear) > junk(vampire) > junk(artist)
