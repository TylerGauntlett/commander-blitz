"""Damage prevented at the cost of a counter -- one prevention, not a prevention and a trigger.

    "If this creature would be dealt damage, prevent that damage and remove a
     +1/+1 counter from it."                            -- Unbreathing Horde

A `prevent_damage` total shield (``prevent_all``) carrying ``remove_counters``.
615.1 makes the whole sentence one prevention effect: the damage is never dealt
and the counter comes off **inside the same event**, so nothing goes on the
stack. Its rulings pin the two numbers: **one** counter however much damage is
prevented, and the damage is prevented even with no counter to remove.

**Why not the shield plus a `damage_prevented` trigger.** The near miss: the
counter would come off later, on the stack, where it can be responded to, and
the trigger would be a second ability the card never printed. **Why not Panther
Habit's ``counter``.** That puts "that many" on, the other direction and the
other number. **Why not plain `prevent_all`.** A Horde that never shrinks is a
strictly better card.

**The order against everything else is 616.1's.** The damaged creature's
controller orders the replacements, and losing a +1/+1 counter only hurts, so
they apply every shield that costs nothing first -- a total shield, a shield
counter, the Habit -- and this one only to damage that would otherwise land.
Combat damage is one event (510.2), so two blockers cost one counter. Under
"damage can't be prevented" 615.12 still applies it: the damage is dealt and
the counter still comes off.

Witness: Unbreathing Horde (Innistrad).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import damage_removes_counters
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE, SHIELD
from commanderblitz.engine.primitives import attach, damage_permanent
from tests.conftest import only_oid, pt, two_seat_board

HORDE = "t_pr_horde"  # 0/0 Zombie with the shield
STURDY = "t_pr_sturdy"  # the same shield on a 1/1
OGRE = "t_pc_ogre"  # red 3/3, a damage source
HABIT = "t_pc_habit"  # Panther Habit: prevent and put that many +1/+1 counters
BLANKET = "t_blanket_shield"  # prevent all damage to creatures you control
TORMENT = "t_no_prevention"  # Everlasting Torment: damage can't be prevented


def position(builder, counters=3, horde=HORDE, mine=(), theirs=(OGRE,)):
    game = two_seat_board(builder, mine=[horde, *mine], theirs=list(theirs), advance=False)
    oid = only_oid(game, horde)
    if counters:
        game.state.objects[oid].add_counter(PLUS_ONE, counters)
        game.state.bump_chars()
    return game, oid


def plus(game, oid: int) -> int:
    return game.state.objects[oid].counter(PLUS_ONE)


def events_since(game, mark: int, kind: str):
    return [e for e in game.state.events[mark:] if e.type == kind]


class TestOneCounterPerHit:
    def test_three_damage_costs_one_counter_and_marks_nothing(self, builder):
        game, horde = position(builder)
        dealt = damage_permanent(game.state, horde, 3, only_oid(game, OGRE))
        assert dealt == 0
        assert game.state.objects[horde].damage == 0
        assert plus(game, horde) == 2
        assert pt(game, horde) == (2, 2)

    def test_a_huge_hit_still_costs_exactly_one(self, builder):
        """"Only one +1/+1 counter will be removed, no matter how much damage
        is prevented." """
        game, horde = position(builder)
        damage_permanent(game.state, horde, 50, None)
        assert plus(game, horde) == 2
        assert game.state.objects[horde].damage == 0

    def test_each_separate_hit_costs_another(self, builder):
        game, horde = position(builder)
        for amount in (1, 2):
            damage_permanent(game.state, horde, amount, None)
        assert plus(game, horde) == 1

    def test_combat_damage_alike(self, builder):
        """"Would be dealt damage" names no kind, so a combat hit counts too."""
        game, horde = position(builder)
        damage_permanent(game.state, horde, 2, only_oid(game, OGRE), is_combat=True, batch=7)
        assert plus(game, horde) == 2


class TestWithNoCounterToRemove:
    def test_the_damage_is_still_prevented(self, builder):
        """The ruling: with no +1/+1 counter on it (toughness kept above 0 some
        other way), damage is still prevented and nothing is removed."""
        game, sturdy = position(builder, counters=0, horde=STURDY)
        mark = len(game.state.events)
        assert damage_permanent(game.state, sturdy, 4, only_oid(game, OGRE)) == 0
        assert game.state.objects[sturdy].damage == 0
        assert plus(game, sturdy) == 0
        assert events_since(game, mark, "counter_removed") == []
        assert events_since(game, mark, "damage_dealt") == []

    def test_the_last_counter_off_a_zero_zero_is_lethal(self, builder):
        """The cost is real: a 0/0 Horde on its last counter is prevented from
        the damage and dies to state-based actions as a 0/0."""
        game, horde = position(builder, counters=1)
        damage_permanent(game.state, horde, 1, None)
        assert plus(game, horde) == 0
        assert pt(game, horde) == (0, 0)


