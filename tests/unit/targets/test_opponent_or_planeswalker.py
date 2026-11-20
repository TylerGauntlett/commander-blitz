""""This enchantment deals 1 damage to target **opponent or planeswalker**."

Theater of Horrors and Collective Defiance. 115.4 makes "target opponent or
planeswalker" one target whose legal choices are an opponent *or any
planeswalker* -- your own included, because "opponent" narrows only the
players. A `kind: "any"` spec reads one selector for both halves, so neither
single-selector spelling is the printed card: `controller: "opponent"` also
drops your own planeswalkers (a narrower card), and no `controller` at all
lets you target yourself (a wider one).

`player_selector` gives the player half its own player spec and leaves
`selector` to the permanent half. 608.2b re-checks a target by the question it
was chosen by, so `still_legal` reads the same `TargetSpec.player_clause`
`candidates` does -- a seat offered here is never one the re-check refuses.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.targeting import still_legal
from tests.conftest import activations, settle_to_priority

PINGER = "t_oop_pinger"  # "target opponent or planeswalker"
NARROW = "t_oop_narrow"  # the near miss: controller "opponent" on both halves
WIDE = "t_oop_wide"  # the near miss: "target player or planeswalker"
WALKER = "t_walker"  # loyalty 4


def position(builder, pinger=PINGER, *, players=2):
    b = builder(players=players).battlefield(0, ["mountain"] * 3 + [pinger, WALKER])
    for seat in range(1, players):
        b = b.battlefield(seat, [WALKER])
    for seat in range(players):
        b = b.library(seat, ["forest"] * 20)
    game = b.build()
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == pinger)
    return game, oid


def walker_of(game, seat):
    return next(o.oid for o in game.state.battlefield_objects(seat) if o.def_id == WALKER)


def offered(game, oid):
    return {a.targets[0] for a in activations(game, oid)}


class TestThePlayerHalfIsOpponentsOnly:
    def test_an_opponent_is_offered(self, builder):
        game, oid = position(builder)
        assert TargetRef.player(1) in offered(game, oid)

    def test_you_are_not(self, builder):
        game, oid = position(builder)
        assert TargetRef.player(0) not in offered(game, oid)

    def test_every_opponent_at_a_pod(self, builder):
        game, oid = position(builder, players=4)
        players = {r.id for r in offered(game, oid) if r.kind == "player"}
        assert players == {1, 2, 3}


class TestThePermanentHalfIsEveryPlaneswalker:
    def test_an_opponents_planeswalker_is_offered(self, builder):
        game, oid = position(builder)
        assert TargetRef.obj(walker_of(game, 1)) in offered(game, oid)

    def test_your_own_planeswalker_is_offered(self, builder):
        game, oid = position(builder)
        assert TargetRef.obj(walker_of(game, 0)) in offered(game, oid)

    def test_a_non_planeswalker_is_not(self, builder):
        game, oid = position(builder)
        objects = {r.id for r in offered(game, oid) if r.kind == "object"}
        assert objects == {walker_of(game, 0), walker_of(game, 1)}


class TestTheNearMissesAreOtherCards:
    def test_controller_opponent_drops_your_own_planeswalker(self, builder):
        game, oid = position(builder, NARROW)
        refs = offered(game, oid)
        assert TargetRef.obj(walker_of(game, 0)) not in refs
        assert TargetRef.player(0) not in refs

    def test_no_controller_lets_you_target_yourself(self, builder):
        game, oid = position(builder, WIDE)
        assert TargetRef.player(0) in offered(game, oid)


class TestItDealsTheDamage:
    def test_to_an_opponent(self, builder):
        game, oid = position(builder)
        life = game.state.players[1].life
        game.apply(next(a for a in activations(game, oid) if a.targets[0] == TargetRef.player(1)))
        settle_to_priority(game)
        assert game.state.players[1].life == life - 1

    def test_to_your_own_planeswalker(self, builder):
        game, oid = position(builder)
        mine = walker_of(game, 0)
        before = game.state.objects[mine].counters.get("loyalty", 0)
        game.apply(next(a for a in activations(game, oid) if a.targets[0] == TargetRef.obj(mine)))
        settle_to_priority(game)
        assert game.state.objects[mine].counters.get("loyalty", 0) == before - 1


class TestTheRecheckReadsThePlayerHalf:
    def test_you_are_never_legal_and_an_opponent_is(self, builder):
        game, oid = position(builder)
        state = game.state
        spec = state.registry.get(PINGER).abilities[0].targets[0]
        assert still_legal(state, 0, spec, TargetRef.player(1), oid)
        assert not still_legal(state, 0, spec, TargetRef.player(0), oid)
        assert still_legal(state, 0, spec, TargetRef.obj(walker_of(game, 0)), oid)


class TestTheLoaderRefuses:
    def _card(self, target: dict):
        return CardModel.model_validate(
            {
                "id": "t_bad_oop",
                "name": "Test Bad Opponent or Planeswalker",
                "oracle_text": "Test Bad deals 1 damage to target opponent or planeswalker.",
                "mana_cost": "{R}",
                "types": ["Instant"],
                "targets": [{"id": "t1", "count": 1, **target}],
                "spell_effects": [{"op": "damage", "amount": {"const": 1}, "target": "t1"}],
            }
        )

    def test_on_any_other_kind(self):
        """A `player` spec's one pool is already `selector.controller`'s."""
        with pytest.raises(DslError, match="player half of an 'any'"):
            compile_card(self._card({"kind": "player", "player_selector": "opponent"}), source="test")

    def test_any(self):
        with pytest.raises(DslError, match="already means"):
            compile_card(self._card({"kind": "any", "player_selector": "any"}), source="test")

    def test_an_unknown_player_spec(self):
        with pytest.raises(DslError, match="unknown player spec"):
            compile_card(self._card({"kind": "any", "player_selector": "oponent"}), source="test")

    def test_a_sibling_reference(self):
        with pytest.raises(DslError, match="sibling target"):
            compile_card(
                self._card({"kind": "any", "player_selector": {"target": "t0"}}), source="test"
            )

    def test_the_shipped_shape_loads(self):
        compile_card(
            self._card(
                {
                    "kind": "any",
                    "selector": {"types": ["Planeswalker"]},
                    "player_selector": "opponent",
                }
            ),
            source="test",
        )
