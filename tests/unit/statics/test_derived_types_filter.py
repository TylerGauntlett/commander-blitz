"""An anthem's filter reads the types layer 4 left.

    "When this enchantment enters, put a +1/+1 counter on each creature you
     control. Creatures you control with +1/+1 counters on them are artifacts
     in addition to their other types. Nonartifact creatures get -1/-1."
                                                    -- The Flesh Is Weak

The second sentence is a type change (613.1d, layer 4); the third is a P/T
change (613.4c, layer 7c). Rule 613.1 applies the layers in order, so which
creatures the -1/-1 reaches is decided after every type change has applied: a
creature the second sentence made an artifact is not a nonartifact creature.
That is an ordered read across layers, not a dependency -- 613.8 orders effects
within one layer (613.8a) -- and nothing in layer 4 reads layer 7c back.

The static filter language reads printed types (ADR 0001), so without
`derived_types` the third sentence shrinks the creatures the second one
converted, which inverts the card: `t_dtf_printed_shrink` is that near miss,
kept live. With the key, the anthem step of `characteristics._compute` hands
`_matches` the object's own working type sets (`Layer4Types`), so the read
asks `chars` nothing and cannot recurse (ADR 0031). The key is admitted on
`buff` alone, because that step is the only reader holding the sets.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import _matches, chars
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import add_counters, remove_counters
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, only_oid, pt, settle, static_probe

FLESH = "t_dtf_flesh"  # The Flesh Is Weak
PRINTED = "t_dtf_printed_shrink"  # "Nonartifact creatures get -1/-1", printed reading
GOBLINIZER = "t_dtf_goblinizer"  # creatures you control are Goblins
GOBLIN_LORD = "t_dtf_goblin_lord"  # Goblins you control get +1/+1, `derived_types`
CONSTRUCT = "t_dtf_construct"  # printed 1/1 artifact creature
BEAR = "t_bear"  # printed 2/2
OGRE = "t_dtf_ogre"  # printed 3/3, which outlives two -1/-1 anthems


def board(builder, mine=(), theirs=(), *, hand=()):
    """``(game, bear)``: player 0's ``mine`` and a Test Bear, facing ``theirs``."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR, *mine])
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .build()
    )
    return game, only_oid(game, BEAR, 0)


def counter(game, oid: int) -> None:
    add_counters(game.state, oid, PLUS_ONE, 1)


def is_artifact(game, oid: int) -> bool:
    return "Artifact" in chars(game.state, oid).types


class TestTheCard:
    def test_entering_converts_and_spares_your_creatures(self, builder):
        """The whole card, cast: counter, artifact, no -1/-1 -- a 3/3."""
        game, bear = board(
            builder, ["plains", "island", "swamp", "swamp", "swamp"], hand=[FLESH]
        )
        game.apply(action_for_card(game, ActionKind.CAST, FLESH))
        settle(game)
        assert only_oid(game, FLESH, 0) in game.state.battlefield
        assert is_artifact(game, bear)
        assert pt(game, bear) == (3, 3)

    def test_a_creature_without_a_counter_shrinks(self, builder):
        game, bear = board(builder, [FLESH])
        assert not is_artifact(game, bear)
        assert pt(game, bear) == (1, 1)

    def test_a_converted_creature_is_spared(self, builder):
        game, bear = board(builder, [FLESH])
        counter(game, bear)
        assert is_artifact(game, bear)
        assert pt(game, bear) == (3, 3), "the counter and no -1/-1"

    def test_a_printed_artifact_is_spared(self, builder):
        game, _ = board(builder, [FLESH, CONSTRUCT])
        assert pt(game, only_oid(game, CONSTRUCT, 0)) == (1, 1)

    def test_an_opponents_creature_with_a_counter_shrinks(self, builder):
        """"Creatures you control" converts; "nonartifact creatures" is anybody's."""
        game, _ = board(builder, [FLESH], [BEAR])
        theirs = only_oid(game, BEAR, 1)
        counter(game, theirs)
        assert not is_artifact(game, theirs)
        assert pt(game, theirs) == (2, 2), "+1/+1 counter, then -1/-1"


