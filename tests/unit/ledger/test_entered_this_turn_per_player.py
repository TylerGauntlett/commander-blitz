"""Permanents that entered this turn, counted for *each* player -- 603.4, 110.2.

"At the beginning of each end step, draw a card for each opponent who drew two
or more cards this turn, then create a Treasure token **for each opponent who
had two or more lands enter the battlefield under their control this turn**"
-- Smuggler's Share, in the Obscura Operation precon.

The question is asked of every opponent separately, and `each_opponent` cannot
ask it: as a `controller` it sums all the opponents' arrivals into one total,
so at a pod two opponents who played one land each read as one opponent who
had two, and the card makes a Treasure nobody earned. The witness below is
exactly that board.

So inside a `for_each_player` loop, the effect-side value takes
`{"controller": {"binding": "each_player"}}`, the player the loop is visiting,
and reads that player's own count. A static has no loop to bind anybody, so the
binding there would read nobody and 0 for ever; the static side keeps
refusing it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.statics import _validate_static_value as validate_static_value
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.state import new_object
from commanderblitz.engine.zones import move_object
from tests.conftest import count_on_battlefield

THEIR_LANDS = {
    "permanents_entered_this_turn": {
        "controller": {"binding": "each_player"},
        "types": ["Land"],
    }
}

#: Smuggler's Share's Treasure clause, as a card writes it.
TREASURE_PER_OPPONENT = {
    "op": "for_each_player",
    "players": "each_opponent",
    "effects": [
        {
            "op": "if",
            "condition": {"cmp": ">=", "left": THEIR_LANDS, "right": {"const": 2}},
            "then": [{"op": "create_token", "token": "treasure_token"}],
        }
    ],
}


def land_enters(game, pid: int) -> None:
    """A basic land arrives under ``pid``'s control, firing the real event."""
    obj = new_object(game.state, "forest", owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD)


def pod(builder, *, entered: dict[int, int]):
    game = builder(players=3).build()
    for pid, how_many in entered.items():
        for _ in range(how_many):
            land_enters(game, pid)
    return game


def treasures_made(game) -> int:
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    list(execute(ctx, [TREASURE_PER_OPPONENT]))
    return count_on_battlefield(game, "treasure_token", 0)


class TestEachOpponentIsCountedAlone:
    def test_the_binding_reads_the_visited_players_own_count(self, builder):
        game = pod(builder, entered={1: 2, 2: 1})
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)

        ctx.bindings["each_player"] = 1
        first = evaluate_value(ctx, THEIR_LANDS)
        ctx.bindings["each_player"] = 2
        second = evaluate_value(ctx, THEIR_LANDS)

        assert (first, second) == (2, 1)

    def test_two_opponents_with_one_land_each_earn_nothing(self, builder):
        """The witness: `each_opponent` sums these to 2 and would pay out."""
        game = pod(builder, entered={1: 1, 2: 1})
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        summed = {"permanents_entered_this_turn": {"controller": "each_opponent", "types": ["Land"]}}

        assert evaluate_value(ctx, summed) == 2, "the near miss, on the record"
        assert treasures_made(game) == 0

    def test_one_treasure_per_opponent_who_had_two(self, builder):
        game = pod(builder, entered={1: 2, 2: 3})
        assert treasures_made(game) == 2

    def test_the_boundary_is_two(self, builder):
        game = pod(builder, entered={1: 2, 2: 1})
        assert treasures_made(game) == 1

    def test_your_own_lands_never_count(self, builder):
        game = pod(builder, entered={0: 4})
        assert treasures_made(game) == 0


class TestTheLoaderAdmitsOnlyABinding:
    def test_the_effect_side_takes_a_binding(self):
        validate_value(THEIR_LANDS, "v")

    @pytest.mark.parametrize(
        "who",
        [{"target": "t1"}, {"binding": ""}, {"binding": "each_player", "extra": 1}],
    )
    def test_any_other_mapping_is_refused(self, who):
        with pytest.raises(DslError, match="controller"):
            validate_value(
                {"permanents_entered_this_turn": {"controller": who, "types": ["Land"]}}, "v"
            )

    def test_a_static_has_no_loop_and_refuses_it(self):
        with pytest.raises(DslError, match="controller"):
            validate_static_value(THEIR_LANDS, "v")
