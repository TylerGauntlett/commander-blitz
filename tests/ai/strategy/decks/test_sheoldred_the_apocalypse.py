"""Sheoldred ("Draw Death"): hand out cards only while each one costs the drawer life."""

from __future__ import annotations

from automtg.ai.agents.heuristic_agent import HeuristicAgent
from automtg.engine.enums import ActionKind

DECK = "sheoldred_the_apocalypse"


def chosen(game, seat: int = 0):
    return HeuristicAgent(0).act(game, seat, game.legal_actions())


def card_of(game, action) -> str:
    return game.state.objects[action.source].def_id if action.source is not None else ""


def players_targeted(action) -> list[int]:
    return [ref.id for ref in action.targets if ref.kind == "player"]


class TestPacts:
    def test_without_a_punisher_sign_in_blood_draws_us_the_cards(self, builder):
        game = builder().hand(0, ["sign_in_blood"]).battlefield(0, ["swamp"] * 2).deck(0, DECK).build()
        action = chosen(game)
        assert card_of(game, action) == "sign_in_blood"
        assert players_targeted(action) == [0]

    def test_with_sheoldred_out_it_goes_across_the_table(self, builder):
        game = (
            builder()
            .hand(0, ["sign_in_blood"])
            .battlefield(0, ["swamp"] * 2 + ["sheoldred_the_apocalypse"])
            .deck(0, DECK)
            .build()
        )
        action = chosen(game)
        assert card_of(game, action) == "sign_in_blood"
        assert players_targeted(action) == [1]

    def test_a_pact_that_kills_is_aimed_at_the_player_it_kills(self, builder):
        game = (
            builder(players=3)
            .hand(0, ["sign_in_blood", "t_big"])
            .battlefield(0, ["swamp"] * 8 + ["sheoldred_the_apocalypse"])
            .life(1, 30)
            .life(2, 6)
            .deck(0, DECK)
            .build()
        )
        # Two cards at two each, plus two: six, exactly what seat 2 has left.
        action = chosen(game)
        assert card_of(game, action) == "sign_in_blood"
        assert players_targeted(action) == [2]


class TestGroupDraw:
    def test_temple_bell_stays_untapped_without_a_punisher(self, builder):
        game = builder().battlefield(0, ["temple_bell"]).deck(0, DECK).build()
        assert chosen(game).kind is ActionKind.PASS

    def test_temple_bell_rings_under_sheoldred(self, builder):
        game = (
            builder().battlefield(0, ["temple_bell", "sheoldred_the_apocalypse"]).deck(0, DECK).build()
        )
        action = chosen(game)
        assert action.kind is ActionKind.ACTIVATE
        assert card_of(game, action) == "temple_bell"

    def test_font_of_mythos_is_held_until_somebody_pays_for_the_cards(self, builder):
        game = builder().hand(0, ["font_of_mythos"]).battlefield(0, ["swamp"] * 4).deck(0, DECK).build()
        assert chosen(game).kind is ActionKind.PASS
