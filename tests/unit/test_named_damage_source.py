""""**Target creature you control** deals damage … to each other creature."

Chandra's Ignition. Two separate claims, and the engine could make neither.

**Who deals it.** The `damage` op always attributed its damage to the resolving
spell, and the printed card says the *creature* deals it. That is not
bookkeeping: lifelink on the creature gains its controller life, deathtouch on
it kills what it hits, and "damage dealt by a source you control" reads it.
`TestTheCreatureIsTheSource` is the pair that separates the two readings — a
lifelinking source gains life, a spell source gains none.

**"Each *other* creature."** The chosen creature must not burn itself. That half
turned out to be sayable already: `snapshot` binds the target and
`exclude_binding` removes it from the pool, which is the same shape Martial
Coup's "destroy all other creatures" uses to spare the Soldiers it just made.
Worth recording, because the gap record filed it as missing.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import only_oid, pass_until

IGNITION = "t_ignition"  # the creature deals it
SPELL_SOURCE = "t_ignition_spell_source"  # the spell deals it -- the counterfactual
LINKER = "t_lifelinker"  # 2/2 lifelink
BEAR = "t_bear"  # 2/2 vanilla
BIG = "t_big_wall"  # 0/9 -- survives, so damage is readable as marks


def position(builder, spell: str):
    """A lifelinker to point at, a Bear beside it, and a wall opposite."""
    return (
        builder(players=2)
        .battlefield(0, [LINKER, BEAR] + ["mountain"] * 5)
        .battlefield(1, [BIG, "plains"])
        .library(0, ["forest"] * 10)
        .hand(0, [spell])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_at_the_linker(game, spell: str) -> None:
    game._advance()
    linker = only_oid(game, LINKER)
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == spell
        and a.targets
        and a.targets[0].id == linker
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


class TestTheCreatureIsTheSource:
    def test_its_lifelink_gains_life(self, builder):
        """The claim the whole key exists for.

        A 2/2 lifelinker deals 2 to the Bear, 2 to the wall and 2 to the
        opponent -- six damage, six life.
        """
        game = position(builder, IGNITION)
        cast_at_the_linker(game, IGNITION)

        assert game.state.players[0].life == 46

    def test_a_spell_source_gains_nothing(self, builder):
        """The counterfactual, kept as a live card.

        Identical text, identical targets, no `source_object` -- and the
        lifelink never fires, because the spell has none.
        """
        game = position(builder, SPELL_SOURCE)
        cast_at_the_linker(game, SPELL_SOURCE)

        assert game.state.players[0].life == 40


class TestEachOtherCreature:
    def test_the_chosen_creature_is_spared(self, builder):
        """"each **other** creature" -- it does not burn itself."""
        game = position(builder, IGNITION)
        linker = only_oid(game, LINKER)

        cast_at_the_linker(game, IGNITION)

        assert game.state.objects[linker].zone is Zone.BATTLEFIELD
        assert game.state.objects[linker].damage == 0

    def test_your_own_other_creature_is_not(self, builder):
        """It is "each other creature", not "each creature you don't control"."""
        game = position(builder, IGNITION)
        bear = only_oid(game, BEAR)

        cast_at_the_linker(game, IGNITION)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD, "a 2/2 takes 2"

    def test_the_opponents_creature_is_hit(self, builder):
        game = position(builder, IGNITION)
        wall = only_oid(game, BIG, 1)

        cast_at_the_linker(game, IGNITION)

        assert game.state.objects[wall].damage == 2


class TestEachOpponent:
    def test_the_opponent_takes_it_and_you_do_not(self, builder):
        game = position(builder, IGNITION)

        cast_at_the_linker(game, IGNITION)

        assert game.state.players[1].life == 38
