"""A static ability whose ``affects`` is a union of whole filters.

    "Skeletons you control and other Zombies you control get +1/+1 and have
     deathtouch."                                            -- Death Baron

Rule 611.3a applies a static's effect to every object it describes, and an
object either is described or is not: a creature that is both a Skeleton and a
Zombie is one object the sentence names, and gets +1/+1 once. Every other key in
`STATIC_FILTER_KEYS` is ANDed, so one filter could say only "Skeleton Zombies",
and the two near misses are both wrong cards:

* two statics -- "Skeletons" and "other Zombies" -- pump a Skeleton Zombie
  twice. Changelings, which are every type, make that the ordinary case in a
  Zombie deck rather than a curiosity;
* one static with ``subtypes: ["Skeleton", "Zombie"]`` cannot put the "other"
  on the Zombie half alone: with `exclude_self` the Baron would stop pumping a
  Baron that is also a Skeleton, and without it the Baron pumps itself.

``any_of`` is matched by `characteristics._matches_wherever`, each branch as the
outer filter plus the branch's keys, so `exclude_self` belongs to its branch.
`t_sfu_bone_lord` is the witness that it does: the same printed line on a
Skeleton Zombie, which the Skeleton branch reaches and the Zombie branch does
not, so it pumps itself -- once.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import keywords, oids_of, only_oid, pt, static_probe, two_seat_board

BARON = "t_sfu_baron"  # Zombie Wizard 2/2: Skeletons and other Zombies +1/+1, deathtouch
BONE_LORD = "t_sfu_bone_lord"  # the same line on a Skeleton Zombie 2/2
SKELETON = "t_sfu_skeleton"  # 1/1
ZOMBIE = "t_sfu_zombie"  # 1/1
BOTH = "t_sfu_skeleton_zombie"  # 1/1, printed Skeleton Zombie -- a changeling's case
GOBLIN = "t_sfu_goblin"  # 1/1

UNION = {
    "types": ["Creature"],
    "any_of": [{"subtypes": ["Skeleton"]}, {"subtypes": ["Zombie"], "exclude_self": True}],
}


def board(builder, mine=(), theirs=()):
    """``(game, oid)`` -- the board, and the id of the lord that leads ``mine``."""
    game = two_seat_board(builder, mine, theirs)
    return game, only_oid(game, mine[0], 0)


def creature(game, card_id: str, pid: int = 0) -> int:
    return only_oid(game, card_id, pid)


class TestEachBranchIsDescribed:
    def test_a_skeleton_you_control_is_pumped(self, builder):
        game, _ = board(builder, [BARON, SKELETON])
        oid = creature(game, SKELETON)
        assert pt(game, oid) == (2, 2)
        assert "deathtouch" in keywords(game, oid)

    def test_another_zombie_you_control_is_pumped(self, builder):
        game, _ = board(builder, [BARON, ZOMBIE])
        oid = creature(game, ZOMBIE)
        assert pt(game, oid) == (2, 2)
        assert "deathtouch" in keywords(game, oid)

    def test_a_creature_in_neither_branch_is_not(self, builder):
        game, _ = board(builder, [BARON, GOBLIN])
        oid = creature(game, GOBLIN)
        assert pt(game, oid) == (1, 1)
        assert "deathtouch" not in keywords(game, oid)

    def test_the_outer_controller_default_still_applies(self, builder):
        """"…you control", on both halves: an opponent's Skeleton and Zombie
        are described by neither branch."""
        game, _ = board(builder, [BARON], [SKELETON, ZOMBIE])
        for card_id in (SKELETON, ZOMBIE):
            oid = creature(game, card_id, 1)
            assert pt(game, oid) == (1, 1)
            assert "deathtouch" not in keywords(game, oid)


class TestTheUnionIsNotATally:
    def test_a_skeleton_zombie_gets_plus_one_once(self, builder):
        """The whole card: two statics would make this a 3/3."""
        game, _ = board(builder, [BARON, BOTH])
        oid = creature(game, BOTH)
        assert pt(game, oid) == (2, 2)
        assert "deathtouch" in keywords(game, oid)

    def test_two_barons_pump_each_other_once_each(self, builder):
        """Each Baron is "another Zombie" to the other, so each is a 3/3; a
        Skeleton Zombie under both is pumped once by each, not twice by each."""
        game = two_seat_board(builder, [BARON, BARON, BOTH])
        for oid in oids_of(game, BARON, 0):
            assert pt(game, oid) == (3, 3)
        assert pt(game, creature(game, BOTH)) == (3, 3)


class TestExcludeSelfIsScopedToItsBranch:
    def test_the_baron_is_not_another_zombie(self, builder):
        """A Zombie and not a Skeleton, so only the "other" branch could reach
        it, and that branch excludes it."""
        game, oid = board(builder, [BARON])
        assert pt(game, oid) == (2, 2)
        assert "deathtouch" not in keywords(game, oid)

    def test_a_skeleton_source_is_one_of_the_skeletons(self, builder):
        """"Skeletons you control" has no "other": the Skeleton branch reaches
        the source even though the Zombie branch refuses it -- and once."""
        game, oid = board(builder, [BONE_LORD])
        assert pt(game, oid) == (3, 3)
        assert "deathtouch" in keywords(game, oid)


class TestItWearsOff:
    def test_the_pump_leaves_with_the_baron(self, builder):
        game, baron = board(builder, [BARON, BOTH])
        oid = creature(game, BOTH)
        assert pt(game, oid) == (2, 2)
        move_object(game.state, baron, Zone.GRAVEYARD)
        assert pt(game, oid) == (1, 1)
        assert "deathtouch" not in keywords(game, oid)


class TestTheLoaderRefuses:
    @staticmethod
    def _compile(affects):
        return compile_card(
            CardModel.model_validate(
                static_probe(
                    {
                        "effect": "buff",
                        "affects": affects,
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                    }
                )
            )
        )

    def test_the_union_loads(self):
        self._compile(UNION)

    def test_a_union_of_one(self):
        with pytest.raises(DslError, match="at least two"):
            self._compile({"any_of": [{"subtypes": ["Skeleton"]}]})

    def test_a_branch_that_repeats_an_outer_key(self):
        """It would replace the outer `types` rather than narrow it, and stop
        requiring a creature."""
        with pytest.raises(DslError, match="already appear on the outer filter"):
            self._compile(
                {"types": ["Creature"], "any_of": [{"types": ["Artifact"]}, {"subtypes": ["Zombie"]}]}
            )

    def test_a_key_the_static_language_does_not_have_inside_a_branch(self):
        with pytest.raises(DslError, match="unsupported keys"):
            self._compile({"any_of": [{"subtypes": ["Skeleton"]}, {"zone": "graveyard"}]})

    def test_a_malformed_comparison_inside_a_branch(self):
        with pytest.raises(DslError, match="power"):
            self._compile({"any_of": [{"subtypes": ["Skeleton"]}, {"power": ">=4"}]})

    def test_an_empty_branch(self):
        """`{}` would match every creature you control and widen the union to
        all of them."""
        with pytest.raises(DslError, match="non-empty"):
            self._compile({"any_of": [{"subtypes": ["Skeleton"]}, {}]})

    def test_any_of_is_affects_only(self):
        """`blockers` is read by its own callers; the word stays out of it."""
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "block_restriction",
                            "affects": {"self_only": True},
                            "blockers": {
                                "any_of": [{"subtypes": ["Wall"]}, {"types": ["Artifact"]}]
                            },
                        }
                    )
                )
            )
