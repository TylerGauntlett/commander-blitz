"""Kinds of counters, not counters -- `distinct` with `of: "counter_kind"`.

    "Go for the Goal! -- {3}, {T}: Until end of turn, target creature gains
    'Whenever this creature deals combat damage to a player, draw a card for
    each kind of counter on it' and it can't be blocked this turn."
                                                    -- Blitzball Stadium

Rule 122.1: a counter is a marker of a named kind, and a +1/+1, a shield and an
oil counter are three kinds. "For each kind of counter on it" counts the kinds,
so the near miss is wrong quietly in the direction that draws extra cards:
`counters_on {"counter": "any"}` sums every counter, and a creature the
Stadium's own support put three +1/+1 counters on would draw three rather than
one. `has_counters` is a filter and cannot be a number at all. Counting
distinct values over a pool is what `distinct` already is, so the kind is one
more `of`, read live off the pool at resolution (608.2h).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, remove_counters
from tests.conftest import hand_ids, oids_of, only_oid

BEAR = "t_rc_bear"

#: The granted trigger's amount, as a card author writes it.
KINDS_ON_IT = {"distinct": {"of": "counter_kind", "objects": {"self_only": True}}}


def position(builder, *, bears: int = 1):
    """``(game, oid)``: a Bear of seat 0's, on a board with libraries to draw from."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR] * bears)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game, oids_of(game, BEAR, 0)[0]


def kinds_on(game, oid: int, expr=None) -> int:
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    return evaluate_value(ctx, expr or KINDS_ON_IT)


class TestKindsAreCountedNotCounters:
    def test_many_of_one_kind_is_one(self, builder):
        """The near miss: `counters_on "any"` would read three here."""
        game, oid = position(builder)
        add_counters(game.state, oid, "+1/+1", 3)
        assert kinds_on(game, oid) == 1
        assert kinds_on(game, oid, {"counters_on": {"counter": "any", "objects": {"self_only": True}}}) == 3

    def test_each_different_kind_adds_one(self, builder):
        game, oid = position(builder)
        add_counters(game.state, oid, "+1/+1", 2)
        add_counters(game.state, oid, "shield", 1)
        add_counters(game.state, oid, "oil", 4)
        assert kinds_on(game, oid) == 3

    def test_no_counters_is_zero(self, builder):
        game, oid = position(builder)
        assert kinds_on(game, oid) == 0

    def test_a_kind_whose_last_counter_left_is_not_on_it(self, builder):
        """The boundary: a kind is on the object only while a counter of it is."""
        game, oid = position(builder)
        add_counters(game.state, oid, "+1/+1", 1)
        add_counters(game.state, oid, "stun", 1)
        remove_counters(game.state, oid, "stun", 1)
        assert kinds_on(game, oid) == 1


class TestThePoolIsItsObjects:
    def test_self_only_reads_only_that_creature(self, builder):
        game, _ = position(builder, bears=2)
        first, second = oids_of(game, BEAR, 0)
        add_counters(game.state, first, "+1/+1", 1)
        add_counters(game.state, second, "oil", 1)
        add_counters(game.state, second, "shield", 1)
        assert kinds_on(game, first) == 1
        assert kinds_on(game, second) == 2

    def test_a_shared_kind_across_a_pool_counts_once(self, builder):
        game, _ = position(builder, bears=2)
        first, second = oids_of(game, BEAR, 0)
        add_counters(game.state, first, "+1/+1", 1)
        add_counters(game.state, second, "+1/+1", 2)
        add_counters(game.state, second, "oil", 1)
        mine = {"distinct": {"of": "counter_kind", "objects": {"controller": "you", "types": ["Creature"]}}}
        assert kinds_on(game, first, mine) == 2


class TestTheDraw:
    def test_it_draws_a_card_for_each_kind(self, builder):
        game, _ = position(builder)
        oid = only_oid(game, BEAR, 0)
        add_counters(game.state, oid, "+1/+1", 3)
        add_counters(game.state, oid, "shield", 1)
        before = len(hand_ids(game, 0))
        ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
        for _ in execute(ctx, [{"op": "draw", "player": "you", "amount": KINDS_ON_IT}]):
            raise AssertionError("draw asked a question")
        assert len(hand_ids(game, 0)) == before + 2


def stadium(amount: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "{3}, {T}: Target creature gains \"Whenever this creature deals combat damage to a player, draw a card for each kind of counter on it\" until end of turn.",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "activated",
                    "cost": {"mana": "{3}", "tap": True},
                    "targets": [
                        {
                            "id": "t1",
                            "kind": "permanent",
                            "count": 1,
                            "selector": {"types": ["Creature"], "zone": "battlefield"},
                        }
                    ],
                    "effects": [{"op": "grant_ability", "ability": 0, "objects": {"target": "t1"}}],
                }
            ],
            "grantable_abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "deals_combat_damage_to_player", "source": "self"},
                    "effects": [{"op": "draw", "player": "you", "amount": amount}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_printed_card_loads(self):
        compile_card(stadium(KINDS_ON_IT))

    def test_it_still_needs_objects(self):
        with pytest.raises(DslError, match="needs 'objects'"):
            validate_value({"distinct": {"of": "counter_kind"}}, "test")

    def test_a_misspelt_of_is_refused(self):
        with pytest.raises(DslError, match="'of' must be one of"):
            compile_card(stadium({"distinct": {"of": "counter_kinds", "objects": {"self_only": True}}}))

    def test_a_static_may_not_read_it(self):
        """A static reads `distinct` only as delirium's printed card types, so this `of` is refused."""
        from commanderblitz.cards.loader.statics import _validate_static_value

        with pytest.raises(DslError, match="can only read 'card_type'"):
            _validate_static_value(KINDS_ON_IT, "test")
