"""A mass `animate` that keeps each Vehicle's own size.

Armed and Armored: *"Vehicles you control become artifact creatures until end
of turn."*

**301.7, why the pool names no size.** A Vehicle prints a power and toughness
that it has only while it is a creature; when it becomes one, those are its
base values. A sized animation would make every Vehicle the same size, and a
Vehicle sized by the effect that made it (the X/X Nalaar Aetherjet, 111.4)
answers differently from one that printed its size. So the card writes one
`keep_pt` animation over a selector narrowed to `subtypes: ["Vehicle"]`.

**Why the loader still refuses a wider pool.** `keep_pt` on a pool that can
reach a permanent with no printed size would make a 0/0 that 704.5f bins. A
selector narrowed to Vehicles reaches only permanents that print one, the
same guarantee a target narrowed that way gives
(`test_animate_target_keep_pt.py`). An unnarrowed selector, and a binding,
whose contents another effect's filter chose, are refused.
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
from commanderblitz.engine.primitives import clear_until_eot
from tests.conftest import only_oid

BLACKJACK = "the_blackjack_3_3_c_flying_crew2"
AETHERJET = "nalaar_aetherjet_x_x_c_flying_crew2"

#: Armed and Armored's first sentence, as the card writes it.
VEHICLES_ANIMATE = [
    {
        "op": "animate",
        "objects": {"zone": "battlefield", "controller": "you", "subtypes": ["Vehicle"]},
        "types": ["Artifact", "Creature"],
        "keep_pt": True,
    }
]


def position(builder):
    """Player 0 with a Blackjack, an Aetherjet sized 5/5 and a Sol Ring;
    player 1 with a Blackjack of their own."""
    game = (
        builder(players=2)
        .battlefield(0, [BLACKJACK, AETHERJET, "sol_ring"])
        .battlefield(1, [BLACKJACK])
        .build(advance=False)
    )
    jet = only_oid(game, AETHERJET, 0)
    game.state.objects[jet].copy_overrides = {"power": 5, "toughness": 5}
    game.state.bump_chars()
    return game


def resolve(game) -> None:
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, VEHICLES_ANIMATE)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def size(game, oid: int) -> tuple[int | None, int | None]:
    c = chars(game.state, oid)
    return c.power, c.toughness


class TestEveryVehicleYouControl:
    def test_each_becomes_a_creature_at_its_own_size(self, builder):
        game = position(builder)
        jack, jet = only_oid(game, BLACKJACK, 0), only_oid(game, AETHERJET, 0)
        resolve(game)
        assert {"Artifact", "Creature"} <= chars(game.state, jack).types
        assert {"Artifact", "Creature"} <= chars(game.state, jet).types
        assert size(game, jack) == (3, 3)
        assert size(game, jet) == (5, 5), "one sized by its maker keeps that size"

    def test_it_wears_off_at_end_of_turn(self, builder):
        game = position(builder)
        jack = only_oid(game, BLACKJACK, 0)
        resolve(game)
        clear_until_eot(game.state)
        assert "Creature" not in chars(game.state, jack).types


class TestWhatItDoesNotReach:
    def test_a_non_vehicle_artifact_stays_a_non_creature(self, builder):
        game = position(builder)
        ring = only_oid(game, "sol_ring", 0)
        resolve(game)
        assert "Creature" not in chars(game.state, ring).types

    def test_an_opponents_vehicle_stays_a_non_creature(self, builder):
        game = position(builder)
        theirs = only_oid(game, BLACKJACK, 1)
        resolve(game)
        assert "Creature" not in chars(game.state, theirs).types


def _card(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_animator", "name": "Bad Animator",
                "oracle_text": "Vehicles you control become artifact creatures until end of turn.",
                "mana_cost": "{2}", "types": ["Sorcery"],
                "spell_effects": [{"op": "animate", "types": ["Artifact", "Creature"],
                                   **effect}],
            }
        )
    )


class TestTheLoader:
    def test_a_selector_narrowed_to_vehicles_compiles(self):
        _card({"objects": {"zone": "battlefield", "controller": "you",
                           "subtypes": ["Vehicle"]}, "keep_pt": True})

    def test_an_unnarrowed_selector_is_refused(self):
        with pytest.raises(DslError, match="keep_pt"):
            _card({"objects": {"zone": "battlefield", "controller": "you",
                               "types": ["Artifact"]}, "keep_pt": True})

    def test_a_binding_is_refused_even_narrowed(self):
        with pytest.raises(DslError, match="keep_pt"):
            _card({"objects": {"binding": "found", "subtypes": ["Vehicle"]},
                   "keep_pt": True})
