"""``any_types`` — "target artifact **or** enchantment" (rule 115.4).

`types` is a conjunction: `matches` tests `set(want).issubset(types)`, so
`["Artifact", "Enchantment"]` selects a permanent that is *both at once*, which
in practice is nothing. Every way of faking the disjunction makes a different
card, and all three have been tried in gap records:

- `{"types": ["Artifact"]}` alone silently drops half the printed clause.
- `{"not_types": [...everything else...]}` is the complement only for permanents
  with a single type — it refuses artifact creatures and enchantment creatures,
  which the printed line accepts.
- two optional target specs destroys *up to two* permanents, not one.

The any-of form already existed for `subtypes` and `colors`; this is the type
equivalent. Wickerbough Elder is the witness in the shipped pool, and
`docs/decks.md` names Mortify and Bedevil as substitutions that exist only
because the selector language had no union.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches, validate_selector
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid

ARTIFACT_OR_ENCHANTMENT = {
    "zone": "battlefield",
    "any_types": ["Artifact", "Enchantment"],
}


def board(builder):
    """One of each shape the disjunction has to rule on.

    `t_anthem` is the enchantment, `sol_ring` the artifact, `grizzly_bears` a
    creature that is neither, and `forest` a land — the negative cases matter as
    much as the positive ones, or the clause has become "target permanent".
    """
    return (
        builder(players=2)
        .battlefield(0, ["forest", "sol_ring", "t_anthem", "grizzly_bears"])
        .build()
    )


def selects(game, oid: int, selector: dict) -> bool:
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    return matches(ctx, oid, selector)


class TestItIsAnyOfNotAllOf:
    def test_an_artifact_matches(self, builder):
        game = board(builder)
        assert selects(game, only_oid(game, "sol_ring"), ARTIFACT_OR_ENCHANTMENT)

    def test_an_enchantment_matches(self, builder):
        game = board(builder)
        assert selects(game, only_oid(game, "t_anthem"), ARTIFACT_OR_ENCHANTMENT)

    def test_the_conjunction_would_match_neither(self, builder):
        """The bug this key exists to fix, asserted directly.

        Without it the only spelling available is `types`, and `types` selects
        a permanent that is an artifact *and* an enchantment — so the card
        destroys nothing at all on this board.
        """
        game = board(builder)
        both = {"zone": "battlefield", "types": ["Artifact", "Enchantment"]}
        assert not selects(game, only_oid(game, "sol_ring"), both)
        assert not selects(game, only_oid(game, "t_anthem"), both)


class TestWhatItStillRefuses:
    def test_a_plain_creature_does_not_match(self, builder):
        game = board(builder)
        assert not selects(game, only_oid(game, "grizzly_bears"), ARTIFACT_OR_ENCHANTMENT)

    def test_a_land_does_not_match(self, builder):
        game = board(builder)
        assert not selects(game, only_oid(game, "forest"), ARTIFACT_OR_ENCHANTMENT)

    def test_an_artifact_creature_matches_where_not_types_would_refuse_it(self, builder):
        """The reason `not_types` is not a substitute.

        Solemn Simulacrum is an Artifact Creature. It is a legal target for
        "destroy target artifact or enchantment", and the complement spelling
        `{"not_types": ["Creature", "Land", ...]}` would exclude it.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "solemn_simulacrum"])
            .build()
        )
        solemn = only_oid(game, "solemn_simulacrum")
        assert selects(game, solemn, ARTIFACT_OR_ENCHANTMENT)
        complement = {
            "zone": "battlefield",
            "not_types": ["Creature", "Land", "Planeswalker"],
        }
        assert not selects(game, solemn, complement), (
            "if this ever passes, not_types became a valid substitute and this "
            "test is no longer making its point"
        )


class TestLoadTimeGuards:
    def test_a_misspelled_type_is_a_load_error(self):
        """It would narrow the selector silently, which is the whole hazard:
        "artifact or enchantmnet" quietly becomes "artifact"."""
        with pytest.raises(DslError, match="unknown card type"):
            validate_selector({"any_types": ["Artifact", "Enchantmnet"]}, "somewhere")

    def test_the_same_guard_covers_the_older_type_keys(self):
        with pytest.raises(DslError, match="unknown card type"):
            validate_selector({"types": ["Creatur"]}, "somewhere")
        with pytest.raises(DslError, match="unknown card type"):
            validate_selector({"not_types": ["Lnad"]}, "somewhere")

    def test_one_type_is_refused_because_types_already_says_it(self):
        """Two spellings of the same filter is how they drift apart."""
        with pytest.raises(DslError, match="at least two types"):
            validate_selector({"any_types": ["Artifact"]}, "somewhere")

    def test_a_valid_disjunction_loads(self):
        validate_selector(ARTIFACT_OR_ENCHANTMENT, "somewhere")
