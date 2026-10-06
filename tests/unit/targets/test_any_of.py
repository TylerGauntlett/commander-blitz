"""``any_of`` — a union of whole selectors, not of one key's values.

    Stumpsquall Hydra — "When this creature enters, distribute X +1/+1 counters
    among **it and any number of commanders**."

`any_types` was the same idea confined to one key, and it does not reach this:
the pool here is "this object" *or* "a commander", and neither `self_only` nor
`is_commander` is true of both. There is no clause to widen — the two halves are
different descriptions, so the union has to be across selectors.

The composition rule is what makes it usable rather than a special case: a union
narrows nothing on its own, and every key outside it still filters. So
`{"zone": "battlefield", "types": ["Creature"], "any_of": [...]}` reads as
"a creature that is either of these", not "either a creature or these".
"""

from __future__ import annotations

import pytest

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import matches, resolve_pool, validate_selector
from automtg.engine.errors import DslError
from tests.conftest import only_oid

SELF_OR_COMMANDER = [{"self_only": True}, {"is_commander": True}]


def board(builder):
    """A commander, a plain creature, and a source that is neither."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + ["t_bear", "grizzly_bears"])
        .commander(0, ["t_commander"])
        .build()
    )
    return game


def ctx_for(game, source_oid: int) -> EffectContext:
    return EffectContext(state=game.state, controller=0, source_oid=source_oid)


class TestTheUnionItself:
    def test_the_source_matches_its_own_branch(self, builder):
        game = board(builder)
        bear = only_oid(game, "t_bear")
        ctx = ctx_for(game, bear)
        assert matches(ctx, bear, {"any_of": SELF_OR_COMMANDER})

    def test_a_commander_matches_the_other_branch(self, builder):
        """Put the commander on the battlefield so both branches have something."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["t_bear"])
            .battlefield(0, ["t_commander"])
            .build()
        )
        bear = only_oid(game, "t_bear")
        commander = only_oid(game, "t_commander")
        game.state.objects[commander].is_commander = True
        ctx = ctx_for(game, bear)
        assert matches(ctx, commander, {"any_of": SELF_OR_COMMANDER})

    def test_something_matching_neither_is_refused(self, builder):
        game = board(builder)
        bear = only_oid(game, "t_bear")
        other = only_oid(game, "grizzly_bears")
        ctx = ctx_for(game, bear)
        assert not matches(ctx, other, {"any_of": SELF_OR_COMMANDER})

    def test_neither_branch_alone_would_do(self, builder):
        """The reason this key exists. `self_only` and `is_commander` are each
        true of only one of the two objects the printed line names."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 3 + ["t_bear"])
            .battlefield(0, ["t_commander"])
            .build()
        )
        bear = only_oid(game, "t_bear")
        commander = only_oid(game, "t_commander")
        game.state.objects[commander].is_commander = True
        ctx = ctx_for(game, bear)
        assert not matches(ctx, commander, {"self_only": True})
        assert not matches(ctx, bear, {"is_commander": True})


class TestItComposesWithTheRestOfTheSelector:
    def test_outer_keys_still_filter(self, builder):
        """A union that ignored its neighbours would turn "a creature that is
        either of these" into "either a creature or these"."""
        game = board(builder)
        forest = game.state.battlefield[0]
        assert game.state.card(forest).id == "forest"
        ctx = ctx_for(game, forest)
        # The source is a Forest, so the `self_only` branch matches it -- but the
        # outer `types` clause must still refuse it.
        assert matches(ctx, forest, {"any_of": SELF_OR_COMMANDER})
        assert not matches(
            ctx, forest, {"types": ["Creature"], "any_of": SELF_OR_COMMANDER}
        )

    def test_it_narrows_a_pool(self, builder):
        game = board(builder)
        bear = only_oid(game, "t_bear")
        ctx = ctx_for(game, bear)
        pool = resolve_pool(
            ctx,
            {"zone": "battlefield", "types": ["Creature"], "any_of": SELF_OR_COMMANDER},
        )
        assert pool == [bear], "only the source is on the battlefield to match"


class TestLoadTimeGuards:
    def test_one_branch_is_refused(self):
        """A union of one is a filter written the long way, and two spellings of
        one thing is how they drift."""
        with pytest.raises(DslError, match="at least two selectors"):
            validate_selector({"any_of": [{"self_only": True}]}, "somewhere")

    def test_a_branch_naming_a_zone_is_refused(self):
        """It reads as "or anything in that zone" and is not: a branch filters
        the pool the outer selector already chose."""
        with pytest.raises(DslError, match="put 'zone' on the outer selector"):
            validate_selector(
                {"any_of": [{"zone": "graveyard"}, {"self_only": True}]}, "somewhere"
            )

    def test_a_misspelled_key_inside_a_branch_is_refused(self):
        with pytest.raises(DslError, match="unknown selector keys"):
            validate_selector(
                {"any_of": [{"slef_only": True}, {"is_commander": True}]}, "somewhere"
            )

    def test_a_valid_union_loads(self):
        validate_selector(
            {"zone": "battlefield", "any_of": SELF_OR_COMMANDER}, "somewhere"
        )
