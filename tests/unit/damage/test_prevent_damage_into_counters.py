"""Damage turned into counters -- one replacement, not a prevention and a trigger.

    "If equipped creature would be dealt damage, prevent that damage and put
     that many +1/+1 counters on it."                       -- Panther Habit

A `prevent_damage` total shield (``prevent_all``) carrying a ``counter`` kind.
615.1 makes the whole sentence one prevention effect: the damage is never dealt
and the counters arrive **inside the same event**, so nothing goes on the stack
and there is no window between the two halves.

**Why not the shield plus a `damage_prevented` trigger.** That is the near miss,
and it is wrong three ways: the counters would arrive late -- after state-based
actions, so a lethal hit with damage already marked elsewhere would still kill --
they would be respondable, and the trigger would be a second ability the card
never printed. **Why not plain `prevent_all`.** It prevents the damage and then
does nothing with the amount, which is a strictly worse card.

**The order against everything else is 616.1's.** The damaged creature's
controller orders the replacements, and the loader allows only +1/+1 counters,
so the order they would choose is always the one that turns the most damage into
counters: this shield ahead of protection (which would prevent the same damage
and leave no counters) and a doubling applied *before* it.

Witness: Panther Habit (the Wakanda Forever precon).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import damage_into_counters
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import attach, damage_permanent
from tests.conftest import only_oid, pt, two_seat_board

HABIT = "t_pc_habit"  # Panther Habit
BEAR = "t_pc_bear"  # 2/2 to wear it
WARDED = "t_pc_warded"  # 2/2 with protection from red
OGRE = "t_pc_ogre"  # red 3/3, the damage source
FURNACE = "t_rd_furnace"  # Furnace of Rath: any damage doubled
SCALES = "t_rc_scales"  # Hardened Scales: +1/+1 counters plus one


def equip(game, creature: str) -> int:
    target = only_oid(game, creature)
    assert attach(game.state, only_oid(game, HABIT), target)
    game.state.bump_chars()
    return target


def position(builder, mine=(HABIT, BEAR), wearer=BEAR, theirs=(OGRE,)):
    game = two_seat_board(builder, mine=list(mine), theirs=list(theirs), advance=False)
    return game, equip(game, wearer)


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counter(PLUS_ONE)


def events_since(game, mark: int, kind: str):
    return [e for e in game.state.events[mark:] if e.type == kind]


class TestTheDamageBecomesCounters:
    def test_three_damage_is_three_counters_and_no_damage(self, builder):
        game, bear = position(builder)
        dealt = damage_permanent(game.state, bear, 3, only_oid(game, OGRE))
        assert dealt == 0
        assert game.state.objects[bear].damage == 0
        assert counters(game, bear) == 3
        assert pt(game, bear) == (5, 5)

    def test_a_lethal_hit_leaves_a_bigger_creature(self, builder):
        """The counters land in the replaced event itself, so there is never a
        moment where the bear has lethal damage marked."""
        game, bear = position(builder)
        damage_permanent(game.state, bear, 10, None)
        assert game.state.objects[bear].damage == 0
        assert pt(game, bear) == (12, 12)

    def test_every_hit_is_replaced_again(self, builder):
        game, bear = position(builder)
        for amount in (1, 2, 3):
            damage_permanent(game.state, bear, amount, None)
        assert counters(game, bear) == 6

    def test_noncombat_and_combat_damage_alike(self, builder):
        """"Would be dealt damage" names no kind, so a combat hit counts too."""
        game, bear = position(builder)
        damage_permanent(game.state, bear, 2, only_oid(game, OGRE), is_combat=True)
        assert counters(game, bear) == 2


class TestItIsOneEvent:
    def test_a_prevention_event_carries_the_amount_and_nothing_is_dealt(self, builder):
        game, bear = position(builder)
        mark = len(game.state.events)
        damage_permanent(game.state, bear, 3, only_oid(game, OGRE))
        prevented = events_since(game, mark, "damage_prevented")
        assert [(e.data["amount"], e.data["reason"]) for e in prevented] == [
            (3, "prevent_into_counters")
        ]
        assert events_since(game, mark, "damage_dealt") == []
        placed = events_since(game, mark, "counter_placed")
        assert [(e.data["counter"], e.data["amount"]) for e in placed] == [(PLUS_ONE, 3)]

    def test_nothing_waits_on_the_stack(self, builder):
        """No trigger: the counters are already there and nothing is pending."""
        game, bear = position(builder)
        damage_permanent(game.state, bear, 3, None)
        assert counters(game, bear) == 3
        assert not game.state.stack
        assert not game.state.pending_triggers


class TestOnlyTheEquippedCreature:
    def test_an_unattached_habit_shields_nobody(self, builder):
        game = two_seat_board(builder, mine=[HABIT, BEAR], theirs=[OGRE], advance=False)
        bear = only_oid(game, BEAR)
        assert damage_into_counters(game.state, bear) is None
        assert damage_permanent(game.state, bear, 1, None) == 1
        assert counters(game, bear) == 0

    def test_another_creature_takes_its_damage(self, builder):
        game, _bear = position(builder)
        ogre = only_oid(game, OGRE)
        assert damage_permanent(game.state, ogre, 2, None) == 2
        assert counters(game, ogre) == 0


class TestTheOrderIsTheControllers:
    """616.1: the damaged creature's controller orders the replacements."""

    def test_ahead_of_protection(self, builder):
        """Protection from red would prevent the ogre's damage and leave
        nothing; the controller applies the habit first and keeps the counters."""
        game, warded = position(builder, mine=(HABIT, WARDED), wearer=WARDED)
        damage_permanent(game.state, warded, 3, only_oid(game, OGRE))
        assert counters(game, warded) == 3
        assert game.state.objects[warded].damage == 0

    def test_after_a_doubling(self, builder):
        """Furnace of Rath first, then the habit: six counters, not three."""
        game, bear = position(builder, theirs=(OGRE, FURNACE))
        damage_permanent(game.state, bear, 3, only_oid(game, OGRE))
        assert counters(game, bear) == 6
        assert game.state.objects[bear].damage == 0

    def test_counter_replacements_still_apply(self, builder):
        """Putting the counters is an ordinary placement, so Hardened Scales
        adds its one."""
        game, bear = position(builder, mine=(HABIT, BEAR, SCALES))
        damage_permanent(game.state, bear, 3, None)
        assert counters(game, bear) == 4


class TestTheLoaderGuard:
    def _card(self, **static) -> CardModel:
        base = {"kind": "static", "effect": "prevent_damage", "affects": {"attached": True}}
        base.update(static)
        return CardModel.model_validate(
            {
                "id": "t_pc_probe",
                "name": "Habit Probe",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "subtypes": ["Equipment"],
                "abilities": [base],
            }
        )

    def test_the_habit_loads(self):
        compile_card(self._card(prevent_all=True, counter="+1/+1"))

    def test_absorb_with_counters_is_refused(self):
        """"That many" of a partial prevention is no printed sentence."""
        with pytest.raises(DslError, match="only with 'prevent_all'"):
            compile_card(self._card(amount={"const": 2}, counter="+1/+1"))

    def test_another_kind_is_refused(self):
        """The ordering above is the controller's choice only when the counters
        help them; a -1/-1 version would want the opposite order."""
        with pytest.raises(DslError, match="only '\\+1/\\+1'"):
            compile_card(self._card(prevent_all=True, counter="-1/-1"))
