"""Bard, King of Dale: cantrips feed the payoffs, Greaves guards Bard, Skullclamp eats tokens."""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.engine.enums import ActionKind
from tests.conftest import only_oid

DECK = "bard_king_of_dale"


def make_commander(game, seat: int, card_id: str) -> int:
    oid = only_oid(game, card_id, seat)
    game.state.objects[oid].is_commander = True
    game.state.players[seat].commanders.append(oid)
    return oid


def chosen_card(game, action) -> str:
    return game.state.objects[action.source].def_id


def test_a_cantrip_beats_a_one_drop_once_a_draw_payoff_is_out(builder):
    def position(board):
        return builder().deck(0, DECK).battlefield(0, ["tundra", *board]).hand(0, ["opt", "esper_sentinel"]).build()

    bare = position([])
    assert chosen_card(bare, HeuristicAgent(0).act(bare, 0, bare.legal_actions())) == "esper_sentinel"
    paid = position(["prince_imrahil_the_fair"])
    assert chosen_card(paid, HeuristicAgent(0).act(paid, 0, paid.legal_actions())) == "opt"


def test_lightning_greaves_goes_on_bard(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["t_bear", "bard_king_of_dale", "lightning_greaves"])
        .build()
    )
    bard = make_commander(game, 0, "bard_king_of_dale")
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.ACTIVATE
    assert [ref.id for ref in chosen.targets] == [bard]


def test_skullclamp_goes_on_a_one_toughness_token(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["t_bear", "esper_sentinel", "skullclamp", "plains"])
        .build()
    )
    token = only_oid(game, "esper_sentinel", 0)
    game.state.objects[token].is_token = True
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.ACTIVATE
    assert [ref.id for ref in chosen.targets] == [token]


def test_perch_protection_is_never_cast_with_the_gift(builder):
    game = (
        builder()
        .deck(0, DECK)
        .battlefield(0, ["plains"] * 6)
        .hand(0, ["perch_protection"])
        .build()
    )
    gifts = [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.gift_to is not None]
    assert gifts, "the engine offers the gifted cast"
    chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
    assert chosen.kind is ActionKind.CAST
    assert chosen.gift_to is None
