""""Starting with you, each player…" -- a player loop in turn order from its controller.

    Druid of Purification -- "When this creature enters, starting with you,
    each player may choose an artifact or enchantment you don't control.
    Destroy each permanent chosen this way."

`for_each_player` walks the players `select_players` returns, and
`"each_player"` returns them in **seat order**. That is turn order from seat 0,
so it agrees with the printed card only while the controller sits there. The
printed card names the order (the effect's own instruction, not rule 101.4's
APNAP default): the controller first, then onward in turn order. The order is
not cosmetic. Each later player sees what the earlier ones chose, and on the
Druid a player who sees an opponent take the artifact they wanted gone picks
something else -- the same politics `join_forces` carries, and the order it
already walks through `GameState.turn_order`.

``starting_with: "you"`` reorders the players the spec found; it does not change
which players they are. Anything else under the key is refused at load time,
because a misspelling read as "no order" would quietly fall back to seat order.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError

RING = "sol_ring"

#: Druid of Purification's body, minus the trigger.
CHOOSE = {
    "op": "choose_permanents",
    "as": "chosen",
    "prompt": "Choose an artifact or enchantment to destroy",
    "objects": {
        "zone": "battlefield",
        "controller": "opponent",
        "any_types": ["Artifact", "Enchantment"],
        "count": 1,
        "optional": True,
        "chooser": {"binding": "each_player"},
    },
}


def loop(**extra) -> dict:
    return {"op": "for_each_player", "players": "each_player", "effects": [CHOOSE], **extra}


def table(builder, players: int = 4):
    game = builder(players=players)
    for pid in range(players):
        game = game.battlefield(pid, [RING])
    return game.build(advance=False)


def run(game, spec: dict, controller: int):
    """Drive the loop, every chooser declining; return who was asked, in order."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = OPS["for_each_player"](ctx, spec)
    asked: list[int] = []
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision.player)
        send = []


class TestTheOrder:
    def test_it_starts_with_the_controller(self, builder):
        game = table(builder)
        assert run(game, loop(starting_with="you"), controller=2) == [2, 3, 0, 1]

    def test_it_ignores_who_is_active(self, builder):
        """"You" is the controller, not the active player."""
        game = table(builder)
        game.state.active_idx = 1
        assert run(game, loop(starting_with="you"), controller=3) == [3, 0, 1, 2]

    def test_without_it_the_loop_walks_seat_order(self, builder):
        """The near miss, pinned: right only when the controller is seat 0."""
        game = table(builder)
        assert run(game, loop(), controller=2) == [0, 1, 2, 3]

    def test_from_seat_zero_the_two_coincide(self, builder):
        game = table(builder)
        assert run(game, loop(starting_with="you"), controller=0) == run(
            table(builder), loop(), controller=0
        )


class TestWhoIsInTheLoop:
    def test_it_reorders_the_spec_and_adds_nobody(self, builder):
        """`each_opponent` stays opponents: the controller is not added back."""
        game = table(builder)
        spec = {**loop(starting_with="you"), "players": "each_opponent"}
        assert run(game, spec, controller=2) == [3, 0, 1]

    def test_a_player_who_has_lost_is_skipped(self, builder):
        game = table(builder)
        game.state.players[3].has_lost = True
        assert run(game, loop(starting_with="you"), controller=2) == [2, 0, 1]


class TestTheChoicesAccumulate:
    def test_every_players_pick_lands_in_one_binding(self, builder):
        """"Destroy each permanent chosen this way": the binding collects them all.

        Controller 1 at three seats: the pool is the rings of seats 0 and 2,
        and each chooser in turn takes the last one offered.
        """
        game = table(builder, players=3)
        ctx = EffectContext(state=game.state, controller=1)
        gen = OPS["for_each_player"](ctx, loop(starting_with="you"))
        picks: list[tuple[int, int]] = []
        send = None
        while True:
            try:
                decision = gen.send(send)
            except StopIteration:
                break
            last = len(decision.options) - 1
            picks.append((decision.player, decision.options[last].ref.id))
            send = [last]
        assert [pid for pid, _ in picks] == [1, 2, 0]
        assert sorted(ctx.bindings["chosen"]) == sorted(oid for _, oid in picks)
        assert all(game.state.objects[oid].controller != 1 for _, oid in picks)


class TestTheLoader:
    def test_you_loads(self):
        _validate_effect(loop(starting_with="you"), "t", {})

    @pytest.mark.parametrize("bad", ["controller", "active_player", "each_player", True])
    def test_any_other_value_is_refused(self, bad):
        with pytest.raises(DslError, match="starting_with"):
            _validate_effect(loop(starting_with=bad), "t", {})
