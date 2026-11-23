"""`becomes_crewed` — "Whenever this Vehicle becomes crewed" (702.122d).

702.122d: a Vehicle becomes crewed as **a crew ability of it resolves**, and
"whenever this Vehicle becomes crewed" triggers then. Mobilizer Mech is the
shipped witness ("Whenever this Vehicle becomes crewed, up to one other target
Vehicle you control becomes an artifact creature until end of turn"); Ghost Ark
waits on the same event.

What would be wrong without its own event, a class each:

`TestItFiresOnResolutionNotActivation`
    `ability_activated` fires as crew is *activated*. Crew uses the stack, so
    the opponent can answer it -- destroy the Vehicle -- and the trigger would
    already be waiting.

`TestWhateverCausedIt`
    Folding the trigger's effect into the crew ability's own effects would make
    it part of the crew's resolution rather than a triggered ability, and a copy
    of the crew ability resolving would not count as the Vehicle being crewed.

`TestOnlyCrewCrews`
    A crew ability is known by its cost (`Ability.is_crew`, ADR 0032): an
    animation that is not crew -- Mobilizer Mech's own trigger, aimed at
    another Vehicle -- does not crew it. The loader holds the converse, in
    `TestTheLoaderRefuses`: a `total_power` tap cost on anything but crew's
    printed shape is refused, so the marker cannot be borrowed.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, only_oid, settle

WATCHER = "t_crew_watcher"      # gains 2 life whenever it becomes crewed; crew 1
LIFTER = "t_vehicle_lifter"     # {1}: target Vehicle becomes an artifact creature
BEAR = "t_bear"                 # 2/2

#: Printed positions on the watcher.
W_TRIGGER, W_CREW = range(2)


def position(builder, *extra: str):
    """Player 0's main phase: the watcher, a Bear to crew it, and ``extra``.

    The opponent holds a Lightning Bolt beside a Mountain so the engine stops for
    a response rather than resolving the crew straight away.
    """
    game = (
        builder(players=2)
        .battlefield(0, [WATCHER, BEAR, *extra])
        .battlefield(0, ["plains"] * 2)
        .battlefield(1, ["mountain"])
        .hand(1, ["lightning_bolt"])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .build()
    )
    return game, only_oid(game, WATCHER)


def crew(game, vehicle: int) -> None:
    """Activate crew and tap the Bear for it, leaving the ability on the stack."""
    (action,) = activations(game, vehicle, W_CREW)
    game.apply(action)
    choose = next((a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None)
    if choose is not None:
        game.apply(choose)


def crewed(game) -> list:
    return [e for e in game.state.events if e.type == EventType.BECAME_CREWED]


class TestTheEvent:
    def test_crew_resolving_fires_it_for_the_vehicle(self, builder):
        game, vehicle = position(builder)
        crew(game, vehicle)
        settle(game)
        (event,) = crewed(game)
        assert event.source == vehicle and event.data["oid"] == vehicle
        assert event.player == 0

    def test_the_vehicle_is_a_creature_when_it_fires(self, builder):
        game, vehicle = position(builder)
        crew(game, vehicle)
        settle(game)
        assert "Creature" in chars(game.state, vehicle).types
        assert game.state.players[0].life == 42


class TestItFiresOnResolutionNotActivation:
    def test_nothing_triggers_while_crew_is_on_the_stack(self, builder):
        game, vehicle = position(builder)
        crew(game, vehicle)
        assert game.state.stack
        assert not game.state.pending_triggers
        assert crewed(game) == []

    def test_a_vehicle_gone_before_crew_resolves_is_not_crewed(self, builder):
        """400.7: the crew ability resolves, but there is no Vehicle to crew."""
        game, vehicle = position(builder)
        crew(game, vehicle)
        move_object(game.state, vehicle, Zone.GRAVEYARD)
        settle(game)
        assert crewed(game) == []
        assert game.state.players[0].life == 40


class TestWhateverCausedIt:
    def test_a_copy_of_the_crew_ability_crews_it_again(self, builder):
        """Each crew ability of the Vehicle that resolves crews it (702.122d),
        a copy included -- which a trigger folded into crew's effects would not
        be, since a copy is not the printed line being activated."""
        game, vehicle = position(builder)
        crew(game, vehicle)
        original = game.state.stack[-1]
        game.state.stack.append(replace(original, sid=game.state.alloc_sid()))
        settle(game)
        assert len(crewed(game)) == 2
        assert game.state.players[0].life == 44


class TestOnlyCrewCrews:
    def test_animating_a_vehicle_another_way_is_not_crewing_it(self, builder):
        game, vehicle = position(builder, LIFTER)
        lifter = only_oid(game, LIFTER)
        (action,) = next(
            [a] for a in activations(game, lifter) if vehicle in [t.id for t in a.targets]
        )
        game.apply(action)
        settle(game)
        assert "Creature" in chars(game.state, vehicle).types
        assert crewed(game) == []
        assert game.state.players[0].life == 40

    def test_the_crew_line_is_crew_and_the_trigger_is_not(self, builder):
        game, _ = position(builder)
        card = game.state.registry.get(WATCHER)
        assert card.abilities[W_CREW].is_crew
        assert not card.abilities[W_TRIGGER].is_crew

    def test_a_station_tap_cost_is_not_crew(self):
        """Station also taps a creature, but names it rather than summing power."""
        ability = compile_(_vehicle(effects=[_ANIMATE]))
        assert ability.abilities[0].is_crew
        station = compile_(
            {
                "id": "t_planet",
                "name": "Test Planet",
                "types": ["Artifact"],
                "subtypes": ["Planet"],
                "abilities": [
                    {
                        "kind": "activated",
                        "text": "Station",
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
                    }
                ],
            }
        )
        assert not station.abilities[0].is_crew


_ANIMATE = {
    "op": "animate",
    "keep_pt": True,
    "types": ["Creature"],
    "objects": {"zone": "battlefield", "self_only": True},
}


def _vehicle(*, effects: list) -> dict:
    return {
        "id": "t_crew_shape",
        "name": "Test Crew Shape",
        "types": ["Artifact"],
        "subtypes": ["Vehicle"],
        "power": 3,
        "toughness": 3,
        "abilities": [
            {
                "kind": "activated",
                "text": "Crew 2",
                "cost": {
                    "tap_permanents": {
                        "controller": "you",
                        "types": ["Creature"],
                        "total_power": 2,
                    }
                },
                "effects": effects,
            }
        ],
    }


def compile_(card: dict):
    return compile_card(CardModel.model_validate(card))


class TestTheLoaderRefuses:
    def test_a_total_power_cost_that_does_something_else(self):
        draw = {"op": "draw", "player": "you", "amount": {"const": 1}}
        with pytest.raises(DslError, match="crew's"):
            compile_(_vehicle(effects=[draw]))

    def test_crew_with_a_rider(self):
        draw = {"op": "draw", "player": "you", "amount": {"const": 1}}
        with pytest.raises(DslError, match="crew's"):
            compile_(_vehicle(effects=[_ANIMATE, draw]))

    def test_a_total_power_cost_animating_something_else(self):
        other = {
            "op": "animate",
            "power": {"const": 3},
            "toughness": {"const": 3},
            "types": ["Creature"],
            "objects": {"zone": "battlefield", "subtypes": ["Vehicle"]},
        }
        with pytest.raises(DslError, match="crew's"):
            compile_(_vehicle(effects=[other]))

