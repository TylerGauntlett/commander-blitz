"""`lose_game` -- "that player loses the game" (104.3a).

Vraska the Unseen's Assassin token is the witness: "Whenever this creature
deals combat damage to a player, that player loses the game." The Pact cycle's
unpaid upkeep is the same sentence with ``player: "you"``.

`win_game` on the controller is the near miss, and in a duel it even gives the
same result. In a pod it does not: `sba.declare_win` eliminates *every* other
seat, so one Assassin hit would knock out the players it never touched. So the
claim under test is that exactly the named seat leaves -- through the same
`sba._eliminate` a lethal life total reaches, with its own loss reason -- and
the rest play on.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import LossReason, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import damage_player
from tests.conftest import _default_answer, only_oid

ASSASSIN = "assassin_1_1_b_lose_game"
BEAR = "t_bear"


def a_table(builder, *, players: int = 2, assassin: bool = False):
    b = builder(players=players)
    for pid in range(players):
        b = b.battlefield(pid, [BEAR]).library(pid, ["forest"] * 10)
    if assassin:
        b = b.battlefield(0, [ASSASSIN])
    return b.step(Step.PRECOMBAT_MAIN).build(advance=False)


def lose(game, controller: int = 0, **spec) -> None:
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [{"op": "lose_game", **spec}])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def settle(game, limit: int = 40) -> None:
    for _ in range(limit):
        if game.over or (not game.state.pending_triggers and not game.state.stack):
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never resolved")


class TestTheOp:
    def test_you_lose_by_default(self, builder):
        game = a_table(builder)
        lose(game)
        assert game.over
        assert game.winners == [1]
        assert game.state.players[0].loss_reason is LossReason.LOST_BY_EFFECT

    def test_in_a_pod_only_the_named_seat_leaves(self, builder):
        """The difference from `win_game`: nobody else is eliminated."""
        game = a_table(builder, players=3)
        lose(game, controller=1)
        assert not game.over
        assert game.state.alive() == [0, 2]
        assert game.state.players[1].has_lost
        lost = [e for e in game.state.events if e.type == EventType.PLAYER_LOST]
        assert [e.player for e in lost] == [1]

    def test_its_permanents_leave_with_it(self, builder):
        game = a_table(builder, players=3)
        bear = only_oid(game, BEAR, 1)
        lose(game, controller=1)
        assert game.state.objects[bear].zone is Zone.EXILE

    def test_a_seat_already_gone_is_a_no_op(self, builder):
        game = a_table(builder, players=3)
        lose(game, controller=1)
        lose(game, controller=1)
        assert game.state.alive() == [0, 2]
        assert not game.over

    def test_everyone_losing_is_a_draw(self, builder):
        game = a_table(builder)
        lose(game, player="each_player")
        assert game.over
        assert game.state.result == "draw"


class TestTheAssassin:
    def test_combat_damage_makes_that_player_lose(self, builder):
        game = a_table(builder, players=3, assassin=True)
        assassin = only_oid(game, ASSASSIN, 0)
        damage_player(game.state, 2, 1, assassin, is_combat=True)
        settle(game)
        assert game.state.players[2].has_lost
        assert game.state.players[2].loss_reason is LossReason.LOST_BY_EFFECT
        assert game.state.alive() == [0, 1], "the untouched opponent plays on"
        assert not game.over

    def test_noncombat_damage_does_not(self, builder):
        game = a_table(builder, players=3, assassin=True)
        assassin = only_oid(game, ASSASSIN, 0)
        damage_player(game.state, 2, 1, assassin)
        settle(game)
        assert game.state.alive() == [0, 1, 2]

    def test_in_a_duel_the_hit_wins_the_game(self, builder):
        game = a_table(builder, assassin=True)
        assassin = only_oid(game, ASSASSIN, 0)
        damage_player(game.state, 1, 1, assassin, is_combat=True)
        settle(game)
        assert game.over
        assert game.winners == [0]


class TestTheLoader:
    def test_a_condition_on_the_op_is_refused(self):
        card = {
            "id": "t_bad_pact",
            "name": "Test Bad Pact",
            "oracle_text": "You lose the game.",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "spell_effects": [
                {"op": "lose_game", "condition": {"has_flag": "unpaid"}, "player": "you"}
            ],
        }
        with pytest.raises(DslError, match="lose_game reads no 'condition'"):
            compile_card(CardModel.model_validate(card))
