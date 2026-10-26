"""Rule-modifying statics read the creature as it now is, layers and all.

Graaz, Unstoppable Juggernaut -- "Juggernauts you control attack each combat if
able. / Juggernauts you control can't be blocked by Walls. / Other creatures you
control have base power and toughness 5/3 and are Juggernauts in addition to
their other creature types." The third line is two layered statics (613.1d for
the type, 613.4b for the base size); the first two are not layered at all. An
attack requirement (508.1d) and a block restriction (509.1b) modify the rules of
combat rather than any object's characteristics, so they apply to whatever the
layer system has produced -- including the Juggernauts the third line made.

The static filter language deliberately reads printed characteristics, because a
*layered* static that read another's output would need 613.8 dependency order
the fixed pipeline does not have. That reason does not reach these two: neither
is applied by the pipeline, so reading its output is no loop. Without
`derived` reading, Graaz's first two lines bind Graaz alone, and the card's whole
point -- an army of compelled, Wall-proof 5/3s -- silently does not happen.

The blocker side is the same argument: "can't be blocked by Walls" asks what the
blocker is now, so a creature some static makes a Wall is a Wall.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.combat import attack_required, can_block
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.player_statics import attack_compelled
from tests.conftest import attack_with, find_action, only_oid, pass_until, pt

LORD = "t_juggernaut_lord"
WALL = "t_derived_wall"
WALL_MAKER = "t_wall_maker"


def untap_board(builder, own, opponent=()):
    return (
        builder(players=2)
        .battlefield(0, list(own))
        .battlefield(1, list(opponent))
        .active(0)
        .step(Step.UNTAP)
        .build(advance=False)
    )


def blocking_board(builder, blockers):
    """``(game, lord, bear)`` with both attacking player 1, at declare blockers."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 8 + [LORD, "t_bear"])
        .battlefield(1, list(blockers))
        .build()
    )
    lord, bear = only_oid(game, LORD, 0), only_oid(game, "t_bear", 0)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, lord)
    attack_with(game, bear)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, lord, bear


class TestTheThirdLine:
    def test_other_creatures_are_5_3_juggernauts(self, builder):
        game = untap_board(builder, [LORD, "t_bear"])
        bear = only_oid(game, "t_bear")
        assert pt(game, bear) == (5, 3)
        assert {"Bear", "Juggernaut"} <= chars(game.state, bear).subtypes

    def test_the_lord_keeps_its_own_size(self, builder):
        game = untap_board(builder, [LORD])
        assert pt(game, only_oid(game, LORD)) == (7, 5)

    def test_an_opponents_creature_is_untouched(self, builder):
        game = untap_board(builder, [LORD], ["t_bear"])
        assert pt(game, only_oid(game, "t_bear")) == (2, 2)


class TestTheAttackRequirement:
    def test_a_creature_made_a_juggernaut_must_attack(self, builder):
        """The derived read: the bear is a Juggernaut only by the third line."""
        game = untap_board(builder, [LORD, "t_bear"])
        bear = only_oid(game, "t_bear")
        assert attack_compelled(game.state, bear)
        assert attack_required(game.state, bear)

    def test_the_printed_juggernaut_must_attack_too(self, builder):
        game = untap_board(builder, [LORD])
        assert attack_required(game.state, only_oid(game, LORD))

    def test_without_the_lord_nothing_is_compelled(self, builder):
        game = untap_board(builder, ["t_bear"])
        assert not attack_compelled(game.state, only_oid(game, "t_bear"))

    def test_an_opponents_creature_is_not_compelled(self, builder):
        game = untap_board(builder, [LORD], ["t_bear"])
        assert not attack_compelled(game.state, only_oid(game, "t_bear"))


class TestTheBlockRestriction:
    def test_a_printed_wall_cannot_block_a_made_juggernaut(self, builder):
        game, lord, bear = blocking_board(builder, [WALL])
        wall = only_oid(game, WALL, 1)
        assert not can_block(game.state, wall, bear, 1)
        assert not can_block(game.state, wall, lord, 1)

    def test_a_non_wall_still_blocks(self, builder):
        """The pair: without it, "can't be blocked" passes the test above."""
        game, lord, bear = blocking_board(builder, ["t_bear"])
        theirs = only_oid(game, "t_bear", 1)
        assert can_block(game.state, theirs, bear, 1)
        assert can_block(game.state, theirs, lord, 1)

    def test_a_creature_made_a_wall_is_a_wall(self, builder):
        """The blockers filter reads derived subtypes as well."""
        game, lord, bear = blocking_board(builder, [WALL_MAKER, "t_bear"])
        theirs = only_oid(game, "t_bear", 1)
        assert not can_block(game.state, theirs, bear, 1)
        assert not can_block(game.state, theirs, lord, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _, _ = blocking_board(builder, [WALL])
        wall = only_oid(game, WALL, 1)
        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source == wall
        ]
        assert not offered
