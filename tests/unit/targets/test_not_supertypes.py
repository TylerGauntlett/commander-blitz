"""``not_supertypes`` — "destroy target **nonbasic** land" (rule 205.4a).

A supertype the permanent must *lack*. `supertypes` cannot say it: it is a
positive subset test (`set(want).issubset(supertypes)`), so it can require Basic
and can never forbid it. The negated keys the selector language already had are
`not_types`, `not_subtypes`, `not_colors` and `not_keywords`; there was no
supertype member of that family until Field of Ruin, the witness in the shipped
pool, needed one.

The near miss is the whole reason this is a key and not a card-side trick.
Spelling "nonbasic" as `not_subtypes: ["Plains", "Island", "Swamp", "Mountain",
"Forest"]` reads as the same sentence and is a materially weaker card: it spares
every nonbasic land that carries a basic land type — Hallowed Fountain,
Murmuring Bosk, Dryad Arbor — which is exactly the mana base Field of Ruin is
printed to answer. It also gets the other side right only by coincidence: a
Snow-Covered Forest is Basic and must be an illegal target, and the subtype list
excludes it because it happens to be a Forest rather than because it is basic.
Wastes shows the coincidence failing outright — it is Basic with no subtype at
all, so the approximation would happily destroy it.

`mana_value` cannot separate them either; every land, basic or not, is 0.

Asserted on both paths a targeting card walks: `objects` (`selectors.matches`)
and target legality (`targeting.candidates`, and `still_legal` on resolution).
"""

from __future__ import annotations

import pytest

from automtg.engine.carddef import TargetSpec
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import matches, resolve_pool, validate_selector
from automtg.engine.errors import DslError
from automtg.engine.structs import TargetRef
from automtg.engine.targeting import candidates, still_legal
from tests.conftest import only_oid

#: What Field of Ruin's target spec says.
NONBASIC_LAND = {
    "zone": "battlefield",
    "types": ["Land"],
    "not_supertypes": ["Basic"],
}

#: The tempting approximation, kept here so the tests can assert it is a
#: different filter rather than merely asserting the right one works.
BY_SUBTYPE = {
    "zone": "battlefield",
    "types": ["Land"],
    "not_subtypes": ["Plains", "Island", "Swamp", "Mountain", "Forest"],
}


def board(builder):
    """Every shape the basic/nonbasic line has to rule on, on one battlefield.

    `forest` is the plain basic; `snow_covered_forest` is Basic *and* Snow, the
    two-supertype case; `wastes` is basic with no subtype; `hallowed_fountain`,
    `murmuring_bosk` and `dryad_arbor` are the nonbasic lands that carry a basic
    land type; `command_tower` is the nonbasic land with no subtype at all.
    """
    return (
        builder(players=2)
        .battlefield(0, ["forest", "snow_covered_forest", "wastes", "command_tower"])
        .battlefield(1, ["hallowed_fountain", "murmuring_bosk", "dryad_arbor"])
        .build()
    )


def selects(game, oid: int, selector: dict) -> bool:
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    return matches(ctx, oid, selector)


class TestItForbidsTheSupertype:
    def test_a_basic_land_is_refused(self, builder):
        game = board(builder)
        assert not selects(game, only_oid(game, "forest"), NONBASIC_LAND)

    def test_a_land_with_two_supertypes_is_refused_for_the_one_named(self, builder):
        """Snow-Covered Forest is Basic and Snow. The intersection test has to
        fire on Basic alone; a subset test would ask the wrong question."""
        game = board(builder)
        assert not selects(game, only_oid(game, "snow_covered_forest"), NONBASIC_LAND)

    def test_a_nonbasic_land_with_no_subtypes_is_accepted(self, builder):
        game = board(builder)
        assert selects(game, only_oid(game, "command_tower"), NONBASIC_LAND)

    def test_a_snow_land_that_is_not_basic_is_still_a_legal_target(self, builder):
        """`not_supertypes: ["Basic"]` is about one supertype, not about having
        any. Highland Weald is Snow and nonbasic, and Field of Ruin may destroy
        it."""
        game = builder(players=2).battlefield(0, ["highland_weald"]).build()
        assert selects(game, only_oid(game, "highland_weald"), NONBASIC_LAND)


