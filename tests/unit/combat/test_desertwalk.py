"""Desertwalk: landwalk over a nonbasic land type.

    Hazezon, Shaper of Sand — "Desertwalk (This creature can't be blocked as
    long as defending player controls a Desert.)"

Rule 702.14a lets landwalk name *any* land type, and 702.14c makes it an evasion
that holds while the **defending player** controls a land of that type. Desert is
a nonbasic land type (205.3i), and nothing about the rule changes with that: the
blocker's controller's board is asked for a land with the subtype, read from
`chars`, exactly as for islandwalk. So desertwalk is one more
`LANDWALK_SUBTYPE` row.

The near miss is a static, and it is wrong in the way multiplayer exposes. A
`block_restriction`'s `blockers` filter reads only the would-be blocker, and a
static `exists` condition can only ask whether *any* opponent controls a Desert
-- which would make the creature unblockable at a table where somebody else has
one. `TestTheDefendingPlayerOnly` is that case. A land that is not a Desert
does nothing, and neither does the attacker's own Desert (`TestTheLandType`).
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.enums import (
    EVASION_KEYWORDS,
    LANDWALK_SUBTYPE,
    ActionKind,
    DecisionKind,
    Keyword,
)
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until


def in_combat(builder, seats: list[list[str]], defender: int = 1, mine: tuple = ()):
    """``(game, attacker_oid)``: seat 0's desertwalker attacks ``defender``.

    ``seats`` are the boards of seats 1, 2, ...; ``mine`` adds to seat 0's.
    """
    b = builder(players=len(seats) + 1).battlefield(
        0, ["forest"] * 4 + list(mine) + ["t_desertwalker"]
    )
    for pid, board in enumerate(seats, start=1):
        b = b.battlefield(pid, board)
    game = b.build()
    attacker = only_oid(game, "t_desertwalker")
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(
            game,
            ActionKind.ADD_ATTACKER,
            source=attacker,
            targets=(TargetRef.player(defender),),
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, attacker


class TestTheKeyword:
    def test_it_is_a_landwalk_over_desert(self):
        assert LANDWALK_SUBTYPE[Keyword.DESERTWALK.value] == "Desert"
        assert Keyword.DESERTWALK in EVASION_KEYWORDS

    def test_the_card_carries_it(self, builder):
        game = builder(players=2).battlefield(0, ["t_desertwalker"]).build()
        oid = only_oid(game, "t_desertwalker")
        assert "desertwalk" in chars(game.state, oid).keywords


class TestTheLandType:
    def test_it_cannot_be_blocked_while_the_defender_controls_a_desert(self, builder):
        game, attacker = in_combat(builder, [["t_bear", "painted_bluffs"]])
        bear = only_oid(game, "t_bear", 1)
        assert not can_block(game.state, bear, attacker, 1)

    def test_without_a_desert_it_blocks_normally(self, builder):
        """The pair: a land, even a nonbasic one, is not a Desert."""
        game, attacker = in_combat(builder, [["t_bear", "mountain"]])
        bear = only_oid(game, "t_bear", 1)
        assert can_block(game.state, bear, attacker, 1)

    def test_the_attackers_own_desert_does_not_count(self, builder):
        game, attacker = in_combat(
            builder, [["t_bear", "mountain"]], mine=("painted_bluffs",)
        )
        bear = only_oid(game, "t_bear", 1)
        assert can_block(game.state, bear, attacker, 1)


class TestTheDefendingPlayerOnly:
    def test_another_opponents_desert_does_not_make_it_unblockable(self, builder):
        """Three seats: the Desert is seat 2's, the attack is at seat 1. An
        'any opponent controls a Desert' static would refuse this block."""
        game, attacker = in_combat(
            builder, [["t_bear", "mountain"], ["painted_bluffs"]], defender=1
        )
        bear = only_oid(game, "t_bear", 1)
        assert can_block(game.state, bear, attacker, 1)

    def test_when_it_attacks_the_desert_holder_it_is_unblockable(self, builder):
        game, attacker = in_combat(
            builder, [["mountain"], ["t_bear", "painted_bluffs"]], defender=2
        )
        bear = only_oid(game, "t_bear", 2)
        assert not can_block(game.state, bear, attacker, 2)
