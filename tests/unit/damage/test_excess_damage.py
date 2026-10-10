""""Excess damage is dealt to that creature's controller instead."

Gandalf's Sanction. One damage event split in two — the creature is dealt
exactly lethal and the remainder goes to a player — rather than two events, and
the difference is visible: two events would let a damage-triggered ability fire
twice and would let the second half be prevented on its own.

The engine had no way to say it. `damage` took one target set and one amount,
nothing exposed how much damage a permanent had already marked, so a
hand-rolled `if`/`minus` would both mis-compute and produce the wrong number of
events. `trample` spills for the same reason but only in combat, and
`prevent_damage` suppresses without redirecting.

Lethal is read here the way `sba` reads it — toughness minus damage already
marked, or 1 from a deathtouch source — because if the two disagree this leaves
a creature one point short of the death the rules say it took.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.primitives import damage_permanent
from tests.conftest import only_oid, pass_until

SPILLS = "t_excess_five"  # 5 damage to target creature, excess to its controller
PLAIN = "t_plain_five"  # the same 5 damage with no spill -- the control
BEAR = "t_bear"  # a 2/2
BIG = "t_big_wall"  # a 0/9 -- too big for 5 damage to spill past


def position(builder, spell: str, *, defender_board=(BEAR,)):
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"])
        .battlefield(1, [*defender_board, "plains"])
        .library(0, ["forest"] * 10)
        .hand(0, [spell])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast_at(game, card_id: str, victim: int):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and a.targets
        and a.targets[0].id == victim
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


class TestTheSpill:
    def test_a_two_toughness_creature_sends_three_at_its_controller(self, builder):
        """5 into a 2/2: two is lethal, three spills. 40 - 3 = 37."""
        game = position(builder, SPILLS)
        bear = only_oid(game, BEAR, 1)

        cast_at(game, SPILLS, bear)

        assert game.state.players[1].life == 37
        assert game.state.players[0].life == 40, "the caster is untouched"

    def test_without_the_clause_nothing_spills(self, builder):
        """The control. The same 5 into the same 2/2 and the player is at 40."""
        game = position(builder, PLAIN)
        bear = only_oid(game, BEAR, 1)

        cast_at(game, PLAIN, bear)

        assert game.state.players[1].life == 40

    def test_the_creature_still_dies(self, builder):
        """Only lethal is dealt, so the creature must still be destroyed by it."""
        from commanderblitz.engine.enums import Zone

        game = position(builder, SPILLS)
        bear = only_oid(game, BEAR, 1)

        cast_at(game, SPILLS, bear)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD


class TestDamageAlreadyMarkedCounts:
    def test_a_wounded_creature_spills_more(self, builder):
        """Lethal is what is *left*, so a creature already at 1 damage spills 4.

        This is the half a naive "amount minus toughness" would get wrong, and
        it is why lethal is read the way state-based actions read it.
        """
        game = position(builder, SPILLS)
        bear = only_oid(game, BEAR, 1)
        damage_permanent(game.state, bear, 1, None)

        cast_at(game, SPILLS, bear)

        assert game.state.players[1].life == 36, "one lethal left, four spilled"


class TestNothingToSpill:
    def test_a_creature_bigger_than_the_damage_takes_it_all(self, builder):
        """A 0/9 eats all five, so nothing reaches its controller and it lives."""
        from commanderblitz.engine.enums import Zone

        game = position(builder, SPILLS, defender_board=(BIG,))
        wall = only_oid(game, BIG, 1)

        cast_at(game, SPILLS, wall)

        assert game.state.players[1].life == 40, "no excess, nothing spilled"
        assert game.state.objects[wall].zone is Zone.BATTLEFIELD
        assert game.state.objects[wall].damage == 5, "all five marked on the creature"