class TestTheSubtypeApproximationIsADifferentCard:
    """Each assertion here is a card the two spellings disagree about."""

    @pytest.mark.parametrize(
        "card_id", ["hallowed_fountain", "murmuring_bosk", "dryad_arbor"]
    )
    def test_a_nonbasic_land_with_a_basic_land_type_is_a_legal_target(
        self, builder, card_id
    ):
        game = board(builder)
        oid = only_oid(game, card_id)
        assert selects(game, oid, NONBASIC_LAND)
        assert not selects(game, oid, BY_SUBTYPE), (
            "if this ever passes, not_subtypes became a valid substitute and "
            "this test is no longer making its point"
        )

    def test_a_basic_land_with_no_subtype_would_be_destroyed_by_the_approximation(
        self, builder
    ):
        """Wastes. The approximation errs in *both* directions, and this is the
        dangerous one: it destroys a basic land the printed card protects."""
        game = board(builder)
        oid = only_oid(game, "wastes")
        assert not selects(game, oid, NONBASIC_LAND)
        assert selects(game, oid, BY_SUBTYPE)


class TestTargetLegality:
    """The half the gap record insists on: a card that *targets*.

    `objects` and target legality are two different entry points —
    `resolve_pool` for the first, `targeting.candidates` and `still_legal` for
    the second — and a key honoured in only one of them makes a spell that can
    be aimed at a Mountain and then does nothing.
    """

    spec = TargetSpec(id="t1", kind="permanent", selector={**NONBASIC_LAND, "controller": "opponent"})

    def test_only_the_opponents_nonbasic_lands_are_offered(self, builder):
        game = board(builder)
        offered = {
            game.state.objects[ref.id].def_id
            for ref in candidates(game.state, 0, self.spec, None)
        }
        assert offered == {"hallowed_fountain", "murmuring_bosk", "dryad_arbor"}

    def test_a_basic_land_is_not_offered_even_when_an_opponent_controls_it(
        self, builder
    ):
        game = (
            builder(players=2)
            .battlefield(1, ["forest", "snow_covered_island", "wastes", "command_tower"])
            .build()
        )
        offered = {
            game.state.objects[ref.id].def_id
            for ref in candidates(game.state, 0, self.spec, None)
        }
        assert offered == {"command_tower"}

    def test_a_chosen_basic_land_is_illegal_on_resolution(self, builder):
        """`still_legal` re-checks as the ability resolves, and it is a separate
        call site from `candidates` — so it is asserted separately."""
        game = board(builder)
        assert still_legal(
            game.state, 0, self.spec, TargetRef.obj(only_oid(game, "dryad_arbor")), None
        )
        assert not still_legal(
            game.state, 0, self.spec, TargetRef.obj(only_oid(game, "forest")), None
        )


class TestItComposesWithTheRestOfTheSelector:
    def test_it_narrows_a_pool_rather_than_replacing_it(self, builder):
        game = board(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        pool = resolve_pool(ctx, {**NONBASIC_LAND, "controller": "you"})
        assert [game.state.objects[o].def_id for o in pool] == ["command_tower"]

    def test_without_the_key_every_land_matches(self, builder):
        """The state of the world before this key existed, asserted so the
        tests above are measuring something."""
        game = board(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        pool = resolve_pool(ctx, {"zone": "battlefield", "types": ["Land"], "controller": "you"})
        assert len(pool) == 4


class TestLoadTimeGuards:
    def test_a_misspelled_supertype_is_a_load_error(self):
        """A negation that names nothing forbids nothing, and looks like it
        worked: `not_supertypes: ["basic"]` is a Field of Ruin that destroys
        Mountains."""
        with pytest.raises(DslError, match="unknown supertype"):
            validate_selector({"not_supertypes": ["basic"]}, "somewhere")

    def test_the_same_guard_covers_the_positive_key(self):
        with pytest.raises(DslError, match="unknown supertype"):
            validate_selector({"supertypes": ["Legandary"]}, "somewhere")

    def test_the_real_spelling_loads(self):
        validate_selector(NONBASIC_LAND, "somewhere")
        validate_selector({"supertypes": ["Basic", "Snow"]}, "somewhere")
