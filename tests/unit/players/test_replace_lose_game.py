"""`replace_lose_game` -- "if you would lose the game, instead …" (614.1, 104.3).

    The Golden Throne — "Arcane Life-support — If you would lose the game,
    instead exile The Golden Throne and your life total becomes 1."

A replacement of the *loss*, where `cant_lose_the_game` is a prohibition that
runs nothing: with only the prohibition the Throne would never leave and the
life total would never become 1, so the card would be Platinum Angel on an
artifact -- a permanent, unconditional immunity instead of one second chance.

What would be wrong without each claim:

- **Every cause is replaced** -- 0 life, poison, commander damage, the empty
  library, a `lose_game` op -- because "lose the game" names no cause. A hook
  on the life total alone would let the Throne sit through ten poison.
- **A cause that persists is a new loss at the next check.** The Throne fixes
  the life total and nothing else, so a player with ten poison counters is
  saved once and loses at the next state-based check. Without that the Throne
  would be poison immunity; without the source leaving, it would replace the
  same poison at every check for ever.
- **The replaced draw is spent.** 704.5b asks about draws since the last check;
  a flag left standing would spend a second Throne on the same draw.
- **"Can't lose" comes first.** A loss that cannot happen is not replaced, so
  beside a "you can't lose the game" static the Throne stays where it is.
- **Only its controller's loss, and never a win.** An opponent at 0 still loses,
  and an opponent's win is not "you would lose".
- **`set_life_total` is a gain or a loss** (119.5), so the life events fire and
  a locked life total does not move.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import LossReason
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.temp_effects import lock_life_total
from tests.conftest import oids_of

THRONE = "t_golden_throne"
PLATINUM = "t_platinum_holder"
BEAR = "t_bear"


def board(builder, mine=(THRONE,), theirs=(BEAR,)):
    """Player 0 with ``mine``, player 1 with ``theirs``, frozen in main phase."""
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    return game, game.state.players[0]


def run(game, effects, controller: int = 0) -> None:
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, effects)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def thrones_in_play(game) -> int:
    return len(oids_of(game, THRONE))


def thrones_in_exile(game, pid: int = 0) -> int:
    state = game.state
    return sum(1 for oid in state.players[pid].exile if state.objects[oid].def_id == THRONE)


class TestEveryCauseIsReplaced:
    @pytest.mark.parametrize("cause", ["life", "poison", "commander", "library"])
    def test_the_state_based_loss_is_replaced(self, builder, cause):
        game, me = board(builder)
        if cause == "life":
            me.life = -3
        elif cause == "poison":
            me.poison = 10
        elif cause == "commander":
            me.commander_damage_taken[99] = 21
        else:
            me.attempted_draw_from_empty = True
        sba._player_losses(game.state)
        assert not me.has_lost
        assert me.life == 1
        assert thrones_in_play(game) == 0
        assert thrones_in_exile(game) == 1

    def test_a_lose_game_op_is_replaced(self, builder):
        game, me = board(builder)
        run(game, [{"op": "lose_game"}])
        assert not me.has_lost and not game.over
        assert me.life == 1
        assert thrones_in_exile(game) == 1

    def test_from_zero_life_the_player_plays_on(self, builder):
        game, me = board(builder)
        me.life = 0
        sba.run(game.state)
        assert not game.over
        assert me.life == 1


class TestACauseThatPersists:
    def test_poison_loses_at_the_next_check(self, builder):
        game, me = board(builder)
        me.poison = 10
        sba.run(game.state)
        assert me.has_lost
        assert me.loss_reason is LossReason.POISON

    def test_each_check_spends_one_throne(self, builder):
        game, me = board(builder, mine=(THRONE, THRONE))
        me.commander_damage_taken[99] = 21
        sba._player_losses(game.state)
        assert (thrones_in_play(game), me.has_lost) == (1, False)
        sba._player_losses(game.state)
        assert (thrones_in_play(game), me.has_lost) == (0, False)
        sba._player_losses(game.state)
        assert me.loss_reason is LossReason.COMMANDER_DAMAGE

    def test_the_replaced_draw_is_spent(self, builder):
        game, me = board(builder, mine=(THRONE, THRONE))
        me.attempted_draw_from_empty = True
        sba.run(game.state)
        assert not me.has_lost
        assert not me.attempted_draw_from_empty
        assert thrones_in_play(game) == 1, "one draw spends one Throne"


class TestCantLoseComesFirst:
    def test_a_forbidden_loss_is_not_replaced(self, builder):
        game, me = board(builder, mine=(THRONE, PLATINUM))
        me.life = 0
        sba.run(game.state)
        assert not me.has_lost
        assert me.life == 0
        assert thrones_in_play(game) == 1

    def test_the_lose_game_op_is_held_off_too(self, builder):
        game, me = board(builder, mine=(PLATINUM,))
        run(game, [{"op": "lose_game"}])
        assert not me.has_lost and not game.over


class TestWhoseLoss:
    def test_an_opponent_still_loses(self, builder):
        game, _ = board(builder)
        game.state.players[1].life = 0
        sba.run(game.state)
        assert game.state.players[1].has_lost
        assert thrones_in_play(game) == 1

    def test_an_opponents_win_is_not_replaced(self, builder):
        game, me = board(builder)
        sba.declare_win(game.state, 1)
        assert me.has_lost
        assert me.loss_reason is LossReason.OPPONENT_WON
        assert game.winners == [1]


class TestSetLifeTotal:
    def test_down_is_a_loss_of_the_difference(self, builder):
        game, me = board(builder, mine=())
        game.state.events.clear()
        run(game, [{"op": "set_life_total", "amount": 7}])
        assert me.life == 7
        lost = [e for e in game.state.events if e.type == EventType.LIFE_LOST]
        assert [e.data["amount"] for e in lost] == [33]

    def test_up_is_a_gain_of_the_difference(self, builder):
        game, me = board(builder, mine=())
        me.life = -4
        game.state.events.clear()
        run(game, [{"op": "set_life_total", "amount": {"starting_life_of": "you"}}])
        assert me.life == me.starting_life
        gained = [e for e in game.state.events if e.type == EventType.LIFE_GAINED]
        assert [e.data["amount"] for e in gained] == [me.starting_life + 4]

    def test_a_locked_life_total_does_not_move(self, builder):
        game, me = board(builder, mine=())
        lock_life_total(game.state, 0)
        run(game, [{"op": "set_life_total", "amount": 1}])
        assert me.life == 40

    def test_it_names_other_players(self, builder):
        game, _ = board(builder, mine=())
        run(game, [{"op": "set_life_total", "amount": 5, "player": "opponent"}])
        assert [p.life for p in game.state.players] == [40, 5]


def _card(static=None, effect=None):
    abilities = []
    if static is not None:
        abilities.append({"kind": "static", "text": "If you would lose the game…", **static})
    if effect is not None:
        abilities.append({"kind": "activated", "text": "{T}: …", "cost": {"tap": True},
                          "effects": [effect]})
    return CardModel.model_validate(
        {
            "id": "t_bad_throne",
            "name": "Test Bad Throne",
            "oracle_text": "If you would lose the game…",
            "mana_cost": "{3}",
            "types": ["Artifact"],
            "abilities": abilities,
        }
    )


EXILE_SELF = {"op": "exile", "objects": {"zone": "battlefield", "self_only": True}}


class TestTheLoaderGuard:
    def test_the_throne_loads(self):
        compile_card(_card({"effect": "replace_lose_game", "affects_player": "you",
                            "effects": [EXILE_SELF, {"op": "set_life_total", "amount": 1}]}))

    def test_it_needs_effects(self):
        with pytest.raises(DslError, match="needs 'effects'"):
            compile_card(_card({"effect": "replace_lose_game", "affects_player": "you"}))

    def test_an_op_that_could_ask_is_refused(self):
        with pytest.raises(DslError, match="may not ask a question"):
            compile_card(_card({"effect": "replace_lose_game", "affects_player": "you",
                                "effects": [EXILE_SELF, {"op": "draw", "amount": 7}]}))

    def test_exiling_anything_else_is_refused(self):
        other = {"op": "exile", "objects": {"zone": "battlefield", "types": ["Creature"]}}
        with pytest.raises(DslError, match="exiles only its own source"):
            compile_card(_card({"effect": "replace_lose_game", "affects_player": "you",
                                "effects": [other]}))

    def test_the_source_must_leave(self):
        with pytest.raises(DslError, match="must exile this permanent"):
            compile_card(_card({"effect": "replace_lose_game", "affects_player": "you",
                                "effects": [{"op": "set_life_total", "amount": 1}]}))

    def test_only_its_controllers_loss(self):
        with pytest.raises(DslError, match="'affects_player' is 'you'"):
            compile_card(_card({"effect": "replace_lose_game", "affects_player": "opponent",
                                "effects": [EXILE_SELF]}))

    def test_effects_stay_refused_on_other_statics(self):
        with pytest.raises(DslError, match="cannot have 'effects'"):
            compile_card(_card({"effect": "cant_lose_the_game", "affects_player": "you",
                                "effects": [EXILE_SELF]}))

    def test_set_life_total_needs_an_amount(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(_card(effect={"op": "set_life_total"}))