class TestTheWearingOff:
    def test_losing_the_counter_brings_the_shrink_back(self, builder):
        game, bear = board(builder, [FLESH])
        counter(game, bear)
        remove_counters(game.state, bear, PLUS_ONE, 1)
        assert not is_artifact(game, bear)
        assert pt(game, bear) == (1, 1)

    def test_the_enchantment_leaving_ends_both_lines(self, builder):
        game, bear = board(builder, [FLESH])
        counter(game, bear)
        move_object(game.state, only_oid(game, FLESH, 0), Zone.GRAVEYARD)
        assert not is_artifact(game, bear)
        assert pt(game, bear) == (3, 3), "the counter alone"


class TestTheNearMiss:
    def test_the_printed_reading_shrinks_a_converted_creature(self, builder):
        """Without the key the filter sees the printed Bear, not the artifact."""
        game = builder(players=2).battlefield(0, [FLESH, PRINTED, OGRE]).build()
        ogre = only_oid(game, OGRE, 0)
        counter(game, ogre)
        assert is_artifact(game, ogre)
        assert pt(game, ogre) == (3, 3), "+1 counter, -1 from the printed reader only"


class TestSubtypes:
    def test_a_granted_creature_type_is_seen(self, builder):
        game, bear = board(builder, [GOBLINIZER, GOBLIN_LORD])
        assert "Goblin" in chars(game.state, bear).subtypes
        assert pt(game, bear) == (3, 3)

    def test_without_the_grant_nothing_is_pumped(self, builder):
        game, bear = board(builder, [GOBLIN_LORD])
        assert pt(game, bear) == (2, 2)


class TestOnlyTheAnthemStepAsks:
    def test_a_match_without_the_layer_4_sets_raises(self, builder):
        game, bear = board(builder, [FLESH])
        flesh = game.state.objects[only_oid(game, FLESH, 0)]
        selector = {"controller": "any", "not_types": ["Artifact"], "derived_types": True}
        with pytest.raises(DslError, match="derived_types"):
            _matches(game.state, game.state.objects[bear], flesh, selector)


def compile_static(static: dict):
    return compile_card(CardModel.model_validate(static_probe(static)))


BUFF = {"effect": "buff", "power": -1, "toughness": -1}
AFFECTS = {"controller": "any", "types": ["Creature"], "not_types": ["Artifact"]}


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        assert compile_static({**BUFF, "affects": {**AFFECTS, "derived_types": True}})

    def test_inside_a_union(self):
        affects = {
            "controller": "any",
            "derived_types": True,
            "any_of": [{"types": ["Creature"]}, {"subtypes": ["Goblin"]}],
        }
        assert compile_static({**BUFF, "affects": affects})

    @pytest.mark.parametrize("value", [False, 1, "yes"])
    def test_true_only(self, value):
        with pytest.raises(DslError, match="derived_types"):
            compile_static({**BUFF, "affects": {**AFFECTS, "derived_types": value}})

    def test_another_static_is_refused(self):
        """A keyword grant has readers outside the anthem step; it would raise mid-game."""
        with pytest.raises(DslError, match=r"derived_types.*'buff'"):
            compile_static(
                {
                    "effect": "grant_keyword",
                    "keywords": ["flying"],
                    "affects": {**AFFECTS, "derived_types": True},
                }
            )

    def test_a_filter_naming_no_type_is_refused(self):
        with pytest.raises(DslError, match="names none of them"):
            compile_static({**BUFF, "affects": {"controller": "you", "derived_types": True}})

    def test_a_branch_is_refused(self):
        affects = {
            "controller": "any",
            "any_of": [{"types": ["Creature"], "derived_types": True}, {"tapped": True}],
        }
        with pytest.raises(DslError, match="outer filter"):
            compile_static({**BUFF, "affects": affects})
