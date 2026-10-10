""""Equipped creature" on the effect side, and after it has died.

    Skullclamp — "Whenever equipped creature dies, draw two cards."
    Blade of the Bloodchief — "Whenever a creature dies, put a +1/+1 counter on
    equipped creature."

`attached` existed, in `STATIC_FILTER_KEYS` only. `characteristics` reads it
against `source.attached_to` while applying a *continuous* effect, which is why
"Equipped creature gets +1/-1" and Equip itself both worked on the very card
that could not be written. Two readers had no such key at all: the effect-side
selector language, so no `op` could reach the equipped creature; and trigger
filters, which go through `matches_card_filter` and read the printed card face.

**The dies trigger is the whole difficulty, and a naive version cannot work.**
`zones.move_object` calls `_detach_all` *before* it fires `LEAVES_BATTLEFIELD`
and `DIES`, so by the time the trigger is matched the Equipment is attached to
nothing. `source.attached_to == subject` is false for every dies trigger that
will ever be written — not sometimes, always.

So `last_attached_to` is explicit last-known information, the same shape as
`was_creature`, `was_attacking` and `had_counters`: written by `_detach_all` on
the way out, cleared by `attach` so an Equipment moved to a second creature
cannot still answer for the first. A stale value is harmless because oids are
never reused, so it can only ever match the object it already named.

Both new readers answer off the **ability's source**, not the subject — the same
argument `haunted_by` and cipher's `encoded_by` make. An Equipment knows what it
is attached to; a dying creature does not know what was attached to it.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Zone
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, settle

CLAMP = "t_clamp"  # +1/-1, "whenever equipped creature dies, draw two"
BLADE = "t_blade"  # "whenever a creature dies, +1/+1 counter on equipped creature"
BEAR = "t_bear"  # 2/2
DORK = "t_dork"  # 1/1


def board(builder, equipment: str, creatures=(BEAR,)):
    game = (
        builder(players=2)
        .battlefield(0, [equipment, *creatures])
        .library(0, ["swamp"] * 20)
        .build()
    )
    return game


def only(game, def_id: str) -> int:
    return oids_of(game, def_id)[0]


class TestTheEffectSideSelector:
    def test_an_op_can_reach_the_equipped_creature(self, builder):
        game = board(builder, BLADE, creatures=(BEAR, DORK))
        blade, bear, dork = only(game, BLADE), only(game, BEAR), only(game, DORK)
        attach(game.state, blade, bear)

        destroy(game.state, dork)
        settle(game)

        assert game.state.objects[bear].counter(PLUS_ONE) == 1

    def test_nothing_else_gets_the_counter(self, builder):
        game = board(builder, BLADE, creatures=(BEAR, DORK))
        blade, bear, dork = only(game, BLADE), only(game, BEAR), only(game, DORK)
        attach(game.state, blade, bear)

        destroy(game.state, dork)
        settle(game)

        assert game.state.objects[blade].counter(PLUS_ONE) == 0

    def test_attached_to_nothing_finds_nothing(self, builder):
        """An unequipped Blade must not counter the whole board."""
        game = board(builder, BLADE, creatures=(BEAR, DORK))
        bear, dork = only(game, BEAR), only(game, DORK)

        destroy(game.state, dork)
        settle(game)

        assert game.state.objects[bear].counter(PLUS_ONE) == 0


class TestTheDiesTrigger:
    """The case `attached_to` alone can never answer."""

    def test_it_fires_when_the_equipped_creature_dies(self, builder):
        game = board(builder, CLAMP)
        clamp, bear = only(game, CLAMP), only(game, BEAR)
        attach(game.state, clamp, bear)
        hand = len(game.state.players[0].hand)

        destroy(game.state, bear)
        settle(game)

        assert len(game.state.players[0].hand) == hand + 2

    def test_it_does_not_fire_for_a_creature_it_was_not_on(self, builder):
        game = board(builder, CLAMP, creatures=(BEAR, DORK))
        clamp, bear, dork = only(game, CLAMP), only(game, BEAR), only(game, DORK)
        attach(game.state, clamp, bear)
        hand = len(game.state.players[0].hand)

        destroy(game.state, dork)
        settle(game)

        assert len(game.state.players[0].hand) == hand

    def test_it_does_not_fire_while_unequipped(self, builder):
        game = board(builder, CLAMP)
        bear = only(game, BEAR)
        hand = len(game.state.players[0].hand)

        destroy(game.state, bear)
        settle(game)

        assert len(game.state.players[0].hand) == hand


class TestTheRememberedAttachment:
    def test_detaching_records_what_it_was_on(self, builder):
        game = board(builder, CLAMP)
        clamp, bear = only(game, CLAMP), only(game, BEAR)
        attach(game.state, clamp, bear)

        destroy(game.state, bear)

        assert game.state.objects[clamp].attached_to is None
        assert game.state.objects[clamp].last_attached_to == bear

    def test_reattaching_clears_it(self, builder):
        """An Equipment moved on must not still answer for the creature it left."""
        game = board(builder, CLAMP, creatures=(BEAR, DORK))
        clamp, bear, dork = only(game, CLAMP), only(game, BEAR), only(game, DORK)
        attach(game.state, clamp, bear)
        destroy(game.state, bear)
        settle(game)

        attach(game.state, clamp, dork)
        assert game.state.objects[clamp].last_attached_to is None

    def test_the_equipment_leaving_clears_it_too(self, builder):
        game = board(builder, CLAMP)
        clamp, bear = only(game, CLAMP), only(game, BEAR)
        attach(game.state, clamp, bear)
        destroy(game.state, bear)
        settle(game)

        destroy(game.state, clamp)
        assert game.state.objects[clamp].zone is Zone.GRAVEYARD
        assert game.state.objects[clamp].last_attached_to is None
