"""An in-place copy that is a type or supertype in addition to what it copies.

    "-2: Target artifact you control becomes a copy of another target artifact
    or creature you control until end of turn, **except it's an artifact in
    addition to its other types**."            -- Saheeli, Sublime Artificer

    "…you may have Sarkhan become a copy of it until end of turn, except its
    name is Sarkhan, Soul Aflame **and it's legendary in addition to its other
    types**."                                   -- Sarkhan, Soul Aflame

Rule 707.9b: an exception to a copy effect is part of the copiable values. So
`become_copy`'s ``except_.add_types`` and ``except_.add_supertypes`` are written
onto the copied face itself (`copying_add_types`, `copying_add_supertypes`, read
by `GameState.card_of`), not granted on top. Without them Saheeli's artifact
copying a creature stops being an artifact -- every artifact count misses it and
"destroy target artifact" cannot point at it -- and Sarkhan copying a Dragon is
no legend, so the legend rule (704.5j) never sees it. A later `animate` or
type grant would be a layer-4 effect instead, which a copy of the copy does not
take.

The exception is the copy's, not the original's, and it ends with the copy.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import clear_until_eot
from commanderblitz.engine.structs import TargetRef
from tests.conftest import oids_of, only_oid, pt

ARTIFACT = "t_flying_artifact"  # a noncreature artifact, the thing that changes
BEAR = "t_bear"  # 2/2 vanilla creature, the thing copied


def board(builder, *, bears: int = 1):
    game = builder(players=2).battlefield(0, [ARTIFACT] + [BEAR] * bears).build()
    return game, only_oid(game, ARTIFACT), oids_of(game, BEAR)


def become_copy(game, subject: int, model: int, **overrides):
    """Resolve `become_copy` on ``subject`` copying ``model``: both are bound
    as targets by oid, the way Saheeli's two targets arrive."""
    spec = {
        "op": "become_copy",
        "duration": "end_of_turn",
        "objects": {"target": "t1"},
        "copying": {"target": "t2"},
        **overrides,
    }
    ctx = EffectContext(state=game.state, controller=0, source_oid=subject)
    ctx.targets = {"t1": (TargetRef.obj(subject),), "t2": (TargetRef.obj(model),)}
    gen = execute_one(ctx, spec)
    try:
        while True:
            next(gen)
    except StopIteration:
        pass
    return game


def types_of(game, oid: int) -> set[str]:
    return {str(t) for t in chars(game.state, oid).types}


def supertypes_of(game, oid: int) -> set[str]:
    return {str(t) for t in chars(game.state, oid).supertypes}


ARTIFACT_TOO = {"add_types": ["Artifact"]}
LEGENDARY_TOO = {"add_supertypes": ["Legendary"]}


class TestItIsAnArtifactInAdditionToItsOtherTypes:
    def test_a_copy_of_a_creature_is_an_artifact_creature(self, builder):
        game, artifact, (bear,) = board(builder)
        become_copy(game, artifact, bear, except_=ARTIFACT_TOO)
        assert game.state.card_of(game.state.objects[artifact]).name == "Test Bear"
        assert types_of(game, artifact) == {"Artifact", "Creature"}
        assert pt(game, artifact) == (2, 2)

    def test_the_type_is_on_the_copied_face(self, builder):
        game, artifact, (bear,) = board(builder)
        become_copy(game, artifact, bear, except_=ARTIFACT_TOO)
        assert "Artifact" in game.state.card_of(game.state.objects[artifact]).types

    def test_the_original_is_untouched(self, builder):
        game, artifact, (bear,) = board(builder)
        become_copy(game, artifact, bear, except_=ARTIFACT_TOO)
        assert types_of(game, bear) == {"Creature"}

    def test_without_the_exception_it_is_no_artifact(self, builder):
        """The near miss: a plain copy of a creature takes the creature's types whole."""
        game, artifact, (bear,) = board(builder)
        become_copy(game, artifact, bear)
        assert types_of(game, artifact) == {"Creature"}


class TestItIsLegendaryInAdditionToItsOtherTypes:
    def test_the_copy_is_legendary_and_keeps_its_name(self, builder):
        game, artifact, (bear,) = board(builder)
        become_copy(game, artifact, bear, except_name="Test Sarkhan", except_=LEGENDARY_TOO)
        assert game.state.card_of(game.state.objects[artifact]).name == "Test Sarkhan"
        assert supertypes_of(game, artifact) == {"Legendary"}
        assert supertypes_of(game, bear) == set()

    def test_the_legend_rule_sees_it(self, builder):
        """704.5j -- two legendary copies of one name under one controller."""
        game, artifact, (bear, other) = board(builder, bears=2)
        become_copy(game, artifact, bear, except_=LEGENDARY_TOO)
        become_copy(game, other, bear, except_=LEGENDARY_TOO)
        sba.run(game.state)
        alive = [o for o in (artifact, other) if o in game.state.battlefield]
        assert len(alive) == 1
        assert bear in game.state.battlefield, "the nonlegendary original is not in it"

    def test_without_the_exception_both_stay(self, builder):
        game, artifact, (bear, other) = board(builder, bears=2)
        become_copy(game, artifact, bear)
        become_copy(game, other, bear)
        sba.run(game.state)
        assert artifact in game.state.battlefield and other in game.state.battlefield


class TestTheDuration:
    def test_the_exception_ends_with_the_copy(self, builder):
        game, artifact, (bear,) = board(builder)
        become_copy(game, artifact, bear, except_={**ARTIFACT_TOO, **LEGENDARY_TOO})
        clear_until_eot(game.state)
        obj = game.state.objects[artifact]
        assert obj.copying is None
        assert obj.copying_add_types is None and obj.copying_add_supertypes is None
        assert types_of(game, artifact) == {"Artifact"}
        assert supertypes_of(game, artifact) == set()

    def test_a_new_copy_replaces_the_old_exception(self, builder):
        game, artifact, (bear,) = board(builder)
        become_copy(game, artifact, bear, except_={**ARTIFACT_TOO, **LEGENDARY_TOO})
        become_copy(game, artifact, bear)
        assert types_of(game, artifact) == {"Creature"}
        assert supertypes_of(game, artifact) == set()


class TestTheLoaderRefuses:
    def card(self, exception):
        ability = {
            "kind": "activated",
            "text": "x",
            "cost": {"tap": True},
            "targets": [
                {"id": "t1", "kind": "permanent", "selector": {"zone": "battlefield", "controller": "you",
                                          "types": ["Artifact"], "count": 1}},
                {"id": "t2", "kind": "permanent", "selector": {"zone": "battlefield", "controller": "you",
                                          "types": ["Creature"], "count": 1}},
            ],
            "effects": [
                {"op": "become_copy", "duration": "end_of_turn", "except_": exception,
                 "objects": {"target": "t1"}, "copying": {"target": "t2"}}
            ],
        }
        return {"id": "t_bad", "name": "Bad", "types": ["Artifact"], "abilities": [ability]}

    @pytest.mark.parametrize(
        "exception",
        [
            {"add_types": []},
            {"add_types": "Artifact"},
            {"add_types": ["artifact"]},
            {"add_supertypes": ["Legend"]},
            {"add_supertypes": []},
            {"remove_supertypes": ["Legendary"]},
        ],
    )
    def test_a_malformed_exception(self, exception):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(self.card(exception)))

    @pytest.mark.parametrize("exception", [ARTIFACT_TOO, LEGENDARY_TOO])
    def test_a_well_formed_exception_loads(self, exception):
        compile_card(CardModel.model_validate(self.card(exception)))
