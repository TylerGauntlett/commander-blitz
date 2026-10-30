"""The greatest mana value among a pool, as a static's magnitude.

    "Dragon Man's power is equal to the greatest mana value among noncreature
    permanents you control and noncreature cards in your graveyard."
                                          -- Dragon Man, Reformed Robot

A characteristic-defining ability (604.3) that must track the board
continuously, so a one-shot `set_pt` op cannot say it, and the effect side's
`extreme_value` was not in the static value language. It is now, held to
``of: "mana_value"``: a printed mana value is a pipeline input on
`mana_symbols`' terms, where a power would be another static's output -- the
dependency layers-lite forbids. ``objects`` is a static counting filter or a
``union`` of them, because the printed pool spans the battlefield and a
graveyard. An empty pool is 0. `count` is the near miss: it says how many, never
how big.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.statics import _validate_static_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pt

ROBOT = "t_sev_robot"  # */5, power = greatest MV among your noncreature permanents and graveyard cards
ROCK = "t_sev_rock"  # artifact, MV 2
RELIC = "t_sev_relic"  # enchantment, MV 5
RITUAL = "t_sev_ritual"  # sorcery, MV 6
TITAN = "t_sev_titan"  # creature, MV 7


def board(builder, mine=(), yard=(), theirs=(), their_yard=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .graveyard(0, list(yard))
        .battlefield(1, list(theirs))
        .graveyard(1, list(their_yard))
        .build(advance=False)
    )


def power(game) -> int:
    return pt(game, only_oid(game, ROBOT))[0]


class TestThePool:
    def test_nothing_matching_is_zero(self, builder):
        game = board(builder, mine=[ROBOT])
        assert power(game) == 0

    def test_the_greatest_permanent(self, builder):
        game = board(builder, mine=[ROBOT, ROCK, RELIC])
        assert power(game) == 5

    def test_the_graveyard_joins(self, builder):
        game = board(builder, mine=[ROBOT, RELIC], yard=[RITUAL])
        assert power(game) == 6

    def test_creatures_are_left_out_in_both_zones(self, builder):
        """The robot itself is MV 4 and a creature; the titan is MV 7."""
        game = board(builder, mine=[ROBOT, ROCK, TITAN], yard=[TITAN])
        assert power(game) == 2

    def test_an_opponents_cards_are_not_yours(self, builder):
        game = board(builder, mine=[ROBOT, ROCK], theirs=[RELIC], their_yard=[RITUAL])
        assert power(game) == 2

    def test_toughness_is_untouched(self, builder):
        game = board(builder, mine=[ROBOT, RELIC])
        assert pt(game, only_oid(game, ROBOT)) == (5, 5)


class TestItTracksTheBoard:
    def test_a_permanent_leaving_lowers_it(self, builder):
        game = board(builder, mine=[ROBOT, ROCK, RELIC])
        move_object(game.state, only_oid(game, RELIC), Zone.EXILE)
        assert power(game) == 2

    def test_a_permanent_dying_keeps_counting_from_the_graveyard(self, builder):
        game = board(builder, mine=[ROBOT, RELIC])
        move_object(game.state, only_oid(game, RELIC), Zone.GRAVEYARD)
        assert power(game) == 5


class TestTheLoader:
    GOOD = {"of": "mana_value", "pick": "greatest", "objects": {"union": [
        {"zone": "battlefield", "controller": "you", "not_types": ["Creature"]},
        {"zone": "graveyard", "controller": "you", "not_types": ["Creature"]},
    ]}}

    def test_the_printed_shape_loads(self):
        _validate_static_value({"extreme_value": self.GOOD}, "test")

    def test_a_single_filter_loads(self):
        spec = {"of": "mana_value", "objects": {"controller": "you", "types": ["Artifact"]}}
        _validate_static_value({"extreme_value": spec}, "test")

    def test_power_is_refused(self):
        """A power is a layer's output; reading it would make one static depend on another."""
        with pytest.raises(DslError, match="can only read 'mana_value'"):
            _validate_static_value({"extreme_value": {**self.GOOD, "of": "power"}}, "test")

    def test_objects_are_required(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            _validate_static_value({"extreme_value": {"of": "mana_value"}}, "test")

    def test_a_branch_is_held_to_the_static_filter(self):
        bad = {"of": "mana_value", "objects": {"union": [
            {"controller": "you", "types": ["Artifact"]},
            {"zone": "graveyard", "controller": "you", "tapped": True},
        ]}}
        with pytest.raises(DslError):
            _validate_static_value({"extreme_value": bad}, "test")
