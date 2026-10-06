"""Shroud (702.18a), which is one rule and is not hexproof with a wider net.

    "This permanent or player can't be the target of spells or abilities."

Hexproof stops *opponents*. Shroud stops **everyone**, and the half that only
shroud has is the half that is easy to lose: your own creature becomes
untargetable by your own spells. Simic Sky Swallower shipped for years as a
plain 6/6 flying trampler precisely because writing that line as `hexproof`
makes a strictly better card — one its controller can still pump, blink or
equip by targeting — and nothing on screen would look wrong.

So every test here is paired. Whatever shroud refuses, hexproof on the same
board must still allow, or the two keywords have quietly become one.

The other direction matters as much. Shroud is read by `can_be_targeted` and by
nothing else: it says nothing about damage, blocking, or effects that do not
target. `protection` is the trap on that side — four rules read it, so a shroud
routed through `protected_from` would also make the creature undamageable and
unblockable. Nimble Mongoose and Simic Sky Swallower are the witnesses.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars, protected_from
from automtg.engine.enums import ActionKind, Keyword
from automtg.engine.primitives import damage_permanent
from automtg.engine.targeting import can_be_targeted
from tests.conftest import only_oid


def board(builder, *, mine: str, theirs: str = "grizzly_bears", spell: str = "t_pump_spell"):
    """``(game, mine_oid, theirs_oid)`` — one creature each, and a spell in hand.

    Six lands so anything in this file is castable, and player 0 holds the
    spell in every case: the question is always what *player 0* may target.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + ["island"] * 3 + [mine])
        .battlefield(1, [theirs])
        .hand(0, [spell])
        .build()
    )
    return game, only_oid(game, mine), only_oid(game, theirs, 1)


def targets_offered(game, spell_id: str) -> list[int]:
    """Every oid the spell in hand is actually offered as a target."""
    out: list[int] = []
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST:
            continue
        if game.state.objects[action.source].def_id != spell_id:
            continue
        out.extend(ref.id for ref in action.targets if ref.kind == "object")
    return out


class TestShroudStopsTheControllerToo:
    """The whole difference from hexproof, and the reason the card was unwritable."""

    def test_you_cannot_target_your_own_shrouded_creature(self, builder):
        game, mine, _ = board(builder, mine="t_shrouded")
        assert not can_be_targeted(game.state, 0, mine)
        assert mine not in targets_offered(game, "t_pump_spell"), (
            "your own pump spell is being offered a shrouded creature"
        )

    def test_hexproof_on_the_same_board_still_lets_you_target_it(self, builder):
        """The pair. Without this, shroud passing proves nothing about shroud."""
        game, mine, _ = board(builder, mine="t_hexproof")
        assert can_be_targeted(game.state, 0, mine)
        assert mine in targets_offered(game, "t_pump_spell")

    def test_an_opponent_cannot_target_it_either(self, builder):
        game, mine, _ = board(builder, mine="t_shrouded")
        assert not can_be_targeted(game.state, 1, mine)

    def test_an_unshrouded_creature_on_the_same_board_is_still_offered(self, builder):
        """Shroud is a property of the object, not of the spell."""
        game, mine, theirs = board(builder, mine="t_shrouded")
        offered = targets_offered(game, "t_pump_spell")
        assert theirs in offered
        assert mine not in offered


class TestItIsOnlyTheTargetRule:
    """Shroud is not protection. Four rules read protection; one reads this."""

    def test_it_does_not_prevent_damage(self, builder):
        """A shrouded creature still takes damage and still dies to it.

        Routed through `protected_from` it would take none, which is how a 6/6
        flier turns into an unkillable one.
        """
        game, mine, theirs = board(builder, mine="t_shrouded")
        damage_permanent(game.state, mine, 2, theirs)
        assert game.state.objects[mine].damage == 2

    def test_it_is_not_reachable_through_the_protection_path(self, builder):
        """The one assertion that covers damage, blocking and enchant/equip at
        once: all three ask `protected_from`, and shroud must not answer it."""
        game, mine, theirs = board(builder, mine="t_shrouded")
        assert not protected_from(game.state, mine, theirs)
        assert not protected_from(game.state, mine, None)

    def test_an_effect_that_does_not_target_still_reaches_it(self, builder):
        """"Creatures you control get +1/+1" is not a target, so it applies."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["t_shrouded", "t_anthem"])
            .build()
        )
        shrouded = only_oid(game, "t_shrouded")
        assert chars(game.state, shrouded).power == 3, "the anthem did not reach it"


class TestWhereItApplies:
    def test_a_card_outside_the_battlefield_is_still_targetable(self, builder):
        """`can_be_targeted` short-circuits off the battlefield, and must keep
        doing so: a shrouded creature in a graveyard is a normal card that
        raise-dead can name."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3)
            .graveyard(0, ["t_shrouded"])
            .build()
        )
        (shrouded,) = game.state.players[0].graveyard
        assert game.state.objects[shrouded].def_id == "t_shrouded"
        assert can_be_targeted(game.state, 0, shrouded)

    def test_granted_shroud_is_read_from_the_characteristic_layer(self, builder):
        """`grant_keyword` carries the whole "equipped creature has shroud"
        family for free, so the check must read `chars`, not the printed card."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["island"] * 3)
            .battlefield(0, ["grizzly_bears", "t_shroud_granter"])
            .hand(0, ["t_pump_spell"])
            .build()
        )
        bear = only_oid(game, "grizzly_bears")
        assert Keyword.SHROUD.value in chars(game.state, bear).keywords
        assert not can_be_targeted(game.state, 0, bear)
        assert bear not in targets_offered(game, "t_pump_spell")

    def test_without_the_granter_the_same_bear_is_targetable(self, builder):
        game, bear, _ = board(builder, mine="grizzly_bears", theirs="t_bear")
        assert can_be_targeted(game.state, 0, bear)
