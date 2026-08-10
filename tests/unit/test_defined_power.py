"""Creatures printed `*/*`, and the loop Cultivator Colossus runs on arrival.

`*/*` is a static `set_pt` reading a count, so the number has to *move* when the
board does -- a card that reads the count once on arrival looks identical for a
whole turn and is wrong the moment a land is played.

The ETB loop is the other half: "if you do, draw a card and repeat this process"
has no count known up front, and a version that asked a fixed number of times
would let a player decline and then accept, which the printed card does not.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import only_oid


class TestDefinedPower:
    def test_it_counts_the_lands_you_control(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 5 + ["cultivator_colossus"])
            .battlefield(1, ["forest"] * 3)
            .build()
        )
        colossus = only_oid(game, "cultivator_colossus")
        got = chars(game.state, colossus)
        assert (got.power, got.toughness) == (5, 5), "yours, not everyone's"

    def test_it_moves_when_the_board_does(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 5 + ["cultivator_colossus"])
            .hand(0, ["forest"])
            .build()
        )
        colossus = only_oid(game, "cultivator_colossus")
        assert chars(game.state, colossus).power == 5

        land = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND
            and game.state.objects[a.source].def_id == "forest"
        )
        game.apply(land)
        assert chars(game.state, colossus).power == 6


class TestTheArrivalLoop:
    def board(self, builder, lands_in_hand: int):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * 8)
            .hand(0, ["cultivator_colossus"] + ["forest"] * lands_in_hand)
            .library(0, ["island"] * 20)
            .build()
        )

    def cast_it(self, game):
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "cultivator_colossus"
        )
        game.apply(cast)

    def run(self, game, answers: list[bool]) -> int:
        """Cast it, answer each question in turn, and report how many were asked.

        Anything the questions themselves raise -- "which land?" -- is answered
        along the way, so the count is of the card's own decision and nothing
        else. Unlisted questions are declined, which is how the loop terminates.
        """
        from tests.conftest import _default_answer

        self.cast_it(game)
        pending = iter(answers)
        asked = 0
        for _ in range(200):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.MAY:
                asked += 1
                want = ActionKind.YES if next(pending, False) else ActionKind.NO
                game.apply(next(a for a in game.legal_actions() if a.kind is want))
                continue
            if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
                break
            game.apply(_default_answer(game, decision))
        return asked

    def lands(self, game):
        return [o for o in game.state.battlefield_objects(0) if o.def_id == "forest"]

    def test_saying_yes_puts_a_land_down_tapped_and_draws(self, builder):
        game = self.board(builder, lands_in_hand=3)
        before = len(game.state.players[0].library)
        self.run(game, [True])

        assert len(self.lands(game)) == 9, "the eight it started with, plus one"
        assert self.lands(game)[-1].tapped, "'onto the battlefield tapped'"
        assert len(game.state.players[0].library) == before - 1, "'draw a card'"

    def test_it_asks_again_after_a_yes(self, builder):
        """The 'repeat this process' half. One yes must not end the loop."""
        game = self.board(builder, lands_in_hand=3)
        asked = self.run(game, [True, True])
        assert asked >= 3, "yes, yes, and then asked a third time"
        assert len(self.lands(game)) == 10

    def test_a_no_ends_it(self, builder):
        game = self.board(builder, lands_in_hand=3)
        asked = self.run(game, [True, False])
        assert asked == 2, "declining stops the process, with lands still in hand"
        assert len(self.lands(game)) == 9

    def test_with_no_land_in_hand_it_does_not_ask_at_all(self, builder):
        game = self.board(builder, lands_in_hand=0)
        assert self.run(game, [True]) == 0
        colossus = only_oid(game, "cultivator_colossus")
        assert game.state.objects[colossus].zone is Zone.BATTLEFIELD
