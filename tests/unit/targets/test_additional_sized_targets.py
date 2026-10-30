"""A spell's target count fixed by how many times its additional cost is paid.

    "As an additional cost to cast this spell, sacrifice X creatures. Destroy X
    target nonland permanents." -- Immoral Bargain.

Legal because of the rules order, X's argument for Crackle with Power applied to
the additional cost: 601.2b has the caster announce how they will pay the
additional costs -- here, how many creatures they will sacrifice -- and 601.2c
declares the targets one step later. Payment is later still (601.2h), so the
number is known before anything is sacrificed. 107.3 lets X be 0: sacrificing
nothing is a cast with no targets, not an uncastable spell.

What would be wrong without it is a different card in each direction.
`count: "any"` lets the caster destroy three permanents for one sacrifice, a
strictly better card. A fixed count cannot follow the sacrifices at all. And
the expression read off the object while legality enumerates reads zero -- or
the previous cast's payments -- which is why the loader refused it on a spell
until a cast line could substitute its own number.

The witness is `t_immoral_bargain` in `tests/data/additional_sized_targets.cards.json`.
The known limit is `casting.MAX_ADDITIONAL_TIMES`: a repeatable cost is offered
at most that many times, so X never exceeds it however many creatures you have.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.casting import MAX_ADDITIONAL_TIMES
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, settle_to_priority

BARGAIN = "t_immoral_bargain"
BEAR = "grizzly_bears"
GIANT = "hill_giant"
RING = "sol_ring"


def position(builder, *, mine=(BEAR, BEAR), theirs=(GIANT, RING, BEAR)):
    """Immoral Bargain in hand on the caster's main phase, with priority held."""
    game = (
        builder(players=2)
        .hand(0, [BARGAIN])
        .battlefield(0, ["swamp", *mine])
        .battlefield(1, ["island", *theirs])
        .library(0, ["swamp"] * 10)
        .library(1, ["island"] * 10)
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game.state.players[0].full_control = True
    game._advance()
    return game


def lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BARGAIN
    ]


def resolve(game, action):
    """Cast on ``action``, answer the sacrifice, and let the spell resolve."""
    game.apply(action)
    settle_to_priority(game)
    return game


def compile_bargain(**overrides):
    base = {
        "id": "t_probe",
        "name": "Probe",
        "mana_cost": "{B}",
        "types": ["Sorcery"],
        "additional_cost": {"sacrifice": {"controller": "you", "types": ["Creature"]}},
        "additional_optional": True,
        "additional_repeatable": True,
        "targets": [
            {
                "id": "t1",
                "kind": "permanent",
                "count": {"additional_paid": True},
                "selector": {"zone": "battlefield", "not_types": ["Land"]},
            }
        ],
        "spell_effects": [{"op": "destroy", "objects": {"target": "t1"}}],
    }
    base.update(overrides)
    return compile_card(CardModel.model_validate(base))


class TestEachLineDeclaresExactlyItsX:
    def test_sacrificing_two_offers_exactly_two_targets(self, builder):
        game = position(builder)
        two = [a for a in lines(game) if a.additional_times == 2]
        assert two
        assert all(len(a.targets) == 2 for a in two)
        assert all(len(set(a.targets)) == 2 for a in two), "two different targets (601.2c)"

    def test_every_line_has_as_many_targets_as_sacrifices(self, builder):
        """You can't choose more targets than creatures sacrificed -- or fewer."""
        game = position(builder)
        offered = lines(game)
        assert {a.additional_times for a in offered} == {0, 1, 2}
        for action in offered:
            assert len(action.targets) == action.additional_times, action.label

    def test_x_zero_casts_with_no_targets(self, builder):
        game = position(builder)
        zero = [a for a in lines(game) if a.additional_times == 0]
        assert len(zero) == 1
        assert zero[0].targets == ()

    def test_x_zero_resolves_and_destroys_nothing(self, builder):
        game = position(builder)
        zero = next(a for a in lines(game) if a.additional_times == 0)
        before = len(game.state.battlefield_objects())
        resolve(game, zero)
        assert len(game.state.battlefield_objects()) == before
        assert game.state.objects[zero.source].zone is Zone.GRAVEYARD


