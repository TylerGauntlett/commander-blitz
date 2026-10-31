"""`enchanted_by` -- "creatures that aren't enchanted", "enchanted by an Aura you control".

A permanent is enchanted when an Aura is attached to it (303.4). Attachment is
stored one way, on the Aura as `attached_to`, so before this key no filter could
ask it of the host: `attached` names the one permanent the ability's own source
is attached to, and `modified` also counts counters and Equipment and only Auras
you control. Winds of Rath ("Destroy all creatures that aren't enchanted") would
have destroyed every creature, and Eriette of the Charmed Apple's wall ("Each
creature that's enchanted by an Aura you control can't attack you") would have
walled off every creature or none.

`characteristics.enchanted_by` answers it from the host's end for every filter
language -- the selector, the static filter, the trigger filter and the
cost-reduction count -- so the four cannot disagree. `{"controller": ...}` is
whose Aura, relative to the player the filter is read for; a Curse enchants a
player and no permanent; a bestowed creature is an Aura while attached
(702.103a). Every half is a pipeline input, so the static filter may read it.

The witnesses are Winds of Rath, Eriette of the Charmed Apple and Killian,
Decisive Mentor. `t_eb_wall` and `t_eb_mentor` are Eriette's wall and Killian's
draw alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import _matches
from commanderblitz.engine.cost_reduction import _object_matches
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, attach_to_player
from commanderblitz.engine.triggers import matches_card_filter
from commanderblitz.engine.zones import destroy
from tests.conftest import attack_with, find_action, only_oid, settle, static_probe
from tests.unit.attachments.test_bestow import bestow_onto
from tests.unit.attachments.test_bestow import position as bestow_position
from tests.unit.combat.test_goad import defenders_offered, to_declare_attackers

AURA = "t_eb_aura"  # Enchant creature, and nothing else
BEAR = "t_eb_bear"
CUB = "t_eb_cub"
WALL = "t_eb_wall"  # Eriette's "…enchanted by an Aura you control can't attack you"
MENTOR = "t_eb_mentor"  # Killian's "…one or more creatures enchanted by an Aura you control attack"
GEAR = "t_plain_gear"  # an Equipment with nothing printed
ROBE = "t_robe_mover"  # "Enchant player"
SWAMP = "swamp"

CREATURES = {"zone": "battlefield", "types": ["Creature"]}


def enchanted(builder, *, aura_of=0, mine=(), active=1, players=3, robe_on=None):
    """Player 1's Bear wearing ``aura_of``'s Aura, beside player 1's bare Cub.

    Attached before the position advances, as `test_static_goad.enchanted`
    builds it, so the state-based action that bins an unattached Aura never sees
    one. ``mine`` is what else player 0 controls; ``robe_on`` puts player 0's
    "Enchant player" Aura on that seat. Returns ``(game, bear, cub)``.
    """
    b = builder(players=players).battlefield(aura_of, [AURA]).battlefield(1, [BEAR, CUB])
    if mine:
        b.battlefield(0, list(mine))
    for pid in range(players):
        b.library(pid, [SWAMP] * 20)
    game = b.active(active).step(Step.UNTAP).build(advance=False)
    bear, cub = only_oid(game, BEAR, 1), only_oid(game, CUB, 1)
    assert attach(game.state, only_oid(game, AURA, aura_of), bear)
    if robe_on is not None:
        attach_to_player(game.state, only_oid(game, ROBE, 0), robe_on)
    game._advance()
    return game, bear, cub


def pool(game, spec, controller=0):
    ctx = EffectContext(game.state, controller=controller, source_oid=None)
    return resolve_pool(ctx, {**CREATURES, "enchanted_by": spec})


class TestTheSelector:
    def test_true_is_enchanted_and_false_is_not(self, builder):
        game, bear, cub = enchanted(builder)
        assert pool(game, True) == [bear]
        assert pool(game, False) == [cub]

    def test_whose_aura_is_read_from_the_filters_controller(self, builder):
        """Player 0's Aura: "you" for player 0, "opponent" for player 2, and
        never the creature's own controller, player 1."""
        game, bear, _ = enchanted(builder)
        assert pool(game, {"controller": "you"}) == [bear]
        assert pool(game, {"controller": "opponent"}) == []
        assert pool(game, {"controller": "opponent"}, controller=2) == [bear]
        assert pool(game, {"controller": "you"}, controller=1) == []
        assert pool(game, {"controller": "any"}, controller=1) == [bear]

    def test_equipment_does_not_enchant(self, builder):
        """The difference from `modified`: an Equipment is attached and is not
        an Aura."""
        game, bear, cub = enchanted(builder, mine=[GEAR])
        attach(game.state, only_oid(game, GEAR, 0), cub)
        assert pool(game, True) == [bear]

    def test_an_aura_on_a_player_enchants_no_permanent(self, builder):
        game, bear, cub = enchanted(builder, mine=[ROBE], robe_on=1)
        assert game.state.objects[only_oid(game, ROBE, 0)].attached_to_player == 1
        assert pool(game, True) == [bear]
        assert cub in pool(game, False)

    def test_it_wears_off_with_the_aura(self, builder):
        game, bear, cub = enchanted(builder)
        destroy(game.state, only_oid(game, AURA, 0), cause="test")
        assert pool(game, True) == []
        assert pool(game, False) == [bear, cub]

    def test_a_bestowed_creature_enchants(self, builder):
        """702.103a: an Aura while attached, though its printed face is a
        creature's."""
        game = bestow_position(builder)
        bear = only_oid(game, "t_bear", 0)
        bestow_onto(game, bear)
        assert pool(game, True) == [bear]


