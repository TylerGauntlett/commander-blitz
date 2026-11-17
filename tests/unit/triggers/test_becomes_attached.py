""""Whenever an Aura you control becomes attached to a creature you control" --
the `becomes_attached` trigger.

Rule 701.3a: an Aura, Equipment or Fortification *becomes attached* each time
it is put onto an object -- an Aura spell resolving onto its target, an Aura
entering the battlefield attached (303.4f), an equip or an `attach` moving it.
Every one of those goes through `primitives.attach` (or `attach_to_player`),
which has always fired `EventType.ATTACHED`; what it had was no name in
`TRIGGER_EVENTS`, so no card could listen. 701.3b is the boundary: attaching an
Aura or Equipment to the object it is already attached to does nothing, so it
is not a second "becomes attached", and staying attached is not one at all.

The trigger names **two** objects, and getting either wrong is a different
card. The subject is the attachment (`filter`, `controller`), and the host is
the filter's `attached_to`, asked of the permanent the event names. Without the
host half, Siona, Captain of the Pyleas -- the witness -- makes a Soldier when
her controller's Aura lands on an opponent's creature; without the attachment
half, she makes one off an opponent's Aura on her controller's creature.
`permanent_enters` with an Aura filter, the near miss, could say neither and
misses every equip and every moved Aura besides.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, attach_to_player
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, count_on_battlefield, only_oid, settle_completely

CAPTAIN = "t_ba_siona"
HOUND = "t_ba_hound"
AURA = "t_ba_aura"
GEAR = "t_ba_gear"
BEAR = "t_ba_bear"
SOLDIER = "human_soldier_1_1_w"


def board(builder, mine=(), theirs=(), hand=()):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["forest"] * 20)
        .build(advance=False)
    )
    return game


def settle(game) -> None:
    """Offer priority, then let every trigger reach the stack and resolve.

    The board is built without advancing, so an Aura placed on the battlefield
    unattached is not binned by 704.5m before the test attaches it; the
    `_advance` here is what the attach would otherwise wait on.
    """
    game._advance()
    settle_completely(game)


def in_hand(game, card_id: str) -> int:
    return next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)


def soldiers(game) -> int:
    return count_on_battlefield(game, SOLDIER, 0)


def cast_aura_on(game, host: int) -> None:
    game._advance()
    aura = in_hand(game, AURA)
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and a.source == aura
            and tuple(a.targets) == (TargetRef.obj(host),)
        )
    )
    settle(game)


class TestAnAuraBecomingAttached:
    def test_casting_an_aura_onto_your_creature_makes_a_soldier(self, builder):
        game = board(builder, [CAPTAIN, BEAR], hand=[AURA])
        cast_aura_on(game, only_oid(game, BEAR))
        assert only_oid(game, AURA) in game.state.battlefield
        assert soldiers(game) == 1

    def test_an_aura_entering_attached_makes_a_soldier(self, builder):
        """303.4f: an Aura put onto the battlefield without being cast enters
        attached -- no spell, no target, the same event."""
        game = board(builder, [CAPTAIN, BEAR], hand=[AURA])
        aura = in_hand(game, AURA)
        game.state.objects[aura].enters_attached_to = only_oid(game, BEAR)
        move_object(game.state, aura, Zone.BATTLEFIELD)
        settle(game)
        assert game.state.objects[aura].attached_to == only_oid(game, BEAR)
        assert soldiers(game) == 1

    def test_moving_an_aura_to_another_creature_fires_again(self, builder):
        game = board(builder, [CAPTAIN, BEAR, HOUND, AURA])
        aura, bear, hound = only_oid(game, AURA), only_oid(game, BEAR), only_oid(game, HOUND)
        attach(game.state, aura, bear)
        attach(game.state, aura, hound)
        settle(game)
        assert soldiers(game) == 2


class TestBothObjectsAreAsked:
    def test_your_aura_on_an_opponents_creature_is_not_it(self, builder):
        """The host half: "a creature **you** control"."""
        game = board(builder, [CAPTAIN], theirs=[BEAR], hand=[AURA])
        cast_aura_on(game, only_oid(game, BEAR))
        assert only_oid(game, AURA) in game.state.battlefield
        assert soldiers(game) == 0

    def test_an_opponents_aura_on_your_creature_is_not_it(self, builder):
        """The attachment half: "an Aura **you** control"."""
        game = board(builder, [CAPTAIN, BEAR], theirs=[AURA])
        attach(game.state, only_oid(game, AURA), only_oid(game, BEAR))
        settle(game)
        assert soldiers(game) == 0

    def test_an_equipment_is_not_an_aura(self, builder):
        game = board(builder, [CAPTAIN, BEAR, GEAR])
        attach(game.state, only_oid(game, GEAR), only_oid(game, BEAR))
        settle(game)
        assert soldiers(game) == 0

    def test_an_aura_put_onto_a_player_has_no_creature_host(self, builder):
        game = board(builder, [CAPTAIN, AURA])
        assert attach_to_player(game.state, only_oid(game, AURA), 1)
        settle(game)
        assert soldiers(game) == 0


class TestTheHostCanBeThisCreature:
    def test_equipping_this_creature_draws(self, builder):
        game = board(builder, [HOUND, GEAR])
        game._advance()
        hound = only_oid(game, HOUND)
        before = len(game.state.players[0].hand)
        equip = next(
            a
            for a in activations(game, only_oid(game, GEAR))
            if tuple(a.targets) == (TargetRef.obj(hound),)
        )
        game.apply(equip)
        settle(game)
        assert game.state.objects[only_oid(game, GEAR)].attached_to == hound
        assert len(game.state.players[0].hand) == before + 1

    def test_equipping_another_creature_does_not(self, builder):
        game = board(builder, [HOUND, BEAR, GEAR])
        before = len(game.state.players[0].hand)
        attach(game.state, only_oid(game, GEAR), only_oid(game, BEAR))
        settle(game)
        assert len(game.state.players[0].hand) == before

    def test_an_opponents_equipment_counts(self, builder):
        """No controller is printed on "an Equipment", so `controller: "any"`."""
        game = board(builder, [HOUND], theirs=[GEAR])
        before = len(game.state.players[0].hand)
        attach(game.state, only_oid(game, GEAR), only_oid(game, HOUND))
        settle(game)
        assert len(game.state.players[0].hand) == before + 1


class TestStayingAttachedIsNotBecomingAttached:
    def test_attaching_to_the_same_host_does_nothing(self, builder):
        """701.3b: the boundary. A second attach to the host it is already on
        changes nothing: it keeps its timestamp and fires nothing."""
        game = board(builder, [CAPTAIN, BEAR, AURA])
        aura, bear = only_oid(game, AURA), only_oid(game, BEAR)
        attach(game.state, aura, bear)
        settle(game)
        stamp = game.state.objects[aura].attached_timestamp
        assert soldiers(game) == 1

        assert attach(game.state, aura, bear), "still attached there"
        settle(game)
        assert game.state.objects[aura].attached_timestamp == stamp
        assert soldiers(game) == 1

    def test_coming_off_is_not_becoming_attached(self, builder):
        """The host leaving takes the Aura with it (704.5m): an unattachment,
        and nothing that answers this trigger."""
        game = board(builder, [CAPTAIN, BEAR, AURA])
        aura = only_oid(game, AURA)
        attach(game.state, aura, only_oid(game, BEAR))
        settle(game)
        assert soldiers(game) == 1

        move_object(game.state, only_oid(game, BEAR), Zone.GRAVEYARD)
        sba.run(game.state)
        settle(game)
        assert aura not in game.state.battlefield
        assert soldiers(game) == 1


def _probe(event: str, filt) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_ba_probe",
            "name": "Attach Probe",
            "oracle_text": "Whenever something happens, you gain 1 life.",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": event, "controller": "any", "filter": filt},
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_siona_shape_loads(self):
        compile_card(
            _probe(
                "becomes_attached",
                {"subtypes": ["Aura"], "attached_to": {"types": ["Creature"], "controller": "you"}},
            )
        )

    def test_the_host_filter_is_refused_on_another_event(self):
        """Read nowhere else, so it would load and fire for any host."""
        with pytest.raises(DslError, match="attached_to"):
            compile_card(_probe("permanent_enters", {"attached_to": {"types": ["Creature"]}}))

    def test_a_host_key_the_matcher_never_reads_is_refused(self):
        with pytest.raises(DslError, match="would load and be ignored"):
            compile_card(_probe("becomes_attached", {"attached_to": {"not_colors": ["W"]}}))

    def test_a_host_filter_nested_in_itself_is_refused(self):
        with pytest.raises(DslError, match="attached_to"):
            compile_card(
                _probe(
                    "becomes_attached",
                    {"attached_to": {"attached_to": {"types": ["Creature"]}}},
                )
            )

    def test_the_host_filter_inside_an_any_of_branch_is_refused(self):
        with pytest.raises(DslError):
            compile_card(
                _probe(
                    "becomes_attached",
                    {
                        "any_of": [
                            {"attached_to": {"types": ["Creature"]}},
                            {"subtypes": ["Equipment"]},
                        ]
                    },
                )
            )
