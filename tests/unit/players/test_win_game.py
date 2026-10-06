"""`win_game` — 104.2a, and the one place a game result may be written.

"{W}{W}{W}{W}{W}, {T}, Untap fifteen tapped creatures you control: **You win the
game.**" (Halo Fountain.) "If you rolled 6 exactly seven times, **you win the
game.**" (Luck Bobblehead.) Both gap records blocked on the same sentence and
gave the same diagnosis: `sba.check_game_over` is the engine's only writer of
`state.winners`, and it derives the winner from who survives state-based
actions — so a winner was always a *consequence* of everybody else dying, and
nothing could declare one while every player sat at 40 life.

The two available approximations are both a different card. `damage` or
`lose_life` for a lethal amount gets to a game over through the life total,
which is preventable, replaceable, and simply does not reach 40 life from one
activation of a Fountain. `set_flag` records a boolean that only a `has_flag`
condition reads and changes nothing about the outcome at all.

So the claim under test is not "the game ends" — it is **how** it ends. The op
eliminates every other player and then calls `check_game_over`, rather than
assigning `state.winners` itself, and everything below is a way of asking
whether the result and the board still agree afterwards: the loser has a
`PLAYER_LOST` with an honest reason, their permanents are gone, priority is
nobody's, `Game.over` and `Game.winners` say the same thing the serializer
would, and a later state-based pass does not re-decide any of it.

The boundary is the pod: at three players "you win the game" is *two*
eliminations, not one, and a version that only removed the next seat round
would leave the game running with the winner still in it.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sba
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import LossReason
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.serialize import full_view

BEAR = "t_bear"


def a_table(builder, *, players: int = 2):
    """A game with a creature apiece, and nobody anywhere near dying."""
    b = builder(players=players)
    for pid in range(players):
        b = b.battlefield(pid, [BEAR])
    return b.build()


def win(game, controller: int = 0, **spec) -> None:
    """Resolve one `win_game`, driven the way an ability's effects are."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [{"op": "win_game", **spec}])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def game_over_events(game):
    return [e for e in game.state.events if e.type == EventType.GAME_OVER]


class TestItEndsTheGameWithoutTouchingLife:
    def test_the_controller_wins(self, builder):
        game = a_table(builder)
        win(game)
        assert game.over
        assert game.winners == [0]

    def test_the_result_is_a_win_and_not_a_draw(self, builder):
        game = a_table(builder)
        win(game)
        assert game.state.result == "win"

    def test_nobody_lost_any_life(self, builder):
        """The whole reason `damage` could not stand in."""
        game = a_table(builder)
        assert [p.life for p in game.state.players] == [40, 40]
        win(game)
        assert [p.life for p in game.state.players] == [40, 40]

    def test_the_opponent_is_eliminated(self, builder):
        game = a_table(builder)
        win(game)
        assert game.state.players[1].has_lost
        assert not game.state.players[0].has_lost

    def test_the_loss_reason_says_what_happened(self, builder):
        """A seat eliminated at 40 life did not run out of life, and the
        frontend prints this reason to them."""
        game = a_table(builder)
        win(game)
        assert game.state.players[1].loss_reason is LossReason.OPPONENT_WON

    def test_a_named_player_wins_instead(self, builder):
        """The player spec is not decoration: written for the wrong seat this op
        hands the game to the wrong seat, which is the whole card."""
        game = a_table(builder)
        win(game, player=1)
        assert game.winners == [1]
        assert game.state.players[0].loss_reason is LossReason.OPPONENT_WON


class TestItGoesThroughCheckGameOver:
    def test_the_loser_gets_a_player_lost_event(self, builder):
        """Not a bare `state.winners = [0]`: the seat that lost has to *leave*."""
        game = a_table(builder)
        win(game)
        (lost,) = [e for e in game.state.events if e.type == EventType.PLAYER_LOST]
        assert lost.player == 1
        assert lost.data["reason"] == LossReason.OPPONENT_WON.value

    def test_the_losers_permanents_leave_with_them(self, builder):
        game = a_table(builder)
        theirs = [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].controller == 1
        ]
        assert theirs, "the position is only interesting if they had a board"
        win(game)
        assert not any(
            game.state.objects[oid].controller == 1 for oid in game.state.battlefield
        )

    def test_priority_and_the_pending_decision_are_cleared(self, builder):
        game = a_table(builder)
        assert game.pending() is not None
        win(game)
        assert game.state.priority_idx is None
        assert game.state.pending_decision is None
        assert game.state.pending_generator is None

    def test_exactly_one_game_over_event(self, builder):
        game = a_table(builder)
        win(game)
        (over,) = game_over_events(game)
        assert over.data["winners"] == [0]
        assert over.data["result"] == "win"

    def test_the_serialized_view_agrees(self, builder):
        """`Game.over`, `Game.winners` and the wire format read one writer."""
        game = a_table(builder)
        win(game)
        view = full_view(game.state)
        assert view["game_over"] is True
        assert view["winners"] == [0]
        assert view["result"] == "win"

    def test_no_action_is_legal_afterwards(self, builder):
        game = a_table(builder)
        win(game)
        assert game.legal_actions() == []


