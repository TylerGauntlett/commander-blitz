""""Whenever this Equipment becomes unattached from a permanent, sacrifice that
permanent" -- the `becomes_unattached` trigger.

Rule 701.3a's other half. An attachment *becomes unattached* from a permanent
every way it can come off one, and Grafted Wargear -- the witness, beside
Grafted Exoskeleton, Stitcher's Graft and Captain's Hook -- is a drawback only
if every one of them is heard:

- **Equipped onto another creature.** The commonest, and the one a
  `leaves_battlefield` trigger, the near miss, can never see: nothing left.
- **Unattached by an effect** (the `unattach` op, 701.3d).
- **The host leaving the battlefield.** The trigger fires, and "that
  permanent" is gone, so the sacrifice does nothing.
- **The attachment itself leaving.** Destroying the Wargear still costs the
  creature: the ability looks back at the Equipment as it left (603.10a).

Every route is one event through `primitives.fire_unattached`, fired once, after
the field is cleared, naming the host as ``{"binding": "host"}``. A host and an
attachment that leave together are one unattachment, not two.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Zone
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import count_on_battlefield, only_oid, settle_completely

WARGEAR = "t_bu_wargear"  # Equip {0}; unattached -> sacrifice that permanent
HOOK = "t_bu_hook"  # unattached -> destroy that permanent
BEAR = "t_ba_bear"
HOUND = "t_ba_hound"  # "whenever an Equipment becomes attached to this creature"


def board(builder, mine, theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .build(advance=False)
    )


def settle(game) -> None:
    game._advance()
    settle_completely(game)


def equipped(builder, gear=WARGEAR, mine=(BEAR,)):
    game = board(builder, [gear, *mine])
    gear_oid, bear = only_oid(game, gear), only_oid(game, BEAR)
    attach(game.state, gear_oid, bear)
    settle(game)
    return game, gear_oid, bear


def on_battlefield(game, oid: int) -> bool:
    return oid in game.state.battlefield


class TestStayingAttached:
    def test_becoming_attached_is_not_becoming_unattached(self, builder):
        game, gear, bear = equipped(builder)
        assert on_battlefield(game, bear)
        assert game.state.objects[gear].attached_to == bear

    def test_re_attaching_to_the_same_creature_does_nothing(self, builder):
        """701.3b: no move, so nothing came off."""
        game, gear, bear = equipped(builder)
        attach(game.state, gear, bear)
        settle(game)
        assert on_battlefield(game, bear)


class TestEveryWayOff:
    def test_equipping_another_creature_costs_the_first(self, builder):
        game, gear, bear = equipped(builder, mine=(BEAR, HOUND))
        hound = only_oid(game, HOUND)
        attach(game.state, gear, hound)
        settle(game)
        assert not on_battlefield(game, bear), "the creature it came off"
        assert on_battlefield(game, hound), "not the one it went to"
        assert game.state.objects[gear].attached_to == hound

    def test_the_unattach_op_costs_it(self, builder):
        from commanderblitz.engine.effects.context import EffectContext
        from commanderblitz.engine.effects.ops_counters import op_unattach

        game, gear, bear = equipped(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=gear)
        gen = op_unattach(ctx, {"op": "unattach", "objects": {"self_only": True}})
        if gen is not None:
            for _ in gen:
                pass
        settle(game)
        assert game.state.objects[gear].attached_to is None
        assert not on_battlefield(game, bear)

    def test_destroying_the_equipment_still_costs_the_creature(self, builder):
        """603.10a: the Wargear sees its own departure."""
        game, gear, bear = equipped(builder)
        destroy(game.state, gear)
        settle(game)
        assert game.state.objects[gear].zone is Zone.GRAVEYARD
        assert not on_battlefield(game, bear)

    def test_the_host_leaving_fires_and_does_nothing_more(self, builder):
        game, gear, bear = equipped(builder, mine=(BEAR, HOUND))
        hound = only_oid(game, HOUND)
        before = len(game.state.events)
        move_object(game.state, bear, Zone.HAND)
        settle(game)
        fired = [
            e
            for e in game.state.events[before:]
            if e.type == "unattached" and e.source == gear
        ]
        assert len(fired) == 1 and fired[0].data["host"] == bear
        assert game.state.objects[bear].zone is Zone.HAND
        assert on_battlefield(game, gear) and on_battlefield(game, hound)

    def test_a_host_and_equipment_leaving_together_is_one_unattachment(self, builder):
        game, gear, bear = equipped(builder)
        before = len(game.state.events)
        destroy(game.state, bear)
        destroy(game.state, gear)
        settle(game)
        fired = [e for e in game.state.events[before:] if e.type == "unattached"]
        assert len(fired) == 1


class TestThatPermanent:
    def test_destroy_that_permanent_reads_the_same_host(self, builder):
        """Captain's Hook: the host binding, under a different verb."""
        game, hook, bear = equipped(builder, gear=HOOK, mine=(BEAR, HOUND))
        attach(game.state, hook, only_oid(game, HOUND))
        settle(game)
        assert not on_battlefield(game, bear)
        assert count_on_battlefield(game, HOUND, 0) == 1

    def test_you_cannot_sacrifice_what_you_do_not_control(self, builder):
        """701.17a: an Equipment of yours on an opponent's creature comes off,
        and "sacrifice that permanent" asks you to sacrifice it -- which you
        cannot. Destroy (the Hook) has no such limit."""
        game = board(builder, [WARGEAR, HOOK], theirs=[BEAR])
        gear, hook, bear = only_oid(game, WARGEAR), only_oid(game, HOOK), only_oid(game, BEAR, 1)
        attach(game.state, gear, bear)
        settle(game)
        destroy(game.state, gear)
        settle(game)
        assert on_battlefield(game, bear)
        attach(game.state, hook, bear)
        settle(game)
        destroy(game.state, hook)
        settle(game)
        assert not on_battlefield(game, bear)
