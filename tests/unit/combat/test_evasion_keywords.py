"""The five evasions `can_block` could not ask, and why none of them is a static.

    Shriekmaw — "Fear."
    Guul Draz Vampire — "…has intimidate."
    Lu Bu, Master-at-Arms — "Horsemanship."
    Dauthi Voidwalker — "Shadow."
    Dryad Sophisticate — "Nonbasic landwalk."

Every one of these is a `Keyword` for the reason landwalk and skulk are: the
quality takes no parameter. "Artifact and/or black" is not an argument to fear —
it *is* fear, and there is no second card that says it differently. The one
`block_restriction` form that looks close, a `blockers` filter, is wrong twice
over:

- it is a **prohibition** ("can't be blocked by Humans") while four of these are
  **exemptions** ("can't be blocked *except* by …"), which the positive
  conjunctive filter language cannot negate; and
- it is a static filter, so it reads **printed** characteristics — the
  constraint that keeps the characteristics pipeline acyclic
  (`characteristics` module docstring). Fear and intimidate must read derived
  colors, so a land animated into a black creature blocks a fear creature and
  the printed card is not consulted at all.

Intimidate goes further still and compares the two creatures, which is the shape
skulk opened. Its boundary is the colorless case: a creature with intimidate and
no color shares a color with nothing, so *only* an artifact creature may block
it. An implementation that treated "shares a color" as "is not a different
color" would pass every other test here.

Shadow is the only one of the five that is not an attacker-side rule at all —
702.28b is "can block **or** be blocked by only creatures with shadow", so a
shadow creature may not block a normal one either. Written as a restriction hung
on the attacker it would be half a mechanic, and the half it dropped is the half
that makes Dauthi Voidwalker's controller unable to trade.

Nonbasic landwalk is 702.14 with the test inverted: a supertype the defending
player's land must *lack*. That is why it could not be a sixth
`LANDWALK_SUBTYPE` row, and why "controls eight Forests" is the case that fails
a naive "controls a land" reading.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.combat import can_block
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.primitives import animate
from automtg.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until


def board(builder, mine: list[str], theirs: list[str]):
    """``(game, attacker_oid)`` with ``mine[-1]`` attacking and blockers pending.

    The attacker is always ``mine[-1]`` so a test can stand a granter in front of
    it without moving the creature under test, and ``theirs`` is the defending
    player's whole board -- which for nonbasic landwalk is the thing being
    asked about, not scenery.
    """
    game = builder(players=2).battlefield(0, ["forest"] * 8 + mine).battlefield(1, theirs).build()
    # ``pid=0`` explicitly: half these tests put the same card on both sides --
    # horsemanship blocking horsemanship is the point of the mechanic.
    attacker = only_oid(game, mine[-1], 0)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(
            game, ActionKind.ADD_ATTACKER, source=attacker, targets=(TargetRef.player(1),)
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, attacker


def offered_blocks(game, blocker_oid: int) -> list:
    """The ADD_BLOCKER actions legality is willing to offer this creature."""
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_BLOCKER and a.source == blocker_oid
    ]


class TestFear:
    """"Except by artifact creatures and/or black creatures" -- two escapes, and
    the "and/or" means either alone is enough."""

    def test_a_black_creature_blocks(self, builder):
        game, attacker = board(builder, ["t_fearsome"], ["t_skulker"])
        blocker = only_oid(game, "t_skulker", 1)
        assert "B" in chars(game.state, blocker).colors
        assert can_block(game.state, blocker, attacker, 1)

    def test_a_colorless_artifact_creature_blocks(self, builder):
        """The other escape on its own. This blocker is colorless, so a check
        that required *both* halves would refuse it."""
        game, attacker = board(builder, ["t_fearsome"], ["t_artifact_blocker"])
        blocker = only_oid(game, "t_artifact_blocker", 1)
        assert not chars(game.state, blocker).colors
        assert can_block(game.state, blocker, attacker, 1)

    def test_a_green_creature_is_refused(self, builder):
        game, attacker = board(builder, ["t_fearsome"], ["t_bear"])
        assert not can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_a_creature_without_fear_is_blocked_by_anything(self, builder):
        """The pair for the class -- without it, a rule that refused every block
        would look identical from the refusals alone."""
        game, attacker = board(builder, ["t_bear"], ["t_bear"])
        assert can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _ = board(builder, ["t_fearsome"], ["t_bear"])
        assert not offered_blocks(game, only_oid(game, "t_bear", 1))


class TestIntimidate:
    """The same sentence as fear with "black" replaced by a *relation*."""

    def test_a_creature_sharing_the_color_blocks(self, builder):
        game, attacker = board(builder, ["t_intimidator"], ["t_menacer"])
        blocker = only_oid(game, "t_menacer", 1)
        assert chars(game.state, attacker).colors & chars(game.state, blocker).colors
        assert can_block(game.state, blocker, attacker, 1)

    def test_a_creature_of_another_color_is_refused(self, builder):
        game, attacker = board(builder, ["t_intimidator"], ["t_bear"])
        assert not can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_an_artifact_creature_blocks_regardless_of_color(self, builder):
        game, attacker = board(builder, ["t_intimidator"], ["t_artifact_blocker"])
        assert can_block(game.state, only_oid(game, "t_artifact_blocker", 1), attacker, 1)

    def test_a_colorless_intimidator_is_blocked_only_by_artifacts(self, builder):
        """The boundary, and the whole of "shares a color *with it*". Colorless
        shares a color with nothing, so every nonartifact creature is refused --
        including another colorless one. An engine that read the clause as "is
        not a different color" passes every test above and fails here."""
        game, attacker = board(
            builder, ["t_colorless_intimidator"], ["t_bear", "t_menacer", "t_artifact_blocker"]
        )
        assert not chars(game.state, attacker).colors
        assert not can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)
        assert not can_block(game.state, only_oid(game, "t_menacer", 1), attacker, 1)
        assert can_block(game.state, only_oid(game, "t_artifact_blocker", 1), attacker, 1)


