"""Exchanging a life total with a creature's toughness -- 701.12.

Tree of Perdition is the witness: "{T}: Exchange target opponent's life total
with this creature's toughness." Three things make it an exchange rather than a
chain of a `set_pt` and a life change, and each is a test class here:

- **The life half is a gain or a loss** (119.5). The opponent's life total
  becomes the toughness by losing or gaining the difference, so a loss is a
  `LIFE_LOST` and a gain a `LIFE_GAINED`.
- **The toughness half is an indefinite layer-7b set.** The toughness becomes
  the player's *former* life total for as long as the creature stays, and
  counters still apply on top of it. `set_pt` is an until-end-of-turn pump, so a
  Tree written with it would shrink back at cleanup.
- **All or nothing** (701.12b). Under a life lock (118.5), or when the change
  would be a gain for a player who can't gain life, neither half happens --
  a chain would still have swapped the toughness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_life import op_exchange_life_total
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import add_counters, pump
from commanderblitz.engine.structs import LifeLock
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, only_oid, pass_until, pt, settle

PERDITION = "t_tree_of_perdition"
REDEMPTION = "t_tree_of_redemption"
EREBOS = "t_erebos"  # Your opponents can't gain life.


def position(builder, *, mine=(PERDITION,), my_life: int = 40, their_life: int = 40):
    """Player 0's main phase with a Tree; returns ``(game, tree)``.

    A Forest's worth of bear in hand stops the auto-pass rolling the game on.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 2 + list(mine))
        .hand(0, ["t_bear"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .life(0, my_life)
        .life(1, their_life)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    return game, only_oid(game, mine[-1], 0)


def exchange(game, tree: int) -> None:
    game.apply(activations(game, tree)[0])
    settle(game)


def life(game, pid: int) -> int:
    return game.state.players[pid].life


class TestTheExchange:
    def test_a_high_life_total_comes_down_to_the_toughness(self, builder):
        game, tree = position(builder)
        exchange(game, tree)
        assert life(game, 1) == 13
        assert pt(game, tree) == (0, 40), "the toughness is the opponent's former life"

    def test_the_life_half_is_a_loss(self, builder):
        game, tree = position(builder)
        mark = len(game.state.events)
        exchange(game, tree)
        lost = [e for e in game.state.events[mark:] if e.type == "life_lost"]
        assert [(e.player, e.data["amount"]) for e in lost] == [(1, 27)]

    def test_a_low_life_total_goes_up_as_a_gain(self, builder):
        game, tree = position(builder, their_life=5)
        mark = len(game.state.events)
        exchange(game, tree)
        assert life(game, 1) == 13
        assert pt(game, tree) == (0, 5)
        assert any(e.type == "life_gained" for e in game.state.events[mark:])

    def test_your_own_life_total(self, builder):
        """Tree of Redemption: the same op, ``player: "you"``."""
        game, tree = position(builder, mine=(REDEMPTION,), my_life=4)
        exchange(game, tree)
        assert life(game, 0) == 13
        assert pt(game, tree) == (0, 4)

    def test_the_current_toughness_is_what_is_exchanged(self, builder):
        """"This creature's toughness" is its toughness now, pumps included."""
        game, tree = position(builder)
        pump(game.state, tree, 0, 2)
        exchange(game, tree)
        assert life(game, 1) == 15


class TestTheToughnessIsSet:
    def test_it_lasts_past_the_turn(self, builder):
        game, tree = position(builder)
        exchange(game, tree)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        assert pt(game, tree) == (0, 40)

    def test_counters_apply_on_top(self, builder):
        """A 7b set, so a +1/+1 counter (7c) still counts after the exchange."""
        game, tree = position(builder)
        add_counters(game.state, tree, PLUS_ONE, 1)
        exchange(game, tree)
        assert life(game, 1) == 14
        assert pt(game, tree) == (1, 41)

    def test_it_ends_when_the_creature_leaves(self, builder):
        game, tree = position(builder)
        exchange(game, tree)
        assert game.state.objects[tree].animations
        move_object(game.state, tree, Zone.HAND)
        assert not game.state.objects[tree].animations


class TestAllOrNothing:
    def test_a_locked_life_total_exchanges_nothing(self, builder):
        game, tree = position(builder)
        game.state.life_locks.append(LifeLock(player=1))
        exchange(game, tree)
        assert life(game, 1) == 40
        assert pt(game, tree) == (0, 13), "the toughness half does not happen alone"

    def test_a_forbidden_gain_exchanges_nothing(self, builder):
        game, tree = position(builder, mine=(EREBOS, PERDITION), their_life=5)
        exchange(game, tree)
        assert life(game, 1) == 5
        assert pt(game, tree) == (0, 13)

    def test_a_loss_is_not_a_gain(self, builder):
        """"Can't gain life" forbids only the upward exchange."""
        game, tree = position(builder, mine=(EREBOS, PERDITION))
        exchange(game, tree)
        assert life(game, 1) == 13
        assert pt(game, tree) == (0, 40)

    def test_a_source_gone_before_resolution_exchanges_nothing(self, builder):
        """The Tree destroyed in response: there is no toughness to exchange."""
        game, tree = position(builder)
        move_object(game.state, tree, Zone.GRAVEYARD)
        ctx = EffectContext(state=game.state, controller=0, source_oid=tree)
        op_exchange_life_total(ctx, {"op": "exchange_life_total", "player": "opponent"})
        assert life(game, 1) == 40


def _tree(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "{T}: Exchange.",
            "mana_cost": "{B}",
            "types": ["Creature"],
            "power": 0,
            "toughness": 1,
            "abilities": [
                {"kind": "activated", "text": "{T}: Exchange.", "cost": {"tap": True},
                 "effects": [effect]}
            ],
        }
    )


class TestTheLoaderRefuses:
    def test_a_missing_player(self):
        with pytest.raises(DslError, match="needs 'player'"):
            compile_card(_tree({"op": "exchange_life_total"}))

    @pytest.mark.parametrize(
        ("key", "value"),
        [("objects", {"controller": "you"}), ("amount", {"const": 1}), ("duration", "permanent")],
    )
    def test_keys_it_does_not_read(self, key, value):
        with pytest.raises(DslError, match=f"takes no '{key}'"):
            compile_card(_tree({"op": "exchange_life_total", "player": "you", key: value}))
