"""Bruvac ("Millington"): hold the big mill for Bruvac, loop the Scepter, Oracle only to win."""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.engine.enums import ActionKind
from tests.conftest import action_for_card

DECK = "bruvac_the_grandiloquent"


def chosen(game, seat: int = 0):
    return HeuristicAgent(0).act(game, seat, game.legal_actions())


def card_of(game, action) -> str:
    return game.state.objects[action.source].def_id if action.source is not None else ""


class TestBruvacFirst:
    def test_traumatize_waits_for_bruvac(self, builder):
        game = (
            builder()
            .hand(0, ["traumatize"])
            .commander(0, ["bruvac_the_grandiloquent"])
            .battlefield(0, ["island"] * 5)
            .deck(0, DECK)
            .build()
        )
        action = chosen(game)
        assert card_of(game, action) == "bruvac_the_grandiloquent"

    def test_with_bruvac_out_traumatize_goes_at_the_shortest_library(self, builder):
        game = (
            builder(players=3)
            .hand(0, ["traumatize"])
            .battlefield(0, ["island"] * 5 + ["bruvac_the_grandiloquent"])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 40)
            .library(2, ["island"] * 25)
            .deck(0, DECK)
            .build()
        )
        action = chosen(game)
        assert card_of(game, action) == "traumatize"
        assert [ref.id for ref in action.targets] == [2]


class TestThassasOracle:
    def test_it_is_held_while_it_would_not_win(self, builder):
        game = (
            builder()
            .hand(0, ["thassa_s_oracle"])
            .battlefield(0, ["island"] * 2)
            .library(0, ["island"] * 30)
            .deck(0, DECK)
            .build()
        )
        assert chosen(game).kind is ActionKind.PASS

    def test_it_is_cast_when_devotion_covers_the_library(self, builder):
        game = (
            builder()
            .hand(0, ["thassa_s_oracle"])
            .battlefield(0, ["island"] * 2 + ["bruvac_the_grandiloquent"])
            .library(0, ["island"] * 3)
            .deck(0, DECK)
            .build()
        )
        # Bruvac's {U} and the Oracle's own {U}{U}: three, against three cards.
        assert card_of(game, chosen(game)) == "thassa_s_oracle"


class TestIsochronReversal:
    def test_scepter_imprints_reversal_and_the_loop_decks_the_table(self, builder):
        game = (
            builder(players=3)
            .hand(0, ["isochron_scepter", "dramatic_reversal", "brain_freeze"])
            .battlefield(0, ["island"] * 4 + ["sol_ring", "gilded_lotus", "bruvac_the_grandiloquent"])
            .battlefield(0, ["persistent_petitioners"] * 4)
            .library(0, ["island"] * 30)
            .library(1, ["island"] * 80)
            .library(2, ["island"] * 70)
            .deck(0, DECK)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "isochron_scepter"))
        agent = HeuristicAgent(0)
        # Every seat is the agent; a loop that never terminated would run out
        # the step budget rather than hang the suite.
        for _ in range(600):
            if game.over or game.state.turn > 1:
                break
            decision = game.pending()
            game.apply(agent.act(game, decision.player, game.legal_actions()))
        exiled = [
            o.def_id for o in game.state.objects.values() if o.exiled_by is not None and o.controller == 0
        ]
        assert exiled == ["dramatic_reversal"]
        assert game.state.turn == 2, "the loop must end and pass the turn"
        assert [len(game.state.players[pid].library) for pid in (1, 2)] == [0, 0]
        assert len(game.state.players[0].library) == 30, "it never mills itself"


class TestBrainFreeze:
    def build(self, builder, storm: int):
        game = (
            builder(players=3)
            .hand(0, ["brain_freeze"])
            .battlefield(0, ["island"] * 2 + ["bruvac_the_grandiloquent"])
            .library(0, ["island"] * 20)
            .library(1, ["island"] * 40)
            .library(2, ["island"] * 30)
            .deck(0, DECK)
            .build()
        )
        game.state.turn_ledger.spells_cast[0] = storm
        return game

    def test_it_waits_for_a_storm_count(self, builder):
        game = self.build(builder, storm=0)
        assert chosen(game).kind is ActionKind.PASS

    def test_every_copy_goes_across_the_table(self, builder):
        game = self.build(builder, storm=3)
        action = chosen(game)
        assert card_of(game, action) == "brain_freeze"
        game.apply(action)
        agent = HeuristicAgent(0)
        while game.state.stack and not game.over:
            decision = game.pending()
            game.apply(agent.act(game, decision.player, game.legal_actions()))
        libraries = [len(p.library) for p in game.state.players]
        # Four copies of three, doubled: twenty-four cards, none of them ours.
        assert libraries[0] == 20
        assert 40 + 30 - libraries[1] - libraries[2] == 24