class TestHorsemanship:
    def test_a_creature_without_horsemanship_is_refused(self, builder):
        game, attacker = board(builder, ["t_horseman"], ["t_bear"])
        assert not can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_a_creature_with_horsemanship_blocks(self, builder):
        game, attacker = board(builder, ["t_horseman"], ["t_horseman"])
        assert can_block(game.state, only_oid(game, "t_horseman", 1), attacker, 1)

    def test_a_horseman_may_block_anything(self, builder):
        """One-directional, unlike shadow: horsemanship restricts who may block
        the creature that has it, and never who it may block."""
        game, attacker = board(builder, ["t_bear"], ["t_horseman"])
        assert can_block(game.state, only_oid(game, "t_horseman", 1), attacker, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _ = board(builder, ["t_horseman"], ["t_bear"])
        assert not offered_blocks(game, only_oid(game, "t_bear", 1))


class TestShadowCutsBothWays:
    """702.28b is "can block or be blocked by only creatures with shadow"."""

    def test_a_creature_without_shadow_cannot_block_one_with_it(self, builder):
        game, attacker = board(builder, ["t_shadow_lurker"], ["t_bear"])
        assert not can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_a_creature_with_shadow_cannot_block_one_without_it(self, builder):
        """The other direction, and the half a `blockers` filter cannot state at
        all: the restriction lives on the *blocker* here, and nothing on the
        attacker mentions shadow."""
        game, attacker = board(builder, ["t_bear"], ["t_shadow_lurker"])
        assert not can_block(game.state, only_oid(game, "t_shadow_lurker", 1), attacker, 1)

    def test_shadow_blocks_shadow(self, builder):
        game, attacker = board(builder, ["t_shadow_lurker"], ["t_shadow_lurker"])
        assert can_block(game.state, only_oid(game, "t_shadow_lurker", 1), attacker, 1)

    def test_two_creatures_without_shadow_are_unaffected(self, builder):
        game, attacker = board(builder, ["t_bear"], ["t_bear"])
        assert can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_legality_offers_neither_refused_block(self, builder):
        game, _ = board(builder, ["t_shadow_lurker"], ["t_bear", "t_shadow_lurker"])
        assert not offered_blocks(game, only_oid(game, "t_bear", 1))
        assert offered_blocks(game, only_oid(game, "t_shadow_lurker", 1))


class TestNonbasicLandwalk:
    def test_a_nonbasic_land_on_the_defenders_board_stops_the_block(self, builder):
        game, attacker = board(builder, ["t_nonbasic_walker"], ["t_bear", "t_dual_land"])
        assert not can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_basic_lands_do_not_count(self, builder):
        """The boundary. Eight Forests are eight lands, and a reading that asked
        "controls a land" rather than "controls a *nonbasic* land" would make
        this creature unblockable against every deck in the game."""
        game, attacker = board(builder, ["t_nonbasic_walker"], ["t_bear", "forest"])
        forest = only_oid(game, "forest", 1)
        assert "Basic" in chars(game.state, forest).supertypes
        assert can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_it_is_the_defenders_board_that_matters(self, builder):
        """Not the attacker's, which is the one thing landwalk is famous for
        getting backwards. The attacking player controls the dual here."""
        game, attacker = board(builder, ["t_dual_land", "t_nonbasic_walker"], ["t_bear"])
        assert can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _ = board(builder, ["t_nonbasic_walker"], ["t_bear", "t_dual_land"])
        assert not offered_blocks(game, only_oid(game, "t_bear", 1))


class TestTheyReadDerivedCharacteristics:
    """The claim that rules out a `blockers` filter for any of the five."""

    def test_an_animated_land_blocks_a_fear_creature_once_it_is_black(self, builder):
        """A Forest is a colorless land on its printed card and cannot block a
        fear creature. Animated into a black creature it can -- which is the
        whole reason this comparison is not a static filter."""
        game, attacker = board(builder, ["t_fearsome"], ["forest"])
        land = only_oid(game, "forest", 1)
        assert not can_block(game.state, land, attacker, 1)

        animate(game.state, land, 2, 2, subtypes=["Elemental"], colors=["B"])
        c = chars(game.state, land)
        assert "Creature" in c.types and "B" in c.colors
        assert can_block(game.state, land, attacker, 1)

    def test_an_animated_land_shares_a_color_for_intimidate(self, builder):
        game, attacker = board(builder, ["t_intimidator"], ["forest"])
        land = only_oid(game, "forest", 1)
        animate(game.state, land, 2, 2, subtypes=["Elemental"], colors=["R"])
        assert can_block(game.state, land, attacker, 1)

    def test_granted_horsemanship_on_the_blocker_gives_the_block_back(self, builder):
        """`grant_keyword` reaches these because they are real keywords and not
        statics -- the landwalk argument, and the reason for choosing a keyword."""
        game, attacker = board(builder, ["t_horseman"], ["t_bear", "t_horsemanship_granter"])
        bear = only_oid(game, "t_bear", 1)
        assert "horsemanship" in chars(game.state, bear).keywords
        assert can_block(game.state, bear, attacker, 1)

    def test_granted_horsemanship_on_the_attacker_takes_the_block_away(self, builder):
        """The other side. A vanilla bear that could be blocked cannot once it
        is handed the keyword."""
        game, attacker = board(builder, ["t_horsemanship_granter", "t_bear"], ["t_bear"])
        assert "horsemanship" in chars(game.state, attacker).keywords
        assert not can_block(game.state, only_oid(game, "t_bear", 1), attacker, 1)
