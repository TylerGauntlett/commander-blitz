""""Modified" -- a counter on it, equipped, or enchanted by an Aura you control.

    "Auras, Equipment, and modified creatures you control gain hexproof until
    end of turn."                                                  -- Silkguard

The keyword-action definition is one word standing for three unrelated
relationships, which is why it is one selector key and not three clauses: the
selector language is a conjunction, so a card spelling it out would need an "or"
the language does not have.

Each limb is read from a different direction, and the third is the one that is
easy to get wrong:

- **a counter of any kind.** Not just +1/+1 -- the reminder says "counters".
- **equipped, by anybody's Equipment.** An Equipment an opponent moved onto your
  creature still modifies it; the definition asks what is attached, not who owns
  it.
- **enchanted by an Aura *you control*.** This limb does ask, and it is the one
  asymmetry: an opponent's Pacifism does not make your creature modified.

The lookup walks the battlefield rather than reading a list off the creature,
because attachment is stored one way -- `attached_to`, on the Aura or Equipment
-- and nothing walks back along it. Same fact `attached_to_host` is built on,
read from the other end.
"""

from __future__ import annotations

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import matches
from automtg.engine.objects import PLUS_ONE
from automtg.engine.primitives import add_counters, attach
from tests.conftest import oids_of, two_seat_board

GEAR = "t_plain_gear"  # an Equipment with no abilities
CLOAK = "t_ah_cloak"  # an Aura
BEAR = "t_ah_bear"  # 2/2, unmodified

MODIFIED = {"zone": "battlefield", "types": ["Creature"], "modified": True}


def is_modified(game, oid: int, *, controller: int = 0) -> bool:
    ctx = EffectContext(state=game.state, controller=controller)
    return matches(ctx, oid, MODIFIED)


class TestAnUntouchedCreatureIsNot:
    def test_a_bare_creature(self, builder):
        game = two_seat_board(builder, [BEAR], advance=False)
        assert not is_modified(game, oids_of(game, BEAR, 0)[0])

    def test_an_equipment_lying_around_unattached(self, builder):
        """The Equipment is on the battlefield but on nobody."""
        game = two_seat_board(builder, [BEAR, GEAR], advance=False)
        assert not is_modified(game, oids_of(game, BEAR, 0)[0])

    def test_an_equipment_on_a_different_creature(self, builder):
        game = two_seat_board(builder, [BEAR, BEAR, GEAR], advance=False)
        first, second = oids_of(game, BEAR, 0)
        attach(game.state, oids_of(game, GEAR, 0)[0], second)
        assert not is_modified(game, first)


class TestACounterModifies:
    def test_a_plus_one_counter(self, builder):
        game = two_seat_board(builder, [BEAR], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        add_counters(game.state, bear, PLUS_ONE, 1)
        assert is_modified(game, bear)

    def test_any_counter_at_all(self, builder):
        """"Counters" is the printed word, so a stun counter counts too."""
        game = two_seat_board(builder, [BEAR], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        add_counters(game.state, bear, "stun", 1)
        assert is_modified(game, bear)

    def test_a_counter_removed_again_unmodifies(self, builder):
        """The wearing-off. Read live, not remembered."""
        game = two_seat_board(builder, [BEAR], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        add_counters(game.state, bear, PLUS_ONE, 1)
        add_counters(game.state, bear, PLUS_ONE, -1)
        assert not is_modified(game, bear)


class TestEquipmentModifies:
    def test_your_equipment_on_your_creature(self, builder):
        game = two_seat_board(builder, [BEAR, GEAR], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, oids_of(game, GEAR, 0)[0], bear)
        assert is_modified(game, bear)

    def test_an_opponents_equipment_still_modifies(self, builder):
        """The definition asks what is attached, not who controls it.

        The Aura limb is the one that asks about control, and asserting this
        keeps the two apart rather than letting one rule stand in for both.
        """
        game = two_seat_board(builder, [BEAR], [GEAR], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, oids_of(game, GEAR, 1)[0], bear)
        assert is_modified(game, bear)


class TestOnlyYourAuraModifies:
    def test_your_aura_on_your_creature(self, builder):
        game = two_seat_board(builder, [BEAR, CLOAK], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, oids_of(game, CLOAK, 0)[0], bear)
        assert is_modified(game, bear)

    def test_an_opponents_aura_does_not(self, builder):
        """The asymmetry, and the whole reason this limb is not "enchanted".

        An opponent's Pacifism on your creature is not a modification, and a
        card written without the control clause would hand hexproof to exactly
        the creature the opponent was trying to answer.
        """
        game = two_seat_board(builder, [BEAR], [CLOAK], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, oids_of(game, CLOAK, 1)[0], bear)
        assert not is_modified(game, bear)

    def test_it_is_the_effects_controller_who_counts(self, builder):
        """"You" is whoever the sentence belongs to.

        The same board, asked on behalf of the other player, answers the other
        way -- which is what makes the clause about control rather than about
        the board.
        """
        game = two_seat_board(builder, [BEAR], [CLOAK], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, oids_of(game, CLOAK, 1)[0], bear)
        assert not is_modified(game, bear, controller=0)
        assert is_modified(game, bear, controller=1)