class TestLegalityNeverOffersAnXYouCannotPay:
    def test_no_line_sacrifices_more_creatures_than_you_control(self, builder):
        game = position(builder, mine=(BEAR,))
        assert max(a.additional_times for a in lines(game)) == 1

    def test_with_no_creatures_only_x_zero_is_offered(self, builder):
        game = position(builder, mine=())
        assert {a.additional_times for a in lines(game)} == {0}

    def test_a_creature_about_to_be_sacrificed_may_be_targeted(self, builder):
        """601.2c declares the targets before 601.2h pays the cost, so the
        creature that will be sacrificed is still a legal target when chosen --
        with nothing else on the board, X = 1 points at it."""
        game = position(builder, mine=(BEAR,), theirs=())
        (bear,) = oids_of(game, BEAR, 0)
        one = [a for a in lines(game) if a.additional_times == 1]
        assert [tuple(ref.id for ref in a.targets) for a in one] == [(bear,)]

    def test_the_repeat_cap_bounds_x(self, builder):
        """The known limit: `MAX_ADDITIONAL_TIMES` caps every repeatable cost."""
        many = (BEAR,) * (MAX_ADDITIONAL_TIMES + 2)
        game = position(builder, mine=many)
        assert max(a.additional_times for a in lines(game)) == MAX_ADDITIONAL_TIMES


class TestTheSpellDoesWhatItsLineSays:
    def test_two_sacrificed_two_destroyed(self, builder):
        game = position(builder)
        theirs = set(oids_of(game, GIANT, 1)) | set(oids_of(game, RING, 1))
        line = next(
            a
            for a in lines(game)
            if a.additional_times == 2 and {ref.id for ref in a.targets} == theirs
        )
        mine = oids_of(game, BEAR, 0)
        resolve(game, line)
        assert all(game.state.objects[oid].zone is Zone.GRAVEYARD for oid in theirs)
        assert all(game.state.objects[oid].zone is Zone.GRAVEYARD for oid in mine), (
            "both creatures were the cost"
        )
        assert oids_of(game, BEAR, 1), "the untargeted permanent survives"


class TestTheLoaderRefusesWhatCannotBeHonoured:
    def test_the_printed_shape_loads(self):
        card = compile_bargain()
        assert card.targets[0].additional_sized

    def test_any_other_computed_count_on_a_spell_is_still_refused(self):
        with pytest.raises(DslError, match="computed 'count'"):
            compile_bargain(
                targets=[
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "count": {"count": {"zone": "battlefield"}},
                        "selector": {"zone": "battlefield"},
                    }
                ]
            )

    def test_no_additional_cost_is_refused(self):
        with pytest.raises(DslError, match="additional_paid"):
            compile_bargain(
                additional_cost=None, additional_optional=False, additional_repeatable=False
            )

    def test_a_cost_paid_exactly_once_is_refused(self):
        with pytest.raises(DslError, match="exactly once"):
            compile_bargain(additional_optional=False, additional_repeatable=False)

    @pytest.mark.parametrize(
        "extra", [{"up_to": True}, {"optional": True}, {"count_if_kicked": "any"}]
    )
    def test_a_second_size_on_the_spec_is_refused(self, extra):
        spec = {
            "id": "t1",
            "kind": "permanent",
            "count": {"additional_paid": True},
            "selector": {"zone": "battlefield", "not_types": ["Land"]},
            **extra,
        }
        with pytest.raises(DslError, match="exactly the times"):
            compile_bargain(targets=[spec], kicker="{1}")

    def test_it_must_be_the_last_target(self):
        """The resolving spell hands the last spec every remaining ref."""
        with pytest.raises(DslError, match="must come last"):
            compile_bargain(
                targets=[
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "count": {"additional_paid": True},
                        "selector": {"zone": "battlefield", "not_types": ["Land"]},
                    },
                    {"id": "p", "kind": "player", "selector": {}},
                ]
            )