class TestTheStatic:
    """Eriette's wall: a static filter reads `enchanted_by` relative to the
    static's controller, and the creature's own controller is a separate clause."""

    def test_the_filter_reads_the_statics_controller(self, builder):
        game, bear, cub = enchanted(builder, mine=[WALL])
        wall = game.state.objects[only_oid(game, WALL, 0)]
        affects = {"controller": "any", "types": ["Creature"], "enchanted_by": {"controller": "you"}}
        assert _matches(game.state, game.state.objects[bear], wall, affects)
        assert not _matches(game.state, game.state.objects[cub], wall, affects)

    def test_a_creature_wearing_your_aura_cannot_attack_you(self, builder):
        game, bear, cub = enchanted(builder, mine=[WALL])
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [2]
        assert defenders_offered(game, cub) == [0, 2]

    def test_an_opponents_aura_does_not_wall_you_off(self, builder):
        game, bear, _ = enchanted(builder, aura_of=2, mine=[WALL])
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0, 2]


class TestTheTriggerFilter:
    def test_it_reads_the_abilitys_controller(self, builder):
        game, bear, cub = enchanted(builder, mine=[MENTOR])
        source = game.state.objects[only_oid(game, MENTOR, 0)]
        mine = {"enchanted_by": {"controller": "you"}}
        assert matches_card_filter(game.state, bear, mine, source)
        assert not matches_card_filter(game.state, cub, mine, source)
        assert matches_card_filter(game.state, cub, {"enchanted_by": False}, source)

    @pytest.mark.parametrize(("attackers", "drawn"), [((BEAR, CUB), 1), ((CUB,), 0)])
    def test_killian_draws_once_when_your_aura_attacks(self, builder, attackers, drawn):
        """Player 1 swings at player 2; the Bear wears player 0's Aura. One
        card however many attack beside it, and none without it."""
        game, *_ = enchanted(builder, mine=[MENTOR])
        hand = len(game.state.players[0].hand)
        to_declare_attackers(game)
        for card_id in attackers:
            attack_with(game, only_oid(game, card_id, 1), defender=2)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        settle(game)
        assert len(game.state.players[0].hand) == hand + drawn


class TestTheCostReduction:
    def test_the_count_reads_the_paying_player(self, builder):
        game, bear, cub = enchanted(builder)
        state = game.state
        mine = {"controller": "any", "enchanted_by": {"controller": "you"}}
        assert _object_matches(state, 0, mine, bear, state.objects[bear], None)
        assert not _object_matches(state, 0, mine, cub, state.objects[cub], None)
        assert not _object_matches(state, 1, mine, bear, state.objects[bear], None)


def _compile(ability: dict) -> None:
    compile_card(CardModel.model_validate(static_probe({}) | {"abilities": [ability]}))


class TestTheLoader:
    @pytest.mark.parametrize(
        ("spec", "message"),
        [
            ("you", "true, false, or a filter on the Auras"),
            ({}, "true, false, or a filter on the Auras"),
            ({"types": ["Enchantment"]}, "are not asked of the Auras"),
            ({"controller": "enchanted_player"}, "enchanted_by.controller"),
        ],
    )
    def test_a_malformed_value_is_refused_in_every_language(self, spec, message):
        static = {
            "kind": "static",
            "text": "Probe.",
            "effect": "cant_attack_you",
            "affects": {"controller": "any", "enchanted_by": spec},
        }
        with pytest.raises(DslError, match=message):
            _compile(static)
        trigger = {
            "kind": "triggered",
            "text": "Probe.",
            "trigger": {"event": "attacks", "controller": "any", "filter": {"enchanted_by": spec}},
            "effects": [{"op": "draw", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match=message):
            _compile(trigger)

    @pytest.mark.parametrize("event", ["creature_dies", "dies", "leaves_battlefield"])
    def test_a_departure_trigger_is_refused(self, event):
        """`_detach_all` unattaches the Auras first: the creature that left is
        never enchanted, so the trigger would never fire."""
        trigger = {
            "kind": "triggered",
            "text": "Probe.",
            "trigger": {"event": event, "controller": "any", "filter": {"enchanted_by": True}},
            "effects": [{"op": "draw", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match="has left the battlefield"):
            _compile(trigger)

    def test_the_witness_shapes_load(self):
        _compile(
            {
                "kind": "triggered",
                "text": "Probe.",
                "trigger": {
                    "event": "attacks",
                    "controller": "any",
                    "filter": {"enchanted_by": {"controller": "you"}},
                },
                "effects": [{"op": "draw", "amount": {"const": 1}}],
            }
        )
