"""Protection from each colour outside your commander's color identity.

    Commander's Plate — "Equipped creature gets +3/+3 and has protection from
    each color that's not in your commander's color identity. Equip commander
    {3}. Equip {5}"

The `protection` static took its colours as a printed list and nothing else, and
this set is not printable: it is the five colours *minus* a set read off the
commanders of whoever controls the Plate. A mono-black general makes it
protection from white, blue, red and green; a Bant pair makes it red and black.
Any fixed list is one of those decks and wrong for the other ninety-nine.

So the static carries `from_colors_outside_commander_identity`, and
`protection_from` computes the set at the moment protection is read — which
makes the three things that can change it change it: whose Plate it is (control
of the Equipment, not of the creature: "your" is the Plate's controller), which
commanders that player has (partners are a union), and nothing else. Colour
identity is printed and zone-independent (903.4), so a commander in the command
zone, on the battlefield or in a graveyard gives the same answer.

No commander at all is protection from all five. 903.4 makes a card that asks
about a commander nobody has see an identity with no colours, and every colour
is "not in" an empty set. A colourless general is the same case by a different
route, and Commander's Plate on a Kozilek deck is famously protection from
everything coloured.

The four rules that read protection — damage, enchant/equip, block, target — go
through `protection_from`, so they need nothing: one of them is exercised end to
end here (a red spell cannot target the equipped creature) to hold that down.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import AbilityModel, CardModel
from automtg.engine.characteristics import (
    chars,
    commander_color_identity,
    protection_from,
)
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.primitives import attach, change_control

PLATE = "t_plate_probe"
BEAR = "t_bear"
BLACK = "t_plate_general_b"
AZORIUS = "t_plate_general_wu"
COLORLESS = "t_plate_general_colorless"
RED_BOLT = "t_plate_red_bolt"
BLACK_BOLT = "t_plate_black_bolt"
ALL = frozenset("WUBRG")


def position(builder, *, commanders=(BLACK,), hand=(), lands=(), players: int = 2):
    """You control a Plate and a Bear; `commanders` wait in your command zone.

    Frozen (`advance=False`) unless you hold lands to play with: the tests that
    read protection directly want the board exactly as described, and the ones
    that read `legal_actions` need the engine to have reached your main phase.
    """
    b = builder(players=players).battlefield(0, [PLATE, BEAR])
    if commanders:
        b = b.commander(0, list(commanders))
    if lands:
        b = b.battlefield(0, list(lands))
    if hand:
        b = b.hand(0, list(hand))
    for pid in range(players):
        b = b.library(pid, ["mountain"] * 10)
    game = b.build(advance=bool(lands))
    state = game.state
    plate = next(o.oid for o in state.battlefield_objects(0) if o.def_id == PLATE)
    bear = next(o.oid for o in state.battlefield_objects(0) if o.def_id == BEAR)
    return game, plate, bear


def equipped(builder, **kw):
    game, plate, bear = position(builder, **kw)
    assert attach(game.state, plate, bear)
    game.state.bump_chars()
    return game, plate, bear


class TestTheColourSet:
    def test_a_mono_black_commander_leaves_the_other_four(self, builder):
        game, _, bear = equipped(builder, commanders=(BLACK,))
        assert protection_from(game.state, bear) == frozenset("WURG")

    def test_partners_are_a_union(self, builder):
        """"Your commander's color identity" across two commanders is one
        identity: W, U and B are all inside it."""
        game, _, bear = equipped(builder, commanders=(BLACK, AZORIUS))
        assert protection_from(game.state, bear) == frozenset("RG")

    def test_no_commander_is_protection_from_all_five(self, builder):
        game, _, bear = equipped(builder, commanders=())
        assert commander_color_identity(game.state, 0) == frozenset()
        assert protection_from(game.state, bear) == ALL

    def test_a_colourless_commander_is_all_five_too(self, builder):
        game, _, bear = equipped(builder, commanders=(COLORLESS,))
        assert protection_from(game.state, bear) == ALL

    def test_the_buff_rides_along(self, builder):
        game, _, bear = position(builder)
        before = chars(game.state, bear)
        game, _, bear = equipped(builder)
        after = chars(game.state, bear)
        assert (after.power, after.toughness) == (before.power + 3, before.toughness + 3)


class TestWhereItIsRead:
    def test_only_the_equipped_creature(self, builder):
        game, _, bear = position(builder)
        assert protection_from(game.state, bear) == frozenset(), "unequipped"

    def test_the_commander_s_zone_does_not_matter(self, builder):
        """Identity is printed (903.4): a general that has left the command zone
        is still the same colours."""
        game, _, bear = equipped(builder, commanders=(BLACK,))
        general = game.state.players[0].commanders[0]
        game.state.objects[general].zone = game.state.objects[bear].zone
        assert protection_from(game.state, bear) == frozenset("WURG")

    def test_your_means_the_plate_s_controller(self, builder):
        """Hand the Plate to an opponent with no commander and the same creature
        is now protected from all five -- the identity followed the Equipment."""
        game, plate, bear = equipped(builder, commanders=(BLACK,))
        change_control(game.state, plate, 1)
        game.state.bump_chars()
        assert protection_from(game.state, bear) == ALL

    def test_not_the_equipped_creature_s_controller(self, builder):
        """Steal the creature instead: the Plate is still yours, so still your
        general's identity decides."""
        game, _, bear = equipped(builder, commanders=(BLACK,))
        change_control(game.state, bear, 1)
        game.state.bump_chars()
        assert protection_from(game.state, bear) == frozenset("WURG")

    def test_the_opponent_s_commander_is_not_yours(self, builder):
        game, _, bear = position(builder, commanders=())
        game_state = game.state
        # An Azorius general in the *opponent's* command zone changes nothing.
        from automtg.engine.enums import Zone
        from automtg.engine.state import new_object

        theirs = new_object(game_state, AZORIUS, owner=1, zone=Zone.COMMAND, is_commander=True)
        game_state.players[1].command.append(theirs.oid)
        game_state.players[1].commanders.append(theirs.oid)
        plate = next(o.oid for o in game_state.battlefield_objects(0) if o.def_id == PLATE)
        attach(game_state, plate, bear)
        game_state.bump_chars()
        assert protection_from(game_state, bear) == ALL


