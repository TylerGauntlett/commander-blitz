"""Stormtide Leviathan: the two halves of a lock on the whole table.

    "Islandwalk. All lands are Islands in addition to their other types.
    Creatures without flying or islandwalk can't attack."

Two capabilities, and the card only works because they compose — which is also
what makes it worth one test file rather than two.

**Landwalk** is the first evasion whose condition is not a quality of either
creature: it asks what the *defending player's board* contains. `can_block` knew
flying, reach and protection, all of which read the two creatures involved, so
there was nowhere to put it and no `blockers` filter could express it.

Five keywords rather than one parameterised ability, because `Keyword` is a bare
string and the whole content of the quality is *which* land type.

**`cant_attack`** is a global prohibition, and it is the one static whose filter
routinely names creatures its own controller does not control — so its `affects`
carries an explicit `controller: "any"`, and `not_keywords` had to exist on the
static side at all, which it did not.

The interaction is the card. Line two makes every land an Island, so line one
turns on against everybody, and line three then reads "without flying or
islandwalk" — which is why landwalk had to be a real keyword rather than a
static: nothing else could be *filtered on*.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.combat import can_attack, can_block
from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.conftest import find_action, only_oid, pass_until


def to_attackers(game):
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )


def in_combat(builder, mine: list[str], theirs: list[str], their_lands: list[str]):
    """``(game, attacker_oid)`` with the attack declared and blockers pending."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8 + mine)
        .battlefield(1, theirs + their_lands)
        .build()
    )
    attacker = only_oid(game, mine[-1])
    to_attackers(game)
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=attacker)
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, attacker


class TestLandwalk:
    def test_it_cannot_be_blocked_while_they_control_the_land_type(self, builder):
        game, attacker = in_combat(
            builder, ["t_islandwalker"], ["t_bear"], ["island"]
        )
        bear = only_oid(game, "t_bear", 1)
        assert not can_block(game.state, bear, attacker, 1)

    def test_without_that_land_it_blocks_normally(self, builder):
        """The pair. Landwalk is a condition on their board, not unblockability."""
        game, attacker = in_combat(
            builder, ["t_islandwalker"], ["t_bear"], ["forest"]
        )
        bear = only_oid(game, "t_bear", 1)
        assert can_block(game.state, bear, attacker, 1)

    def test_a_creature_without_it_is_blocked_either_way(self, builder):
        game, attacker = in_combat(builder, ["t_trampler"], ["t_bear"], ["island"])
        bear = only_oid(game, "t_bear", 1)
        assert can_block(game.state, bear, attacker, 1)


class TestTheLandsBecomeIslands:
    def test_every_land_gains_the_subtype(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_tide_lock"])
            .battlefield(1, ["mountain"])
            .build()
        )
        theirs = only_oid(game, "mountain", 1)
        c = chars(game.state, theirs)
        assert "Island" in c.subtypes
        assert "Mountain" in c.subtypes, "it is 'in addition to', not a replacement"

    def test_which_is_what_turns_the_islandwalk_on(self, builder):
        """The two lines compose: without line two, islandwalk does nothing
        against a player holding no Islands."""
        game, attacker = in_combat(
            builder, ["t_tide_lock", "t_islandwalker"], ["t_bear"], ["mountain"]
        )
        bear = only_oid(game, "t_bear", 1)
        assert not can_block(game.state, bear, attacker, 1)


class TestCantAttack:
    def test_a_grounded_creature_cannot_attack(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_tide_lock", "t_bear"])
            .battlefield(1, ["island"])
            .build()
        )
        bear = only_oid(game, "t_bear")
        assert not can_attack(game.state, bear)

    def test_a_flier_still_can(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_tide_lock", "t_flyer"])
            .battlefield(1, ["island"])
            .build()
        )
        assert can_attack(game.state, only_oid(game, "t_flyer"))

    def test_an_islandwalker_still_can(self, builder):
        """`not_keywords` on a static filter, which did not exist before this."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_tide_lock", "t_islandwalker"])
            .battlefield(1, ["island"])
            .build()
        )
        assert can_attack(game.state, only_oid(game, "t_islandwalker"))

    def test_it_locks_the_opponent_down_too(self, builder):
        """The only static whose filter names creatures its controller does not
        control. `controller: "any"` is the whole difference between a lock on
        the table and a drawback on yourself."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_tide_lock"])
            .battlefield(1, ["t_bear", "island"])
            .build()
        )
        assert not can_attack(game.state, only_oid(game, "t_bear", 1))

    def test_without_the_lock_everything_attacks(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 4 + ["t_bear"])
            .battlefield(1, ["island"])
            .build()
        )
        assert can_attack(game.state, only_oid(game, "t_bear"))
