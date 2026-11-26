"""Station on a Spacecraft -- gated triggers and statics, and the creature at its number.

    Rule 721: a station symbol means "As long as this permanent has N or more
    charge counters on it, it has [abilities]." Nothing in the rule limits the
    abilities to activated ones, and a Spacecraft prints all three kinds.

    Rule 721.2b: a station symbol with a P/T box means "as long as this
    permanent has N or more charge counters on it, it's an artifact creature
    with base power and toughness P/T." Below that number it is a noncreature
    artifact, which has no power or toughness (208.3).

The witnesses are the Edge of Eternities and Star Trek Spacecraft:

    U.S.S. Prometheus -- "4+ | Flying" and "8+ | Multivector Assault Mode —
    Whenever U.S.S. Prometheus deals combat damage to an opponent, …"; an
    artifact creature at 4+.
    Uthros Research Craft -- "3+ | Whenever you cast an artifact spell, draw a
    card. …" and "12+ | … This Spacecraft gets +1/+0 for each artifact you
    control."
    Exploration Broodship -- "3+ | You may play an additional land on each of
    your turns."

`t_spacecraft` is their shape: a 4/6 whose P/T box sits at 5+, with a 3+
trigger, a 3+ player static, a "5+ | Flying, hexproof" line and an 8+ buff.

What would be wrong without each piece:

- A gated trigger read off the printed face would draw a card off every artifact
  spell from turn one. Below its number it is not collected at all; once on the
  stack it resolves whatever happens to the counters (113.7a).
- A keyword line is a gated `grant_keyword` on `self_only`, so it switches with
  the static gate. Written as a printed keyword it would be on for ever.
- A static read off the printed face (the player statics walk) would give the
  extra land drop with no counters; it asks `Ability.present_on` too.
- Without the box the Spacecraft is either always a creature -- attackable,
  Wrath-able, a 4/6 blocker on turn three -- or never one.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.authoring.verify import residual_text
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import abilities_of, chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_extra_land_drops
from commanderblitz.engine.primitives import add_counters, remove_counters
from tests.conftest import (
    action_for_card,
    activations,
    keywords,
    only_oid,
    pass_until,
    pt,
    settle,
)

SHIP = "t_spacecraft"
STATION, DRAW_TRIGGER, LAND_DROP, FLYING_LINE, BUFF_LINE = range(5)


def position(builder, charge: int, *, hand=(), lands=(), creatures=("t_bear",), respond=False):
    """The Spacecraft with ``charge`` counters, and what the test needs beside it.

    ``respond`` hands the opponent a castable Bolt, so a window with a trigger on
    the stack is a real one rather than passed automatically.
    """
    b = (
        builder(players=2)
        .battlefield(0, [SHIP], counters={"charge": charge} if charge else None)
        .battlefield(0, list(lands))
        .battlefield(0, list(creatures))
        .hand(0, list(hand))
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
    )
    if respond:
        b = b.hand(1, ["t_bolt"]).battlefield(1, ["mountain"])
    game = b.build()
    return game, only_oid(game, SHIP)


def indices(game, oid: int) -> list[int]:
    return [a.index for a in abilities_of(game.state, oid)]


def cast_sol_ring(game) -> int:
    """Cast the Sol Ring in hand; the hand size before the cast."""
    before = len(game.state.players[0].hand)
    game.apply(action_for_card(game, ActionKind.CAST, "sol_ring"))
    return before - 1


class TestAGatedTrigger:
    def test_below_its_number_it_never_triggers(self, builder):
        game, _ship_oid = position(builder, 2, hand=["sol_ring"], lands=["island"])
        after_cast = cast_sol_ring(game)
        settle(game)
        assert len(game.state.players[0].hand) == after_cast

    def test_at_its_number_it_triggers(self, builder):
        game, _ship_oid = position(builder, 3, hand=["sol_ring"], lands=["island"])
        after_cast = cast_sol_ring(game)
        settle(game)
        assert len(game.state.players[0].hand) == after_cast + 1

    def test_on_the_stack_it_resolves_after_the_counters_are_gone(self, builder):
        """113.7a: once triggered it is independent of its source."""
        game, ship = position(builder, 3, hand=["sol_ring"], lands=["island"], respond=True)
        after_cast = cast_sol_ring(game)
        pass_until(game, lambda g: len(g.state.stack) == 2)
        assert game.state.stack[-1].ability_index == DRAW_TRIGGER

        remove_counters(game.state, ship, "charge", 3)
        assert DRAW_TRIGGER not in indices(game, ship)
        settle(game)

        assert len(game.state.players[0].hand) == after_cast + 1


class TestAGatedKeyword:
    def test_below_its_number_it_has_neither_keyword(self, builder):
        game, ship = position(builder, 4)
        assert not {"flying", "hexproof"} & keywords(game, ship)

    def test_at_its_number_it_has_both(self, builder):
        game, ship = position(builder, 5)
        assert {"flying", "hexproof"} <= keywords(game, ship)

    def test_counters_leaving_take_them_away(self, builder):
        game, ship = position(builder, 5)
        remove_counters(game.state, ship, "charge", 1)
        assert not {"flying", "hexproof"} & keywords(game, ship)

    def test_counters_arriving_switch_them_on(self, builder):
        game, ship = position(builder, 4)
        add_counters(game.state, ship, "charge", 1)
        assert {"flying", "hexproof"} <= keywords(game, ship)


class TestAGatedStatic:
    def test_a_buff_switches_on_at_its_number(self, builder):
        game, ship = position(builder, 7)
        assert pt(game, ship) == (4, 6)
        add_counters(game.state, ship, "charge", 1)
        assert pt(game, ship) == (6, 6)

    def test_a_buff_switches_off_when_counters_leave(self, builder):
        game, ship = position(builder, 8)
        remove_counters(game.state, ship, "charge", 1)
        assert pt(game, ship) == (4, 6)

    def test_a_player_static_read_off_the_printed_face_is_gated_too(self, builder):
        """The player statics walk printed faces; it asks `present_on`."""
        game, ship = position(builder, 2)
        assert player_extra_land_drops(game.state, 0) == 0
        add_counters(game.state, ship, "charge", 1)
        assert player_extra_land_drops(game.state, 0) == 1
        remove_counters(game.state, ship, "charge", 3)
        assert player_extra_land_drops(game.state, 0) == 0

    def test_the_gated_abilities_keep_their_printed_seats(self, builder):
        game, ship = position(builder, 5)
        assert indices(game, ship) == [STATION, DRAW_TRIGGER, LAND_DROP, FLYING_LINE]


class TestBelowItsNumberItIsANoncreatureArtifact:
    def test_it_has_no_creature_type_and_no_power_or_toughness(self, builder):
        game, ship = position(builder, 4)
        c = chars(game.state, ship)
        assert "Creature" not in c.types and "Artifact" in c.types
        assert "Spacecraft" in c.subtypes
        assert (c.power, c.toughness) == (0, 0)

    def test_it_cannot_attack(self, builder):
        game, ship = position(builder, 4)
        pass_until(game, lambda g: g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        attackers = {a.source for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER}
        assert ship not in attackers and attackers, "the Bear should still be offered"

    def test_creature_removal_does_not_touch_it(self, builder):
        game, ship = position(builder, 4, hand=["wrath_of_god"], lands=["plains"] * 4)
        game.apply(action_for_card(game, ActionKind.CAST, "wrath_of_god"))
        settle(game)
        assert ship in game.state.battlefield

    def test_a_card_off_the_battlefield_is_a_noncreature_artifact_card(self, builder):
        game = builder(players=2).hand(0, [SHIP]).build()
        card = game.state.players[0].hand[0]
        assert "Creature" not in chars(game.state, card).types


class TestAtItsNumberItIsAnArtifactCreature:
    def test_it_is_an_artifact_creature_with_its_printed_size(self, builder):
        game, ship = position(builder, 5)
        c = chars(game.state, ship)
        assert {"Artifact", "Creature"} <= c.types
        assert (c.power, c.toughness) == (4, 6)

    def test_it_can_attack(self, builder):
        game, ship = position(builder, 5)
        pass_until(game, lambda g: g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        assert ship in {a.source for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER}

    def test_creature_removal_destroys_it(self, builder):
        game, ship = position(builder, 5, hand=["wrath_of_god"], lands=["plains"] * 4)
        game.apply(action_for_card(game, ActionKind.CAST, "wrath_of_god"))
        settle(game)
        assert ship not in game.state.battlefield

    def test_counters_leaving_make_it_a_noncreature_again(self, builder):
        game, ship = position(builder, 5)
        remove_counters(game.state, ship, "charge", 1)
        assert "Creature" not in chars(game.state, ship).types
        assert pt(game, ship) == (0, 0)

    def test_stationing_to_the_number_makes_the_creature(self, builder):
        """End to end: Station with a 6/6 puts six counters on it."""
        game, ship = position(builder, 0, creatures=["t_big"])
        game.apply(activations(game, ship, STATION)[0])
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[ship].counter("charge") == 6
        assert {"Artifact", "Creature"} <= chars(game.state, ship).types
        assert {"flying", "hexproof"} <= keywords(game, ship)


def _ship(**changes) -> dict:
    card = copy.deepcopy(
        {
            "id": "t_ship_guard",
            "name": "Test Ship Guard",
            "oracle_text": (
                "Station (Tap another creature you control: Put charge counters equal to "
                "its power on this Spacecraft. Station only as a sorcery. It's an artifact "
                "creature at 4+.)\n4+ | Flying"
            ),
            "types": ["Artifact"],
            "subtypes": ["Spacecraft"],
            "power": 3,
            "toughness": 3,
            "station": 4,
            "abilities": [
                {
                    "kind": "activated",
                    "text": (
                        "Station (Tap another creature you control: Put charge counters "
                        "equal to its power on this Spacecraft. Station only as a sorcery. "
                        "It's an artifact creature at 4+.)"
                    ),
                    "cost": {
                        "tap_permanents": {
                            "types": ["Creature"],
                            "exclude_self": True,
                            "as": "stationed",
                        }
                    },
                    "sorcery_speed_only": True,
                    "effects": [
                        {
                            "op": "add_counters",
                            "counter": "charge",
                            "amount": {"power_of": {"binding": "stationed"}},
                            "objects": {"self_only": True},
                        }
                    ],
                },
                {
                    "kind": "static",
                    "text": "4+ | Flying",
                    "threshold": {"counter": "charge", "at_least": 4},
                    "effect": "grant_keyword",
                    "keywords": ["flying"],
                    "affects": {"self_only": True},
                },
            ],
        }
    )
    card.update(changes)
    return card


def _load(card: dict):
    return compile_card(CardModel.model_validate(card))


class TestLoadTimeGuards:
    def test_the_printed_shape_loads(self):
        card = _load(_ship())
        assert card.station == 4
        assert card.abilities[1].threshold == ("charge", 4)

    def test_a_card_without_the_field_has_no_box(self, registry):
        assert registry.get("t_station_planet").station == 0

    def test_a_box_at_a_number_no_line_prints_is_refused(self):
        with pytest.raises(DslError, match="one of the card's own"):
            _load(_ship(station=5))

    def test_a_box_on_a_printed_creature_is_refused(self):
        with pytest.raises(DslError, match="noncreature artifact"):
            _load(_ship(types=["Artifact", "Creature"]))

    def test_a_box_with_no_printed_size_is_refused(self):
        with pytest.raises(DslError, match="power and toughness"):
            _load(_ship(power=None, toughness=None))

    @pytest.mark.parametrize("bad", [0, -1, True, "4"])
    def test_a_box_that_is_not_a_whole_number_is_refused(self, bad):
        with pytest.raises(DslError, match="whole number"):
            _load(_ship(station=bad))

    def test_a_spacecraft_that_forgets_its_box_is_refused(self):
        """Printed P/T beside striations, and no field: it would never be a creature."""
        card = _ship()
        del card["station"]
        with pytest.raises(DslError, match="write 'station'"):
            _load(card)

    def test_a_gated_static_before_an_ungated_one_is_refused(self):
        """The suffix rule holds for every kind, not only activated abilities."""
        card = _ship()
        card["abilities"].reverse()
        with pytest.raises(DslError, match="gated abilities come last"):
            _load(card)

    def test_a_gated_leaves_the_battlefield_trigger_is_refused(self):
        """It would read the counters of a card that has none (603.10a)."""
        card = _ship()
        card["abilities"].append(
            {
                "kind": "triggered",
                "text": "4+ | When this Spacecraft dies, draw a card.",
                "threshold": {"counter": "charge", "at_least": 4},
                "trigger": {"event": "dies", "source": "self"},
                "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
            }
        )
        with pytest.raises(DslError, match="leaves-the-battlefield"):
            _load(card)

    def test_a_gated_ability_off_the_battlefield_is_refused(self):
        card = _ship()
        card["abilities"][1]["active_zones"] = ["graveyard"]
        with pytest.raises(DslError, match="battlefield only"):
            _load(card)


class TestTheResidualGate:
    def test_the_spacecraft_claims_every_line(self, registry):
        card = registry.get(SHIP)
        assert residual_text(card, card.oracle_text).strip() == ""

    def test_the_reminder_is_claimed_only_at_the_boxs_own_number(self):
        """Station's "It's an artifact creature at 4+" is the field's, not the cost's."""
        card = _ship()
        card["abilities"][1]["threshold"]["at_least"] = 2
        card["abilities"][1]["text"] = "4+ | Flying"
        card["station"] = 2
        loaded = _load(card)
        assert "Station" in residual_text(loaded, loaded.oracle_text)
