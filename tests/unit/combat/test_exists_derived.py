"""`exists_derived` -- an attack or block restriction lifted by the board as it is now.

    Rhonas the Indomitable -- "Rhonas can't attack or block unless you control
    another creature with power 4 or greater."

The condition is asked as attackers or blockers are declared (508.1c, 509.1b)
and it reads the creatures' **current** power: Rhonas's own {2}{G} pumps a
3-power creature to 5, and that is the card's central play. A static's `exists`
reads base power, which is what keeps the layer pipeline acyclic (ADR 0001), so
written with it the pumped creature would not free Rhonas and a printed 4-power
creature shrunk to 1 still would.

`exists_derived` is admitted only on `cant_attack` and `cant_block`, whose
readers -- `attack_forbidden`, `block_forbidden` -- ask one creature at a time
outside the pipeline. `_static_active` defers it everywhere else, and the loader
refuses it on any other static rather than let it apply as though the clause
were not printed.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import can_attack
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import attack_forbidden, block_forbidden
from commanderblitz.engine.primitives import add_counters

RHONAS = "t_ed_rhonas"
BEAR = "t_bear"     # 2/2
BIG = "t_big"       # 6/6


def board(builder, others: list[str]):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + [RHONAS] + others)
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .build(advance=False)
    )
    rhonas = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == RHONAS)
    return game, rhonas


def oid_of(game, def_id: str) -> int:
    return next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == def_id)


class TestTheRestriction:
    def test_alone_it_can_neither_attack_nor_block(self, builder):
        game, rhonas = board(builder, [])

        assert attack_forbidden(game.state, rhonas)
        assert block_forbidden(game.state, rhonas)

    def test_a_big_friend_frees_it(self, builder):
        game, rhonas = board(builder, [BIG])

        assert not attack_forbidden(game.state, rhonas)
        assert not block_forbidden(game.state, rhonas)

    def test_a_small_friend_does_not(self, builder):
        game, rhonas = board(builder, [BEAR])

        assert attack_forbidden(game.state, rhonas)

    def test_rhonas_does_not_count_itself(self, builder):
        """"**Another** creature": Rhonas is a 5/5 and still cannot attack alone."""
        game, rhonas = board(builder, [])

        assert attack_forbidden(game.state, rhonas)


class TestItReadsCurrentPower:
    def test_a_bear_with_two_counters_frees_it(self, builder):
        game, rhonas = board(builder, [BEAR])
        add_counters(game.state, oid_of(game, BEAR), "+1/+1", 2)

        assert not attack_forbidden(game.state, rhonas)
        assert not block_forbidden(game.state, rhonas)

    def test_the_answer_reaches_attack_legality(self, builder):
        game, rhonas = board(builder, [BEAR])
        game.state.objects[rhonas].entered_turn = -1
        before = can_attack(game.state, rhonas)
        add_counters(game.state, oid_of(game, BEAR), "+1/+1", 2)

        assert not before
        assert can_attack(game.state, rhonas)


class TestTheLoader:
    COND = {"not": {"exists_derived": {"controller": "you", "types": ["Creature"],
                                       "power": {"op": ">=", "value": 4}}}}

    def _card(self, effect: str, condition=None, **extra) -> CardModel:
        static = {"kind": "static", "effect": effect, "affects": {"self_only": True},
                  "condition": condition or self.COND, **extra}
        return CardModel.model_validate(
            {"id": "t_ed_probe", "name": "Exists Derived Probe", "mana_cost": "{1}",
             "types": ["Creature"], "power": 1, "toughness": 1, "abilities": [static]}
        )

    def test_it_loads_on_cant_attack_and_cant_block(self):
        compile_card(self._card("cant_attack"))
        compile_card(self._card("cant_block"))

    def test_a_layered_static_is_refused(self):
        with pytest.raises(DslError, match="exists_derived"):
            compile_card(self._card("buff", power=1, toughness=1))

    def test_another_zone_is_refused(self):
        with pytest.raises(DslError, match="exists_derived"):
            compile_card(
                self._card("cant_attack", {"exists_derived": {"zone": "graveyard",
                                                              "types": ["Creature"]}})
            )
