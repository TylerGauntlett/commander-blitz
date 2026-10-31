"""`attached_to` -- "each Aura you control that's attached to a creature", "each Aura attached to it".

An Aura or Equipment is attached to the permanent its `attached_to` names
(301.5, 303.4). `enchanted_by` asks that of the host; this is the other end, an
attachment matched by a filter on its host. Without it, Sage's Reverie ("draw a
card for each Aura you control that's attached to a creature") could only count
every Aura you control -- one enchanting a land, an artifact or a player
included -- and Kor Spiritdancer ("+2/+2 for each Aura attached to it") had no
way to say "it": `attached` names the host of the ability's own source, the
opposite direction, and `attached_to_host` the other attachments sharing that
host, which a creature has none of.

The value is a filter on the host in the language it sits in, so the selector
reads it with `matches` and a static with `_matches_wherever`, and `self_only`
there is the ability's own source. Neither end has a controller by default --
the printed line names the host by what it is and an opponent's Pacifism is
attached to Kor Spiritdancer all the same -- so "you control" is written. An
Aura on a player is attached to no permanent. A bestowed creature is an Aura
while attached (702.103b), which the static's printed face says too.

The witnesses are Sage's Reverie and Kor Spiritdancer; `t_at_reverie` and
`t_at_dancer` are their counting lines.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import _matches
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, attach_to_player
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, only_oid, pt, settle, static_probe
from tests.unit.attachments.test_bestow import bestow_onto

AURA = "t_eb_aura"  # Enchant creature, and nothing else
BEAR = "t_eb_bear"
REVERIE = "t_at_reverie"  # Sage's Reverie
DANCER = "t_at_dancer"  # Kor Spiritdancer's "+2/+2 for each Aura attached to it", a 0/2
GEAR = "t_plain_gear"  # an Equipment with nothing printed
ROBE = "t_robe_mover"  # "Enchant player"
SPIRIT = "t_bestower"  # bestow {5}{W}
ISLAND = "island"
PLAINS = "plains"

YOURS_ON_A_CREATURE = {"subtypes": ["Aura"], "controller": "you", "attached_to": {"types": ["Creature"]}}


def board(builder, *, mine=(), theirs=(), hand=(), lands=0):
    """Player 0's ``mine`` facing player 1's ``theirs``, nothing attached yet.

    Frozen in the untap step so a test can attach before the state-based action
    that bins an unattached Aura looks; `go` lets it look. ``lands`` Islands
    and Plains each pay for ``hand``. Returns the game.
    """
    b = builder(players=2).battlefield(0, list(mine)).battlefield(1, list(theirs))
    if lands:
        b.battlefield(0, [ISLAND] * lands + [PLAINS] * lands)
    if hand:
        b.hand(0, list(hand))
    for pid in range(2):
        b.library(pid, [ISLAND] * 20)
    return b.active(0).step(Step.UNTAP).build(advance=False)


def go(game):
    game._advance()
    settle(game)
    return game


def pool(game, spec, controller=0, source=None):
    ctx = EffectContext(game.state, controller=controller, source_oid=source)
    return resolve_pool(ctx, {"zone": "battlefield", "subtypes": ["Aura"], "attached_to": spec})


class TestTheSelector:
    def test_it_matches_by_what_the_host_is(self, builder):
        """An Aura on a creature, one on a land: only the first is attached to
        a creature."""
        game = board(builder, mine=[AURA, AURA, BEAR, ISLAND])
        on_bear, on_land = oids_of(game, AURA, 0)
        attach(game.state, on_bear, only_oid(game, BEAR, 0))
        attach(game.state, on_land, only_oid(game, ISLAND, 0))
        go(game)
        assert pool(game, {"types": ["Creature"]}) == [on_bear]
        assert pool(game, {"types": ["Land"]}) == [on_land]

    def test_the_hosts_controller_is_a_clause_of_its_own(self, builder):
        """Player 0's Aura on player 1's Bear: attached to a creature, to a
        creature an opponent controls, and not to one player 0 controls."""
        game = board(builder, mine=[AURA], theirs=[BEAR])
        aura = only_oid(game, AURA, 0)
        attach(game.state, aura, only_oid(game, BEAR, 1))
        go(game)
        assert pool(game, {"types": ["Creature"]}) == [aura]
        assert pool(game, {"types": ["Creature"], "controller": "opponent"}) == [aura]
        assert pool(game, {"types": ["Creature"], "controller": "you"}) == []

    def test_self_only_is_the_abilitys_source(self, builder):
        game = board(builder, mine=[AURA, BEAR, DANCER])
        aura = only_oid(game, AURA, 0)
        dancer = only_oid(game, DANCER, 0)
        attach(game.state, aura, dancer)
        go(game)
        assert pool(game, {"self_only": True}, source=dancer) == [aura]
        assert pool(game, {"self_only": True}, source=only_oid(game, BEAR, 0)) == []

    def test_an_aura_on_a_player_is_attached_to_no_permanent(self, builder):
        game = board(builder, mine=[ROBE])
        attach_to_player(game.state, only_oid(game, ROBE, 0), 1)
        go(game)
        assert pool(game, {"types": ["Creature"]}) == []
        assert pool(game, {"controller": "any"}) == []


class TestSagesReverie:
    def test_it_draws_for_each_of_your_auras_on_a_creature(self, builder):
        """Already on the board: your Aura on the opponent's Bear (counts), your
        Aura on a land (does not), your Equipment on your Bear (no Aura), the
        opponent's Aura on your Bear (not yours). Then the Reverie itself, on a
        creature as it enters: two cards."""
        game = board(
            builder, mine=[AURA, AURA, BEAR, GEAR], theirs=[BEAR, AURA], hand=[REVERIE], lands=4
        )
        state = game.state
        mine_on_theirs, mine_on_land = oids_of(game, AURA, 0)
        my_bear, their_bear = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        attach(state, mine_on_theirs, their_bear)
        attach(state, mine_on_land, oids_of(game, ISLAND, 0)[0])
        attach(state, only_oid(game, GEAR, 0), my_bear)
        attach(state, only_oid(game, AURA, 1), my_bear)
        go(game)
        hand = len(state.players[0].hand)
        _cast_onto(game, REVERIE, my_bear)
        assert len(state.players[0].hand) == hand - 1 + 2

    def test_the_anthem_counts_the_same_auras_and_wears_off(self, builder):
        game = board(builder, mine=[AURA, BEAR], theirs=[BEAR], hand=[REVERIE], lands=4)
        state = game.state
        aura = only_oid(game, AURA, 0)
        my_bear, their_bear = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        attach(state, aura, their_bear)
        go(game)
        _cast_onto(game, REVERIE, my_bear)
        assert pt(game, my_bear) == (4, 4)
        destroy(state, aura, cause="test")
        assert pt(game, my_bear) == (3, 3)


class TestKorSpiritdancer:
    def test_each_aura_attached_to_it_whoever_controls_it(self, builder):
        game = board(builder, mine=[DANCER, AURA, GEAR], theirs=[AURA])
        state = game.state
        dancer = only_oid(game, DANCER, 0)
        assert pt(game, dancer) == (0, 2)
        attach(state, only_oid(game, AURA, 0), dancer)
        attach(state, only_oid(game, AURA, 1), dancer)
        attach(state, only_oid(game, GEAR, 0), dancer)
        go(game)
        assert pt(game, dancer) == (4, 6)

    def test_an_aura_on_another_creature_does_not_count(self, builder):
        game = board(builder, mine=[DANCER, AURA, BEAR])
        attach(game.state, only_oid(game, AURA, 0), only_oid(game, BEAR, 0))
        go(game)
        assert pt(game, only_oid(game, DANCER, 0)) == (0, 2)

    def test_a_bestowed_creature_counts_as_an_aura(self, builder):
        """702.103b: attached, the Spirit is an Aura and no creature, and the
        static's printed face says so."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 8 + [DANCER])
            .hand(0, [SPIRIT])
            .library(0, [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        dancer = only_oid(game, DANCER, 0)
        spirit = bestow_onto(game, dancer)
        source = game.state.objects[dancer]
        assert _matches(game.state, game.state.objects[spirit], source, {"subtypes": ["Aura"]})
        assert not _matches(
            game.state, game.state.objects[spirit], source, {"types": ["Creature"]}
        )
        # +2/+2 for the Aura and the bestowed Spirit's own +2/+2.
        assert pt(game, dancer) == (4, 6)


class TestTheCostReduction:
    def test_it_is_refused_there(self):
        """A reduction counts a board and `_reduction_matches` does not read the
        key, so it would load and be ignored."""
        model = {
            "id": "x",
            "name": "X",
            "oracle_text": "Probe.",
            "mana_cost": "{9}",
            "types": ["Sorcery"],
            "cost_reduction": {"count": {"subtypes": ["Aura"], "attached_to": {"types": ["Creature"]}}},
            "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match="name a relation to one permanent"):
            compile_card(CardModel.model_validate(model))


def _compile(ability: dict) -> None:
    compile_card(CardModel.model_validate(static_probe({}) | {"abilities": [ability]}))


def _static(spec) -> dict:
    return {
        "kind": "static",
        "text": "Probe.",
        "effect": "buff",
        "affects": {"self_only": True},
        "power": {"count": {"subtypes": ["Aura"], "attached_to": spec}},
    }


def _draw(spec) -> dict:
    return {
        "kind": "triggered",
        "text": "Probe.",
        "trigger": {"event": "self_enters", "source": "self"},
        "effects": [{"op": "draw", "amount": {"count": {"subtypes": ["Aura"], "attached_to": spec}}}],
    }


class TestTheLoader:
    @pytest.mark.parametrize(
        ("spec", "message"),
        [
            (True, "a non-empty filter on the permanent"),
            ({}, "a non-empty filter on the permanent"),
            ({"zone": "graveyard"}, "on the battlefield"),
            ({"attached_to": {"self_only": True}}, "attached_to"),
        ],
    )
    def test_a_malformed_host_filter_is_refused_in_both_languages(self, spec, message):
        with pytest.raises(DslError, match=message):
            _compile(_static(spec))
        with pytest.raises(DslError, match=message):
            _compile(_draw(spec))

    def test_a_pool_key_is_refused_on_the_effect_side(self):
        with pytest.raises(DslError, match="shape a pool"):
            _compile(_draw({"target": "t1"}))

    def test_the_static_host_filter_is_held_to_the_static_language(self):
        with pytest.raises(DslError, match="unsupported keys"):
            _compile(_static({"damaged": True}))
        with pytest.raises(DslError, match="a comparison"):
            _compile(_static({"power": {"amount": 4}}))

    def test_attached_beside_it_is_refused(self):
        static = {
            "kind": "static",
            "text": "Probe.",
            "effect": "buff",
            "affects": {"attached": True, "attached_to": {"types": ["Creature"]}},
            "power": {"const": 1},
        }
        with pytest.raises(DslError, match="cannot be narrowed"):
            _compile(static)

    def test_a_trigger_filter_does_not_read_it(self):
        trigger = {
            "kind": "triggered",
            "text": "Probe.",
            "trigger": {"event": "permanent_enters", "controller": "any", "filter": YOURS_ON_A_CREATURE},
            "effects": [{"op": "draw", "amount": {"const": 1}}],
        }
        with pytest.raises(DslError, match="would load and be ignored"):
            _compile(trigger)

    def test_the_witness_shapes_load(self):
        _compile(_static({"self_only": True}))
        _compile(_draw({"types": ["Creature"]}))


def _cast_onto(game, card_id, host):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and any(getattr(ref, "id", None) == host for ref in a.targets)
    )
    game.apply(action)
    settle(game)
