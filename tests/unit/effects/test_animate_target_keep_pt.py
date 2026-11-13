"""A targeted `animate` that keeps a Vehicle's own size.

Tezzeret, Betrayer of Flesh's -2: *"Target artifact becomes an artifact
creature. If it isn't a Vehicle, it has base power and toughness 4/4."*

**301.7, why the Vehicle half names no size.** A Vehicle prints a power and
toughness that it has only while it is a creature; when it becomes one, those
are its base values. Writing `power_of`/`toughness_of` the target instead would
snapshot the numbers into a base-P/T effect with this ability's timestamp, and
a Vehicle sized by the effect that made it (the X/X Nalaar Aetherjet, 111.4)
or one given counters afterwards answers that differently. So the card writes
two animations over the one target: a `keep_pt` one narrowed to
`subtypes: ["Vehicle"]` and a 4/4 one narrowed to `not_subtypes: ["Vehicle"]`.

**Why the loader still refuses a wider pool.** `keep_pt` on a pool that can
reach a permanent with no printed size would make a 0/0 that 704.5f bins. A
`self_only` crew is held to its card's printed size by the linking pass; a
target narrowed to Vehicles reaches only permanents that print one. Anything
else -- a mass pool of Vehicles, an unnarrowed target -- is refused.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import only_oid

BLACKJACK = "the_blackjack_3_3_c_flying_crew2"
AETHERJET = "nalaar_aetherjet_x_x_c_flying_crew2"

#: Tezzeret's -2, as the card writes it.
MINUS_TWO = [
    {
        "op": "animate",
        "objects": {"target": "t1", "subtypes": ["Vehicle"]},
        "types": ["Artifact", "Creature"],
        "duration": "permanent",
        "keep_pt": True,
    },
    {
        "op": "animate",
        "objects": {"target": "t1", "not_subtypes": ["Vehicle"]},
        "types": ["Artifact", "Creature"],
        "duration": "permanent",
        "power": {"const": 4},
        "toughness": {"const": 4},
    },
]


def position(builder, card_id: str):
    """Player 0's artifact ``card_id`` on the battlefield, and its oid."""
    game = builder(players=2).battlefield(0, [card_id]).build(advance=False)
    return game, only_oid(game, card_id)


def resolve(game, oid: int) -> None:
    ctx = EffectContext(state=game.state, controller=0, targets={"t1": (TargetRef.obj(oid),)})
    gen = execute(ctx, MINUS_TWO)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def size(game, oid: int) -> tuple[int | None, int | None]:
    c = chars(game.state, oid)
    return c.power, c.toughness


class TestANonVehicle:
    def test_it_becomes_a_4_4_artifact_creature(self, builder):
        game, ring = position(builder, "sol_ring")
        resolve(game, ring)
        assert {"Artifact", "Creature"} <= chars(game.state, ring).types
        assert size(game, ring) == (4, 4)

    def test_it_does_not_wear_off_at_end_of_turn(self, builder):
        from commanderblitz.engine.primitives import clear_until_eot

        game, ring = position(builder, "sol_ring")
        resolve(game, ring)
        clear_until_eot(game.state)
        assert "Creature" in chars(game.state, ring).types
        assert size(game, ring) == (4, 4)


class TestAVehicle:
    def test_it_keeps_its_printed_size(self, builder):
        game, jack = position(builder, BLACKJACK)
        assert "Creature" not in chars(game.state, jack).types
        resolve(game, jack)
        assert "Creature" in chars(game.state, jack).types
        assert size(game, jack) == (3, 3), "a Vehicle is not made 4/4"

    def test_one_sized_by_its_maker_keeps_that_size(self, builder):
        game, jet = position(builder, AETHERJET)
        game.state.objects[jet].copy_overrides = {"power": 5, "toughness": 5}
        resolve(game, jet)
        assert size(game, jet) == (5, 5)

    def test_counters_still_add_to_it(self, builder):
        game, jack = position(builder, BLACKJACK)
        resolve(game, jack)
        game.state.objects[jack].counters["+1/+1"] = 2
        game.state.bump_chars()
        assert size(game, jack) == (5, 5)


def _card(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_animator", "name": "Bad Animator",
                "oracle_text": "Target artifact becomes an artifact creature.",
                "mana_cost": "{2}", "types": ["Sorcery"],
                "targets": [{"id": "t1", "kind": "permanent",
                             "selector": {"types": ["Artifact"]}}],
                "spell_effects": [{"op": "animate", "types": ["Creature"],
                                   "duration": "permanent", **effect}],
            }
        )
    )


class TestTheLoader:
    def test_a_target_narrowed_to_vehicles_compiles(self):
        _card({"objects": {"target": "t1", "subtypes": ["Vehicle"]}, "keep_pt": True})

    def test_an_unnarrowed_target_is_refused(self):
        with pytest.raises(DslError, match="keep_pt"):
            _card({"objects": {"target": "t1"}, "keep_pt": True})

    def test_a_target_narrowed_to_something_else_is_refused(self):
        with pytest.raises(DslError, match="keep_pt"):
            _card({"objects": {"target": "t1", "subtypes": ["Equipment"]}, "keep_pt": True})

    def test_a_size_beside_keep_pt_is_still_refused(self):
        with pytest.raises(DslError, match="keep_pt"):
            _card({"objects": {"target": "t1", "subtypes": ["Vehicle"]}, "keep_pt": True,
                   "power": {"const": 4}, "toughness": {"const": 4}})