class TestTheRulesThatReadIt:
    def _targets_of(self, game, card_id):
        return {
            ref.id
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
            for ref in a.targets
            if ref.kind == "object"
        }

    def test_a_colour_outside_the_identity_cannot_target_it(self, builder):
        game, _, bear = position(
            builder, commanders=(BLACK,), hand=(RED_BOLT, BLACK_BOLT), lands=("mountain", "swamp")
        )
        assert bear in self._targets_of(game, RED_BOLT), "before the Plate"
        plate = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == PLATE)
        attach(game.state, plate, bear)
        game.state.bump_chars()
        assert bear not in self._targets_of(game, RED_BOLT), "red is outside mono-black"
        assert bear in self._targets_of(game, BLACK_BOLT), "black is inside it"


class TestTheEquipLines:
    def test_equip_commander_reaches_only_a_commander(self, builder):
        game, plate, bear = position(builder, commanders=(BLACK,), lands=["mountain"] * 5)
        from automtg.engine.enums import Zone

        general = game.state.players[0].commanders[0]
        game.state.players[0].command.remove(general)
        game.state.objects[general].zone = Zone.BATTLEFIELD
        game.state.battlefield.append(general)
        game.state.bump_chars()
        activations = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == plate
        ]
        by_line = {}
        for a in activations:
            by_line.setdefault(a.ability_index, set()).update(r.id for r in a.targets)
        assert by_line[2] == {general}, "Equip commander {3}"
        assert by_line[3] == {general, bear}, "Equip {5}"


class TestTheLoader:
    def _static(self, **extra) -> dict:
        return {
            "kind": "static",
            "text": "protection",
            "effect": "protection",
            "affects": {"attached": True},
            **extra,
        }

    def _card(self, *abilities) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_plate_loader_probe",
                "name": "Test Plate Loader Probe",
                "oracle_text": "protection",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "subtypes": ["Equipment"],
                "abilities": list(abilities),
            }
        )

    def test_the_flag_alone_is_a_quality(self):
        card = compile_card(self._card(self._static(from_colors_outside_commander_identity=True)))
        static = card.abilities[0].static
        assert static["from_colors_outside_commander_identity"] is True
        assert "from_colors" not in static

    def test_with_a_printed_list_it_is_refused(self):
        with pytest.raises(DslError, match="whole colour set"):
            compile_card(
                self._card(
                    self._static(from_colors_outside_commander_identity=True, from_colors=["B"])
                )
            )

    def test_on_anything_but_protection_it_is_refused(self):
        ability = {
            "kind": "static",
            "text": "protection",
            "effect": "buff",
            "power": 1,
            "toughness": 1,
            "affects": {"attached": True},
            "from_colors_outside_commander_identity": True,
        }
        with pytest.raises(DslError, match="need effect 'protection'"):
            compile_card(self._card(ability))

    def test_false_is_not_a_quality(self):
        with pytest.raises(DslError, match="protection needs"):
            compile_card(self._card(self._static(from_colors_outside_commander_identity=False)))

    def test_the_schema_names_it(self):
        assert "from_colors_outside_commander_identity" in AbilityModel.model_fields
