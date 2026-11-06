"""`equipped` -- "the number of equipped creatures you control".

    "Whenever Barret Wallace attacks, it deals damage equal to the number of
    equipped creatures you control to defending player."  -- Barret Wallace

A permanent is equipped when one or more Equipment is attached to it (301.5c),
and the word names no controller: an Equipment an opponent moved onto your
creature still equips it. `enchanted_by` is the same question asked of Auras;
this is its Equipment twin, read from the host's end of `attached_to` by
`characteristics.is_equipped`.

What would be wrong without it:

- **`modified`** also matches a creature with a counter on it or one wearing
  your Aura, so Barret Wallace would deal damage for a +1/+1 counter.
- **Counting Equipment** (`subtypes: ["Equipment"], attached_to: {...}`) counts
  the attachments, so a creature wearing two Equipment would draw Cloud,
  Ex-SOLDIER two cards instead of one.

Witnesses: Barret Wallace and Cloud, Ex-SOLDIER (`data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches, validate_selector
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import add_counters, attach
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, two_seat_board

GEAR = "t_plain_gear"  # an Equipment with no abilities
CLOAK = "t_ah_cloak"  # an Aura
BEAR = "t_ah_bear"  # 2/2

EQUIPPED_CREATURES = {
    "count": {"zone": "battlefield", "types": ["Creature"], "controller": "you", "equipped": True}
}


def position(builder, mine=(BEAR,), theirs=()):
    game = two_seat_board(builder, list(mine), list(theirs), advance=False)
    return game, oids_of(game, BEAR, 0)[0]


def equipped(game, oid: int, want: bool = True) -> bool:
    ctx = EffectContext(state=game.state, controller=0)
    return matches(ctx, oid, {"zone": "battlefield", "equipped": want})


def how_many(game) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=0), EQUIPPED_CREATURES)


class TestWhatEquips:
    def test_a_bare_creature_is_not(self, builder):
        game, bear = position(builder)
        assert not equipped(game, bear)
        assert equipped(game, bear, want=False)

    def test_your_equipment_on_it(self, builder):
        game, bear = position(builder, [BEAR, GEAR])
        attach(game.state, oids_of(game, GEAR, 0)[0], bear)
        assert equipped(game, bear)
        assert not equipped(game, bear, want=False)

    def test_an_opponents_equipment_on_it(self, builder):
        """The word asks what is attached, not whose it is."""
        game, bear = position(builder, [BEAR], [GEAR])
        attach(game.state, oids_of(game, GEAR, 1)[0], bear)
        assert equipped(game, bear)

    def test_an_equipment_on_another_creature(self, builder):
        game = two_seat_board(builder, [BEAR, BEAR, GEAR], advance=False)
        first, second = oids_of(game, BEAR, 0)
        attach(game.state, oids_of(game, GEAR, 0)[0], second)
        assert not equipped(game, first)
        assert equipped(game, second)


class TestItIsNotModified:
    def test_an_aura_does_not_equip(self, builder):
        game, bear = position(builder, [BEAR, CLOAK])
        attach(game.state, oids_of(game, CLOAK, 0)[0], bear)
        assert not equipped(game, bear)

    def test_a_counter_does_not_equip(self, builder):
        """The `modified` near miss: a counter modifies, it does not equip."""
        game, bear = position(builder)
        add_counters(game.state, bear, PLUS_ONE, 1)
        assert not equipped(game, bear)


class TestTheWearingOff:
    def test_an_equipment_destroyed_unequips(self, builder):
        """Read live, not remembered."""
        game, bear = position(builder, [BEAR, GEAR])
        gear = oids_of(game, GEAR, 0)[0]
        attach(game.state, gear, bear)
        destroy(game.state, gear)
        assert not equipped(game, bear)

    def test_moving_the_equipment_moves_the_answer(self, builder):
        game = two_seat_board(builder, [BEAR, BEAR, GEAR], advance=False)
        first, second = oids_of(game, BEAR, 0)
        gear = oids_of(game, GEAR, 0)[0]
        attach(game.state, gear, first)
        attach(game.state, gear, second)
        assert not equipped(game, first)
        assert equipped(game, second)


class TestCountingCountsCreatures:
    def test_two_equipment_on_one_creature_is_one(self, builder):
        """Cloud draws a card per equipped creature, not per Equipment."""
        game, bear = position(builder, [BEAR, GEAR, GEAR])
        for gear in oids_of(game, GEAR, 0):
            attach(game.state, gear, bear)
        assert how_many(game) == 1

    def test_each_equipped_creature_you_control_counts(self, builder):
        game = two_seat_board(builder, [BEAR, BEAR, BEAR, GEAR, GEAR], [BEAR], advance=False)
        mine = oids_of(game, BEAR, 0)
        gears = oids_of(game, GEAR, 0)
        attach(game.state, gears[0], mine[0])
        attach(game.state, gears[1], oids_of(game, BEAR, 1)[0])
        assert how_many(game) == 1

    def test_none_equipped_is_zero(self, builder):
        game, _ = position(builder, [BEAR, GEAR])
        assert how_many(game) == 0


class TestTheLoaderRefusesANonBoolean:
    @pytest.mark.parametrize("value", ["true", {"controller": "you"}, 1])
    def test_refused(self, value):
        """A filter on the Equipment would read as `true`, quietly "anybody's"."""
        with pytest.raises(DslError, match="equipped"):
            validate_selector({"zone": "battlefield", "equipped": value}, "card")

    @pytest.mark.parametrize("value", [True, False])
    def test_a_boolean_loads(self, value):
        validate_selector({"zone": "battlefield", "equipped": value}, "card")