class TestItIsOneEvent:
    def test_a_prevention_event_and_a_removal_and_nothing_dealt(self, builder):
        game, horde = position(builder)
        mark = len(game.state.events)
        damage_permanent(game.state, horde, 3, only_oid(game, OGRE))
        prevented = events_since(game, mark, "damage_prevented")
        assert [(e.data["amount"], e.data["reason"]) for e in prevented] == [
            (3, "prevent_remove_counters")
        ]
        assert events_since(game, mark, "damage_dealt") == []
        removed = events_since(game, mark, "counter_removed")
        assert [(e.data["counter"], e.data["amount"]) for e in removed] == [(PLUS_ONE, 1)]

    def test_nothing_waits_on_the_stack(self, builder):
        game, horde = position(builder)
        damage_permanent(game.state, horde, 3, None)
        assert plus(game, horde) == 2
        assert not game.state.stack
        assert not game.state.pending_triggers

    def test_two_blows_in_one_combat_event_cost_one_counter(self, builder):
        """510.2: combat damage is one simultaneous event, so two blockers'
        assignments in the same step's batch are one replaced event."""
        game, horde = position(builder)
        for _ in range(2):
            damage_permanent(game.state, horde, 3, None, is_combat=True, batch=11)
        assert plus(game, horde) == 2
        damage_permanent(game.state, horde, 3, None, is_combat=True, batch=12)
        assert plus(game, horde) == 1


class TestOnlyItself:
    def test_another_creature_takes_its_damage(self, builder):
        game, _horde = position(builder)
        ogre = only_oid(game, OGRE)
        assert damage_removes_counters(game.state, ogre) is None
        assert damage_permanent(game.state, ogre, 2, None) == 2


class TestTheOrderIsTheControllers:
    """616.1: the damaged creature's controller orders the replacements, and
    applies every shield that costs no +1/+1 counter first."""

    def test_after_a_total_shield(self, builder):
        game, horde = position(builder, mine=(BLANKET,))
        mark = len(game.state.events)
        damage_permanent(game.state, horde, 3, None)
        assert plus(game, horde) == 3
        prevented = events_since(game, mark, "damage_prevented")
        assert [e.data["reason"] for e in prevented] == ["prevent_all"]

    def test_after_a_shield_counter(self, builder):
        game, horde = position(builder)
        game.state.objects[horde].add_counter(SHIELD, 1)
        damage_permanent(game.state, horde, 3, None)
        assert game.state.objects[horde].counter(SHIELD) == 0
        assert plus(game, horde) == 3
        damage_permanent(game.state, horde, 3, None)
        assert plus(game, horde) == 2

    def test_after_panther_habit(self, builder):
        """The Habit turns the damage into counters; with no damage left the
        Horde's shield has nothing to replace."""
        game, horde = position(builder, mine=(HABIT,))
        assert attach(game.state, only_oid(game, HABIT), horde)
        game.state.bump_chars()
        damage_permanent(game.state, horde, 2, None)
        assert plus(game, horde) == 5


class TestDamageThatCantBePrevented:
    def test_the_damage_lands_and_the_counter_still_comes_off(self, builder):
        """615.12: the prevention prevents nothing, but its additional effect
        still happens."""
        game, horde = position(builder, mine=(TORMENT,))
        mark = len(game.state.events)
        assert damage_permanent(game.state, horde, 1, None) == 1
        assert game.state.objects[horde].damage == 1
        assert plus(game, horde) == 2
        assert events_since(game, mark, "damage_prevented") == []

    def test_once_per_combat_event_there_too(self, builder):
        game, horde = position(builder, mine=(TORMENT,))
        for _ in range(2):
            damage_permanent(game.state, horde, 1, None, is_combat=True, batch=5)
        assert plus(game, horde) == 2
        assert game.state.objects[horde].damage == 2


class TestTheLoaderGuard:
    def _card(self, **static) -> CardModel:
        base = {"kind": "static", "effect": "prevent_damage", "affects": {"self_only": True}}
        base.update(static)
        return CardModel.model_validate(
            {
                "id": "t_pr_probe",
                "name": "Horde Probe",
                "mana_cost": "{2}{B}",
                "types": ["Creature"],
                "power": 0,
                "toughness": 0,
                "abilities": [base],
            }
        )

    def test_the_horde_loads(self):
        compile_card(self._card(prevent_all=True, remove_counters={"counter": "+1/+1"}))

    def test_absorb_with_a_removal_is_refused(self):
        with pytest.raises(DslError, match="only with 'prevent_all'"):
            compile_card(
                self._card(amount={"const": 2}, remove_counters={"counter": "+1/+1"})
            )

    def test_beside_that_many_is_refused(self):
        with pytest.raises(DslError, match="not both"):
            compile_card(
                self._card(
                    prevent_all=True, counter="+1/+1", remove_counters={"counter": "+1/+1"}
                )
            )

    def test_another_kind_is_refused(self):
        """The ordering above is the controller's only when the removal hurts."""
        with pytest.raises(DslError, match="only '\\+1/\\+1'"):
            compile_card(self._card(prevent_all=True, remove_counters={"counter": "-1/-1"}))

    @pytest.mark.parametrize("amount", [0, -1, "that_many", {"const": 1}])
    def test_a_non_fixed_amount_is_refused(self, amount):
        with pytest.raises(DslError, match="whole number"):
            compile_card(
                self._card(
                    prevent_all=True, remove_counters={"counter": "+1/+1", "amount": amount}
                )
            )

    def test_an_unknown_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(
                self._card(
                    prevent_all=True, remove_counters={"counter": "+1/+1", "of": "self"}
                )
            )

    def test_on_another_static_is_refused(self):
        with pytest.raises(DslError, match="read only by the 'prevent_damage' static"):
            compile_card(
                self._card(effect="cant_block", remove_counters={"counter": "+1/+1"})
            )
