"""A target declared only when the spell is cast during a given phase.

    "Exile target artifact or enchantment. **If you cast this spell during your
    main phase, you may exile up to one other target artifact or
    enchantment.**" -- Return to Dust.

The second target is part of the cast, not of the resolution: 601.2c declares
every target as the spell is cast, and the printed condition is a fact about
that same moment. So a cast outside your main phase has one target and a cast
inside it may have two. `cast_during` on the spec is read by
`targeting.enumerate_target_tuples` through `conditions.cast_during_now`, from
the same facts `stack.push_spell` stamps for the `cast_during` condition: the
step the game is in and whether the caster is the active player.

The near miss is a second target that is always declared, exiled inside an
`if cast_during` at resolution. That card can point at a second permanent
during combat or on an opponent's turn -- ward triggers, heroic fires,
"becomes the target" pays out -- and so is a different card.

Resolution splits the stored refs by the full spec list. The gated spec is held
to the last place and to a size that admits nought (``optional`` or ``up_to``)
by the loader, so the one-target cast's empty second bucket is one
`filter_legal` already reads correctly.

The witness is Return to Dust (`t_return_to_dust` in
`tests/data/cast_during_targets.cards.json`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import TargetRef
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, oids_of

DUST = "t_return_to_dust"
RING = "sol_ring"
ANTHEM = "t_lg_anthem"  # an enchantment
BEAR = "grizzly_bears"


def position(builder, *, step=Step.PRECOMBAT_MAIN, active=0, theirs=(RING, ANTHEM, BEAR)):
    game = (
        builder(players=2)
        .hand(0, [DUST])
        .battlefield(0, ["plains"] * 4)
        .library(0, ["plains"] * 10)
        .battlefield(1, ["island", *theirs])
        .library(1, ["island"] * 10)
        .turn(3)
        .active(active)
        .step(step)
        .build(advance=False)
    )
    game.state.players[0].full_control = True
    game._advance()
    # On seat 1's turn seat 1 holds priority first; pass it to the caster.
    while (pending := game.pending()) is not None and pending.player != 0:
        game.apply(_default_answer(game, pending))
    return game


def lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == DUST
    ]


def sizes(game) -> set[int]:
    return {len(a.targets) for a in lines(game)}


def theirs(game, card):
    return oids_of(game, card, 1)[0]


def resolve(game, action, *, exile_second=True):
    game.apply(action)
    for _ in range(40):
        pending = game.pending()
        # The spell has left the stack by the time its `may` asks.
        if not game.state.stack and (pending is None or pending.kind is DecisionKind.PRIORITY):
            break
        if pending.kind is DecisionKind.MAY:
            want = ActionKind.YES if exile_second else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
        else:
            game.apply(_default_answer(game, pending))


class TestYourMainPhase:
    def test_one_or_two_targets_may_be_declared(self, builder):
        game = position(builder)
        assert sizes(game) == {1, 2}

    def test_the_second_main_phase_is_one_too(self, builder):
        game = position(builder, step=Step.POSTCOMBAT_MAIN)
        assert sizes(game) == {1, 2}

    def test_the_two_targets_are_different_objects(self, builder):
        """ "Up to one **other** target": 115.3, one object per word "target"."""
        game = position(builder)
        for action in lines(game):
            assert len(set(action.targets)) == len(action.targets)

    def test_only_artifacts_and_enchantments(self, builder):
        game = position(builder)
        bear = TargetRef.obj(theirs(game, BEAR))
        assert all(bear not in a.targets for a in lines(game))

    def test_both_are_exiled(self, builder):
        game = position(builder)
        ring, anthem = theirs(game, RING), theirs(game, ANTHEM)
        pair = (TargetRef.obj(ring), TargetRef.obj(anthem))
        resolve(game, next(a for a in lines(game) if a.targets == pair))
        assert game.state.objects[ring].zone is Zone.EXILE
        assert game.state.objects[anthem].zone is Zone.EXILE

    def test_the_second_is_a_may(self, builder):
        game = position(builder)
        ring, anthem = theirs(game, RING), theirs(game, ANTHEM)
        pair = (TargetRef.obj(ring), TargetRef.obj(anthem))
        resolve(game, next(a for a in lines(game) if a.targets == pair), exile_second=False)
        assert game.state.objects[ring].zone is Zone.EXILE
        assert game.state.objects[anthem].zone is Zone.BATTLEFIELD

    def test_one_target_resolves_alone(self, builder):
        """The empty second bucket: resolution splits by the full spec list."""
        game = position(builder)
        ring = theirs(game, RING)
        resolve(game, next(a for a in lines(game) if a.targets == (TargetRef.obj(ring),)))
        assert game.state.objects[ring].zone is Zone.EXILE
        assert game.state.objects[theirs(game, ANTHEM)].zone is Zone.BATTLEFIELD

    def test_one_legal_object_is_still_a_cast(self, builder):
        game = position(builder, theirs=(RING,))
        assert sizes(game) == {1}


class TestOutsideIt:
    @pytest.mark.parametrize("step", [Step.UPKEEP, Step.BEGIN_COMBAT, Step.END_STEP])
    def test_your_other_steps_declare_one(self, builder, step):
        game = position(builder, step=step)
        assert sizes(game) == {1}

    def test_an_opponents_main_phase_declares_one(self, builder):
        """ "**Your** main phase": the phase alone is not enough."""
        game = position(builder, active=1)
        assert sizes(game) == {1}

    def test_and_resolves_with_one(self, builder):
        game = position(builder, step=Step.END_STEP)
        ring = theirs(game, RING)
        resolve(game, lines(game)[0])
        exiled = [
            o for o in (ring, theirs(game, ANTHEM)) if game.state.objects[o].zone is Zone.EXILE
        ]
        assert len(exiled) == 1


def model(**second) -> CardModel:
    spec = {
        "id": "t2",
        "kind": "permanent",
        "optional": True,
        "cast_during": "your_main",
        "selector": {"any_types": ["Artifact", "Enchantment"], "zone": "battlefield"},
    }
    spec.update(second)
    spec = {k: v for k, v in spec.items() if v is not None}
    text = (
        "Exile target artifact or enchantment. If you cast this spell during your main "
        "phase, you may exile up to one other target artifact or enchantment."
    )
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": text,
            "mana_cost": "{2}{W}{W}",
            "types": ["Instant"],
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "selector": {"any_types": ["Artifact", "Enchantment"], "zone": "battlefield"},
                },
                spec,
            ],
            "spell_effects": [
                {"op": "exile", "objects": {"target": "t1"}},
                {"op": "exile", "objects": {"target": "t2"}},
            ],
        }
    )


class TestTheLoader:
    def test_the_shape_loads(self):
        compile_card(model())

    def test_an_unknown_phase_is_refused(self):
        with pytest.raises(DslError, match="cast_during"):
            compile_card(model(cast_during="your_lunch"))

    def test_a_fixed_count_is_refused(self):
        """Shut, it would declare nothing where a fixed count needs a ref."""
        with pytest.raises(DslError, match="needs 'optional' or 'up_to'"):
            compile_card(model(optional=None))

    def test_up_to_n_loads(self):
        compile_card(model(optional=None, count=2, up_to=True))

    def test_a_floor_is_refused(self):
        with pytest.raises(DslError, match="min_count"):
            compile_card(model(optional=None, count=3, up_to=True, min_count=1))

    def test_it_must_come_last(self):
        card = model()
        card.targets.reverse()
        with pytest.raises(DslError, match="last target"):
            compile_card(card)

    def test_an_abilitys_target_is_refused(self):
        card = CardModel.model_validate(
            {
                "id": "y",
                "name": "Y",
                "oracle_text": "{T}: Exile up to one target artifact.",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "{T}: Exile up to one target artifact.",
                        "cost": {"tap": True},
                        "targets": [
                            {
                                "id": "t1",
                                "kind": "permanent",
                                "optional": True,
                                "cast_during": "your_main",
                                "selector": {"types": ["Artifact"], "zone": "battlefield"},
                            }
                        ],
                        "effects": [{"op": "exile", "objects": {"target": "t1"}}],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="about a cast"):
            compile_card(card)
