"""`auras_had` and `enchanted_by` on a departure -- the Auras a creature wore as it left.

"Whenever an enchanted creature dies, draw a card for each Aura you controlled
that was attached to it" (Hateful Eidolon). Leaves-the-battlefield abilities
look back in time (603.10a): both halves are asked about a creature that has
already left, and `zones._detach_all` has unattached every Aura before the
event goes out. Asked of the board, `enchanted_by: true` never matched a
departure and `false` always did, and a `count` of the Auras attached to it
reads graveyard cards at resolution -- the trigger would load and never fire,
or fire and draw nothing.

`zones.move_object` snapshots the Auras attached as the permanent leaves, one
seat per Aura, onto the departure event as `had_auras`, beside `had_counters`
and `had_power`; `characteristics.aura_controllers` is the one place an Aura is
told from another attachment, for the live reading and the snapshot alike. The
engine moves a simultaneous event's permanents one at a time, so an Aura that
left in the same event as its host is kept in `GameState.leaving_auras` for the
rest of the batch, as `leaving_dies_replacers` keeps Kalitas.

The witness is Hateful Eidolon. `t_ah_eidolon` is its trigger alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import only_oid, settle, static_probe
from tests.unit.attachments.test_bestow import bestow_onto

EIDOLON = "t_ah_eidolon"  # Hateful Eidolon's trigger alone
MOURNER = "t_ah_mourner"  # "whenever a creature that wasn't enchanted leaves, gain 1"
AURA = "t_eb_aura"  # Enchant creature, and nothing else
BEAR = "t_eb_bear"
CUB = "t_eb_cub"
GEAR = "t_plain_gear"  # an Equipment with nothing printed
SPIRIT = "t_bestower"  # bestow {5}{W}
PLAINS = "plains"
SWAMP = "swamp"


def position(builder, *, mine=(AURA, AURA), theirs=(), watcher=EIDOLON):
    """Player 1's Bear wearing every Aura in ``mine`` (player 0's) and ``theirs``
    (player 2's), beside player 1's bare Cub; player 0 has ``watcher``.

    Attached before the position advances, so the state-based action that bins
    an unattached Aura never sees one. Returns ``(game, bear, cub)``.
    """
    b = builder(players=3).battlefield(0, [watcher, *mine]).battlefield(1, [BEAR, CUB])
    if theirs:
        b.battlefield(2, list(theirs))
    for pid in range(3):
        b.library(pid, [SWAMP] * 20)
    game = b.active(0).step(Step.UNTAP).build(advance=False)
    bear, cub = only_oid(game, BEAR, 1), only_oid(game, CUB, 1)
    for pid in (0, 2):
        for oid in list(game.state.battlefield):
            obj = game.state.objects[oid]
            if obj.controller == pid and obj.def_id in (AURA, GEAR):
                assert attach(game.state, oid, bear)
    game._advance()
    return game, bear, cub


def hand(game, pid=0) -> int:
    return len(game.state.players[pid].hand)


def kill(game, oid) -> None:
    destroy(game.state, oid, cause="test")
    settle(game)


def departures(game, oid):
    return [
        e
        for e in game.state.events
        if e.type in (EventType.DIES, EventType.LEAVES_BATTLEFIELD) and e.data.get("oid") == oid
    ]


class TestTheSnapshot:
    def test_the_departure_carries_one_seat_per_aura(self, builder):
        game, bear, _ = position(builder, mine=(AURA, AURA), theirs=(AURA,))
        destroy(game.state, bear, cause="test")
        events = departures(game, bear)
        assert {e.type for e in events} == {EventType.DIES, EventType.LEAVES_BATTLEFIELD}
        for event in events:
            assert sorted(event.data["had_auras"]) == [0, 0, 2]

    def test_equipment_is_not_an_aura(self, builder):
        game, bear, _ = position(builder, mine=(AURA, GEAR))
        destroy(game.state, bear, cause="test")
        assert {tuple(e.data["had_auras"]) for e in departures(game, bear)} == {(0,)}

    def test_a_bare_creature_wore_nothing(self, builder):
        game, _, cub = position(builder)
        destroy(game.state, cub, cause="test")
        assert {tuple(e.data["had_auras"]) for e in departures(game, cub)} == {()}

    def test_an_aura_leaving_in_the_same_event_is_still_attached(self, builder):
        """A "destroy all nonland permanents" may reach the Aura first; within
        one simultaneous event its host still wore it (603.10a)."""
        game, bear, _ = position(builder, mine=(AURA,))
        destroy(game.state, only_oid(game, AURA, 0), cause="test")
        destroy(game.state, bear, cause="test")
        assert {tuple(e.data["had_auras"]) for e in departures(game, bear)} == {(0,)}

    def test_an_aura_that_left_in_an_earlier_event_is_not(self, builder):
        game, bear, _ = position(builder, mine=(AURA,))
        destroy(game.state, only_oid(game, AURA, 0), cause="test")
        game.state.event_batch += 1
        destroy(game.state, bear, cause="test")
        assert {tuple(e.data["had_auras"]) for e in departures(game, bear)} == {()}


class TestHatefulEidolon:
    def test_it_draws_for_each_aura_you_controlled(self, builder):
        """Two of player 0's Auras and one of player 2's: two cards."""
        game, bear, _ = position(builder, mine=(AURA, AURA), theirs=(AURA,))
        before = hand(game)
        kill(game, bear)
        assert hand(game) == before + 2

    def test_an_opponents_aura_alone_triggers_and_draws_nothing(self, builder):
        """"An enchanted creature" is anybody's Aura; "each Aura you controlled"
        is player 0's only."""
        game, bear, _ = position(builder, mine=(), theirs=(AURA,))
        before = hand(game)
        destroy(game.state, bear, cause="test")
        assert game.state.pending_triggers
        settle(game)
        assert hand(game) == before

    def test_a_bare_creature_does_not_trigger_it(self, builder):
        game, _, cub = position(builder)
        destroy(game.state, cub, cause="test")
        assert not game.state.pending_triggers

    def test_a_bounce_is_not_a_death(self, builder):
        game, bear, _ = position(builder)
        move_object(game.state, bear, Zone.HAND)
        assert not game.state.pending_triggers

    def test_a_bestowed_creature_was_an_aura(self, builder):
        """702.103a: an Aura while attached; 702.103f makes it a creature again
        once its host leaves, and the snapshot is taken before that."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 8)
            .battlefield(0, [EIDOLON, "t_bear"])
            .hand(0, [SPIRIT])
            .library(0, [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        bear = only_oid(game, "t_bear", 0)
        bestow_onto(game, bear)
        before = hand(game)
        kill(game, bear)
        assert hand(game) == before + 1


class TestEnchantedByOnADeparture:
    def test_false_is_a_creature_that_wore_nothing(self, builder):
        game, bear, cub = position(builder, watcher=MOURNER)
        life = game.state.players[0].life
        kill(game, bear)
        assert game.state.players[0].life == life
        kill(game, cub)
        assert game.state.players[0].life == life + 1


class TestTheValue:
    def ctx(self, game, controller, had):
        return EffectContext(
            game.state, controller=controller, source_oid=None, bindings={"had_auras": had}
        )

    @pytest.mark.parametrize(
        ("spec", "controller", "expected"),
        [
            (True, 0, 3),
            ({"controller": "any"}, 0, 3),
            ({"controller": "you"}, 0, 2),
            ({"controller": "opponent"}, 0, 1),
            ({"controller": "you"}, 2, 1),
            ({"controller": "you"}, 1, 0),
        ],
    )
    def test_whose_auras_are_read_from_the_abilitys_controller(
        self, builder, spec, controller, expected
    ):
        game, *_ = position(builder)
        assert evaluate_value(self.ctx(game, controller, [0, 0, 2]), {"auras_had": spec}) == expected

    def test_a_trigger_that_never_fired_reads_zero(self, builder):
        game, *_ = position(builder)
        ctx = EffectContext(game.state, controller=0, source_oid=None)
        assert evaluate_value(ctx, {"auras_had": True}) == 0


def _compile(amount) -> None:
    ability = {
        "kind": "triggered",
        "text": "Probe.",
        "trigger": {"event": "creature_dies", "controller": "any"},
        "effects": [{"op": "draw", "amount": amount}],
    }
    compile_card(CardModel.model_validate(static_probe({}) | {"abilities": [ability]}))


class TestTheLoader:
    @pytest.mark.parametrize(
        ("spec", "message"),
        [
            (False, "false counts nothing"),
            ("you", "true, or a filter on the Auras"),
            ({}, "true, or a filter on the Auras"),
            ({"types": ["Enchantment"]}, "are not recorded of the Auras"),
            ({"controller": "enchanted_player"}, "auras_had.controller"),
        ],
    )
    def test_a_malformed_value_is_refused(self, spec, message):
        with pytest.raises(DslError, match=message):
            _compile({"auras_had": spec})

    @pytest.mark.parametrize("event", ["creature_dies", "dies", "leaves_battlefield", "sacrificed"])
    def test_enchanted_by_loads_on_a_departure_trigger(self, event):
        ability = {
            "kind": "triggered",
            "text": "Probe.",
            "trigger": {"event": event, "controller": "any", "filter": {"enchanted_by": True}},
            "effects": [{"op": "draw", "amount": {"auras_had": {"controller": "you"}}}],
        }
        compile_card(CardModel.model_validate(static_probe({}) | {"abilities": [ability]}))
