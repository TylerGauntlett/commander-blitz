"""Flanking (702.25) -- a keyword whose whole content is a rules-supplied trigger.

    "Flanking (Whenever a creature without flanking blocks this creature, the
    blocking creature gets -1/-1 until end of turn.)"
                                        -- Sidar Kondo of Jamuraa

    "All Sliver creatures have flanking."   -- Sidewinder Sliver

Exalted's shape: `Keyword.FLANKING`, whose trigger `carddef.FLANKING_TRIGGER`
`triggers._candidate_abilities` yields for every battlefield permanent whose
derived keywords include it. It has to be a `Keyword` twice over. The trigger's
own exemption, "a creature **without flanking**", reads the word on the
*blocker*, so without a keyword to read the trigger cannot be written at all;
and Sidewinder Sliver, Agility and Jabari's Banner grant it, so a trigger
printed on the card would not reach the creatures they hand it to.

The rules points, each with a test:

- a blocker without flanking gets -1/-1 until end of turn, and only the
  creatures blocking *this* attacker;
- a blocker with flanking is exempt, and if every blocker has it nothing
  triggers;
- a granted flanking triggers, and a creature that loses its abilities does not;
- a blocker the -1/-1 kills dies before combat damage.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Keyword, Zone
from commanderblitz.engine.structs import TargetRef
from tests.conftest import (
    _default_answer,
    attack_with,
    find_action,
    keywords,
    oids_of,
    only_oid,
    pass_until,
    pt,
)

FLANKER = "t_fk_flanker"  # 2/2, flanking
SLIVER = "t_fk_sliver"  # 2/2 Sliver, "All Sliver creatures have flanking."
SLIVER_BEAR = "t_fk_sliver_bear"  # 2/2 Sliver, no abilities
BEAR = "t_bear"  # 2/2, no abilities
WALL = "t_wall"  # a defender, to block with
ONE_ONE = "t_fk_squire"  # 1/1, no abilities -- dies to the -1/-1
BLANKER = "t_fk_blanker"  # "Creatures your opponents control lose all abilities."


def to(game, kind: DecisionKind) -> None:
    pass_until(game, lambda g: g.pending() and g.pending().kind is kind)


def done(game) -> None:
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def settle(game, limit: int = 40) -> None:
    """Resolve what the block queued without leaving the turn: the -1/-1 is
    until end of turn, so an assertion after the rollover reads a wiped board."""
    turn = game.state.turn
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        assert game.state.turn == turn, "the turn rolled over before the assertion"
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the block triggers never resolved")


def combat(builder, mine, theirs, blocks):
    """Seat 0's ``mine`` attack, seat 1's ``theirs`` block as ``blocks`` says.

    ``blocks`` maps (blocker id, index among seat 1's) to (attacker id, index
    among seat 0's). Returns the game with the block triggers resolved, still in
    the turn of the declaration.
    """
    game = (
        builder(players=2)
        .hand(0, ["t_bolt"])
        .battlefield(0, ["mountain", *mine])
        .battlefield(1, list(theirs))
        .build()
    )
    attackers = {(cid, i): oid for cid in set(mine) for i, oid in enumerate(oids_of(game, cid, 0))}
    to(game, DecisionKind.DECLARE_ATTACKERS)
    for oid in attackers.values():
        attack_with(game, oid)
    done(game)
    to(game, DecisionKind.DECLARE_BLOCKERS)
    for (bid, bi), (aid, ai) in blocks.items():
        blocker = oids_of(game, bid, 1)[bi]
        game.apply(
            find_action(
                game,
                ActionKind.ADD_BLOCKER,
                source=blocker,
                targets=(TargetRef.obj(attackers[(aid, ai)]),),
            )
        )
    done(game)
    settle(game)
    return game


class TestTheBlockerShrinks:
    def test_a_blocker_without_flanking_gets_minus_one(self, builder):
        game = combat(builder, [FLANKER], [WALL], {(WALL, 0): (FLANKER, 0)})
        wall = only_oid(game, WALL, 1)
        base = game.state.card_of(game.state.objects[wall])
        assert pt(game, wall) == (base.power - 1, base.toughness - 1)

    def test_every_blocker_without_flanking_shrinks(self, builder):
        game = combat(
            builder, [FLANKER], [WALL, WALL], {(WALL, 0): (FLANKER, 0), (WALL, 1): (FLANKER, 0)}
        )
        for wall in oids_of(game, WALL, 1):
            base = game.state.card_of(game.state.objects[wall])
            assert pt(game, wall) == (base.power - 1, base.toughness - 1)

    def test_the_attacker_is_untouched(self, builder):
        game = combat(builder, [FLANKER], [WALL], {(WALL, 0): (FLANKER, 0)})
        assert pt(game, only_oid(game, FLANKER, 0)) == (2, 2)

    def test_a_creature_blocking_somebody_else_does_not_shrink(self, builder):
        game = combat(
            builder, [FLANKER, BEAR], [WALL, BEAR],
            {(WALL, 0): (FLANKER, 0), (BEAR, 0): (BEAR, 0)},
        )
        assert pt(game, only_oid(game, BEAR, 1)) == (2, 2)

    def test_a_vanilla_attacker_shrinks_nobody(self, builder):
        """The control: the -1/-1 is flanking's and nothing else's."""
        game = combat(builder, [BEAR], [WALL], {(WALL, 0): (BEAR, 0)})
        wall = only_oid(game, WALL, 1)
        base = game.state.card_of(game.state.objects[wall])
        assert pt(game, wall) == (base.power, base.toughness)

    def test_a_blocker_it_kills_dies_before_damage(self, builder):
        """704.5f looks as soon as the trigger resolves, still in declare blockers."""
        game = combat(builder, [FLANKER], [ONE_ONE], {(ONE_ONE, 0): (FLANKER, 0)})
        (squire,) = [o for o in game.state.objects.values() if o.def_id == ONE_ONE]
        assert squire.zone is Zone.GRAVEYARD
        assert game.state.objects[only_oid(game, FLANKER, 0)].damage == 0


class TestTheExemption:
    def test_a_blocker_with_flanking_does_not_shrink(self, builder):
        game = combat(builder, [FLANKER], [FLANKER], {(FLANKER, 0): (FLANKER, 0)})
        assert pt(game, only_oid(game, FLANKER, 1)) == (2, 2)

    def test_nothing_triggers_when_every_blocker_has_it(self, builder):
        """"Whenever a creature *without flanking* blocks" -- no such creature,
        no trigger, not a trigger that resolves into nothing."""
        game = (
            builder(players=2)
            .hand(0, ["t_bolt"])
            .battlefield(0, ["mountain", FLANKER])
            .battlefield(1, [FLANKER])
            .build()
        )
        mine, theirs = only_oid(game, FLANKER, 0), only_oid(game, FLANKER, 1)
        to(game, DecisionKind.DECLARE_ATTACKERS)
        attack_with(game, mine)
        done(game)
        to(game, DecisionKind.DECLARE_BLOCKERS)
        game.apply(
            find_action(game, ActionKind.ADD_BLOCKER, source=theirs, targets=(TargetRef.obj(mine),))
        )
        done(game)
        assert not game.state.pending_triggers and not game.state.stack

    def test_only_the_blockers_without_it_shrink(self, builder):
        game = combat(
            builder, [FLANKER], [FLANKER, WALL],
            {(FLANKER, 0): (FLANKER, 0), (WALL, 0): (FLANKER, 0)},
        )
        wall = only_oid(game, WALL, 1)
        base = game.state.card_of(game.state.objects[wall])
        assert pt(game, only_oid(game, FLANKER, 1)) == (2, 2)
        assert pt(game, wall) == (base.power - 1, base.toughness - 1)


class TestGrantedFlanking:
    def test_a_granted_flanking_triggers(self, builder):
        game = combat(
            builder, [SLIVER, SLIVER_BEAR], [WALL], {(WALL, 0): (SLIVER_BEAR, 0)}
        )
        bear = only_oid(game, SLIVER_BEAR, 0)
        assert Keyword.FLANKING.value in keywords(game, bear)
        wall = only_oid(game, WALL, 1)
        base = game.state.card_of(game.state.objects[wall])
        assert pt(game, wall) == (base.power - 1, base.toughness - 1)

    def test_a_granted_flanking_exempts_the_blocker(self, builder):
        """The exemption reads derived keywords, so a granted flanking on the
        blocker counts exactly as a printed one does."""
        game = combat(
            builder, [FLANKER], [SLIVER, SLIVER_BEAR], {(SLIVER_BEAR, 0): (FLANKER, 0)}
        )
        assert pt(game, only_oid(game, SLIVER_BEAR, 1)) == (2, 2)

    def test_losing_its_abilities_stops_it(self, builder):
        game = combat(builder, [FLANKER], [BLANKER, WALL], {(WALL, 0): (FLANKER, 0)})
        flanker = only_oid(game, FLANKER, 0)
        assert Keyword.FLANKING.value not in keywords(game, flanker)
        wall = only_oid(game, WALL, 1)
        base = game.state.card_of(game.state.objects[wall])
        assert pt(game, wall) == (base.power, base.toughness)
