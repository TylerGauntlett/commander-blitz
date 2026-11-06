"""A counter of a named kind -- `has_counters: "-1/-1"`.

    "-3: Destroy target creature with a -1/-1 counter on it."
                                              -- Liliana, Death Wielder

`has_counters: true` is one or more counters of **any** kind (122.1), so a
creature carrying only +1/+1 or stun counters would be a legal target, and that
is a wider card. `counters_on` is a value: as an `if` at resolution it would
change what the ability does, not what it may target (115.1, 601.2c). The key
widens to take one counter kind, and is honoured by every reader of the filter
language through `characteristics.has_counters_matches`: targets are checked as
the ability is activated and again as it resolves (608.2b), so a creature whose
-1/-1 counter leaves in response is no longer a legal target and the ability
does nothing to it.

The kind goes through the same near-miss check `add_counters` uses, and
``"any"`` is refused because ``true`` already says it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import matches_static
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, remove_counters
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.targeting import enumerate_target_tuples, filter_legal
from commanderblitz.engine.triggers import matches_card_filter
from tests.conftest import oids_of, only_oid

WIELDER = "t_hck_wielder"
BEAR = "t_rc_bear"
DESTROY = 1  # the -3


def position(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, [WIELDER, *mine])
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def specs(game):
    return game.state.registry.get(WIELDER).abilities[DESTROY].targets


def targetable(game) -> set[int]:
    source = only_oid(game, WIELDER)
    return {
        ref.id
        for tuple_ in enumerate_target_tuples(game.state, 0, specs(game), source)
        for ref in tuple_
    }


class TestOnlyThatKindMakesItATarget:
    def test_a_minus_one_counter_makes_it_a_target(self, builder):
        game = position(builder, theirs=[BEAR, BEAR])
        marked, clean = oids_of(game, BEAR, 1)
        add_counters(game.state, marked, "-1/-1", 1)
        assert targetable(game) == {marked}
        assert clean not in targetable(game)

    def test_another_kind_does_not(self, builder):
        """The whole difference from `has_counters: true`."""
        game = position(builder, theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        add_counters(game.state, bear, "+1/+1", 2)
        add_counters(game.state, bear, "stun", 1)
        assert targetable(game) == set()

    def test_its_own_controllers_creatures_qualify_too(self, builder):
        game = position(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, "-1/-1", 1)
        assert targetable(game) == {bear}


class TestOnResolution:
    def test_losing_the_counter_in_response_makes_it_illegal(self, builder):
        """608.2b: the restriction is asked again as the ability resolves."""
        game = position(builder, theirs=[BEAR])
        bear = only_oid(game, BEAR, 1)
        add_counters(game.state, bear, "-1/-1", 1)
        buckets, _ = filter_legal(game.state, 0, specs(game), (TargetRef.obj(bear),), None)
        assert buckets["t1"] == (TargetRef.obj(bear),)
        remove_counters(game.state, bear, "-1/-1", 1)
        buckets, _ = filter_legal(game.state, 0, specs(game), (TargetRef.obj(bear),), None)
        assert buckets["t1"] == ()


class TestEveryFilterLanguage:
    def test_the_effect_side_selector(self, builder):
        game = position(builder, theirs=[BEAR, BEAR])
        marked, other = oids_of(game, BEAR, 1)
        add_counters(game.state, marked, "-1/-1", 1)
        add_counters(game.state, other, "+1/+1", 1)
        ctx = EffectContext(state=game.state, controller=0)
        pool = {"zone": "battlefield", "controller": "any", "has_counters": "-1/-1"}
        assert resolve_pool(ctx, pool) == [marked]

    def test_the_static_filter(self, builder):
        game = position(builder, mine=[BEAR, BEAR])
        marked, other = oids_of(game, BEAR, 0)
        add_counters(game.state, marked, "-1/-1", 1)
        add_counters(game.state, other, "+1/+1", 1)
        source = game.state.objects[only_oid(game, WIELDER)]
        filt = {"types": ["Creature"], "has_counters": "-1/-1"}
        assert matches_static(game.state, game.state.objects[marked], source, filt)
        assert not matches_static(game.state, game.state.objects[other], source, filt)

    def test_the_trigger_filter(self, builder):
        game = position(builder, mine=[BEAR, BEAR])
        marked, other = oids_of(game, BEAR, 0)
        add_counters(game.state, marked, "-1/-1", 1)
        add_counters(game.state, other, "+1/+1", 1)
        source = game.state.objects[only_oid(game, WIELDER)]
        filt = {"has_counters": "-1/-1"}
        assert matches_card_filter(game.state, marked, filt, source)
        assert not matches_card_filter(game.state, other, filt, source)

    def test_true_still_means_any_kind(self, builder):
        game = position(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, "+1/+1", 1)
        ctx = EffectContext(state=game.state, controller=0)
        pool = {"zone": "battlefield", "types": ["Creature"], "has_counters": True}
        assert resolve_pool(ctx, pool) == [bear]


def destroy_with(has_counters) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "Destroy target creature with a counter on it.",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "targets": [
                {"id": "t1", "kind": "permanent", "count": 1,
                 "selector": {"zone": "battlefield", "types": ["Creature"],
                              "has_counters": has_counters}}
            ],
            "spell_effects": [{"op": "destroy", "objects": {"target": "t1"}}],
        }
    )


class TestTheLoader:
    def test_a_kind_loads(self):
        compile_card(destroy_with("-1/-1"))

    def test_a_kind_near_miss_is_refused(self):
        with pytest.raises(DslError, match="stun counter"):
            compile_card(destroy_with("Stun"))

    def test_any_is_refused_in_favour_of_true(self):
        with pytest.raises(DslError, match="write true"):
            compile_card(destroy_with("any"))

    def test_a_number_is_refused(self):
        with pytest.raises(DslError, match="one counter kind"):
            compile_card(destroy_with(1))

    def test_the_static_side_checks_the_kind_too(self):
        static = {
            "kind": "static",
            "text": "Probe.",
            "effect": "buff",
            "power": {"const": 1},
            "toughness": {"const": 1},
            "affects": {"types": ["Creature"], "has_counters": "Shield"},
        }
        card = CardModel.model_validate(
            {"id": "p", "name": "P", "oracle_text": "Probe.", "mana_cost": "{W}",
             "types": ["Enchantment"], "abilities": [static]}
        )
        with pytest.raises(DslError, match="shield counter"):
            compile_card(card)