class TestItIsNotRedecided:
    def test_a_later_state_based_pass_leaves_the_winner_alone(self, builder):
        """`check_game_over` returns early once `game_over` is set; this pins that
        the win survives the pass the engine makes after every resolution."""
        game = a_table(builder)
        win(game)
        sba.run(game.state)
        assert game.winners == [0]
        assert len(game_over_events(game)) == 1

    def test_a_second_win_does_not_change_the_answer(self, builder):
        """Two simultaneous wins: the first named seat keeps it, and the game is
        not re-decided into a draw by eliminating everybody."""
        game = a_table(builder)
        win(game)
        win(game, player=1)
        assert game.winners == [0]
        assert game.state.result == "win"

    def test_a_player_who_has_already_left_cannot_win(self, builder):
        """The other order. Eliminating "everybody else" on behalf of a seat that
        is already out empties the table, and `check_game_over` would call that a
        draw -- so the sentence has to do nothing instead."""
        game = a_table(builder, players=3)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.players[0].has_lost
        assert not game.over, "two seats are still playing"
        win(game, controller=0)
        assert not game.over
        assert not game.state.players[1].has_lost
        assert not game.state.players[2].has_lost


class TestThePod:
    def test_every_other_seat_loses(self, builder):
        """104.2a. At three players the sentence is two eliminations, and a
        version that removed one would leave the game running."""
        game = a_table(builder, players=3)
        win(game, controller=1)
        assert game.over
        assert game.winners == [1]
        assert game.state.players[0].has_lost
        assert game.state.players[2].has_lost

    def test_it_does_not_end_before_the_last_one_leaves(self, builder):
        """Eliminating one of two opponents must not trip `check_game_over`
        early -- the result is written once, with one seat left."""
        game = a_table(builder, players=3)
        win(game, controller=1)
        (over,) = game_over_events(game)
        assert over.data["winners"] == [1]

    def test_the_winner_keeps_their_board(self, builder):
        game = a_table(builder, players=3)
        win(game, controller=1)
        assert [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].controller == 1
        ]


def probe(effects):
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{W}",
            "types": ["Sorcery"],
            "spell_effects": effects,
        }
    )


class TestTheLoaderGuardsIt:
    def test_a_bare_win_game_compiles(self):
        card = compile_card(probe([{"op": "win_game"}]))
        assert [e["op"] for e in card.spell_effects] == ["win_game"]

    def test_a_condition_on_it_is_refused(self):
        """Luck Bobblehead's "**if** you rolled 6 exactly seven times". Nothing
        reads a `condition` on this op, so accepting one ships a card that wins
        the game every time it resolves and looks perfectly ordinary."""
        with pytest.raises(DslError, match="win_game reads no 'condition'"):
            compile_card(
                probe([{"op": "win_game", "condition": {"has_flag": "lucky"}}])
            )

    def test_the_condition_belongs_in_an_if(self):
        """And the shape the error points at does load."""
        card = compile_card(
            probe(
                [
                    {
                        "op": "if",
                        "condition": {"has_flag": "lucky"},
                        "then": [{"op": "win_game"}],
                    }
                ]
            )
        )
        assert card.spell_effects[0]["then"] == [{"op": "win_game"}]

    def test_a_nonsense_player_is_refused(self):
        """Through the shared `_validate_player_spec`, like every other op that
        names a seat -- so `win_game` needed no copy of that check."""
        with pytest.raises(DslError):
            compile_card(probe([{"op": "win_game", "player": "the_loser"}]))


class TestTheTwoCardsAreExpressible:
    """The sentences the gap records blocked on, as the DSL now spells them."""

    def test_halo_fountains_third_line(self):
        card = compile_card(
            CardModel.model_validate(
                {
                    "id": "probe_fountain",
                    "name": "Probe Fountain",
                    "oracle_text": "x",
                    "mana_cost": "{3}{W}",
                    "types": ["Enchantment"],
                    "abilities": [
                        {
                            "kind": "activated",
                            "cost": {"mana": "{W}{W}{W}{W}{W}", "tap": True},
                            "effects": [{"op": "win_game", "player": "you"}],
                        }
                    ],
                }
            )
        )
        (ability,) = card.abilities
        assert [e["op"] for e in ability.effects] == ["win_game"]

    def test_luck_bobbleheads_conditional_win(self):
        card = compile_card(
            probe(
                [
                    {
                        "op": "if",
                        "condition": {"has_flag": "sevens"},
                        "then": [{"op": "win_game", "player": "you"}],
                    }
                ]
            )
        )
        assert card.spell_effects[0]["op"] == "if"

    def test_it_actually_wins_when_the_branch_is_taken(self, builder):
        """Both halves together: the `if` gate and the op behind it."""
        game = a_table(builder)
        ctx = EffectContext(state=game.state, controller=0)
        gen = execute(
            ctx,
            [
                {
                    "op": "if",
                    "condition": {"has_flag": "sevens"},
                    "then": [{"op": "win_game"}],
                }
            ],
        )
        with contextlib.suppress(StopIteration):
            while True:
                next(gen)
        assert not game.over, "the false branch must not win the game"
        win(game)
        assert game.winners == [0]
