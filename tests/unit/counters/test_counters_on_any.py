"""Every kind of counter among a pool -- `counters_on` with `counter: "any"`.

    "When Ferrafor enters, create a number of 1/1 green Saproling creature
    tokens equal to the number of counters among creatures target player
    controls."                                         -- Ferrafor, Young Yew

`counters_on` took one named kind, and the card names none. Counter kinds are
open-ended (122.1: a +1/+1, a -1/-1, a stun, an oil counter are all counters),
so summing a fixed list of kinds would be a narrower card than the printed one,
and `counters_had: "any"` reads only the snapshot a leaves-the-battlefield event
binds, never live permanents. ``"any"`` is the same word `counters_had` already
uses for "every kind", read live off the pool at resolution (608.2h), in both
value languages so an effect amount and a static's magnitude agree.

The word is a reader's, not a kind: no counter is named "any", so the loader's
kind near-miss check is skipped for it and nothing else.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import counters_of_kind
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters
from commanderblitz.engine.structs import TargetRef
from tests.conftest import count_on_battlefield, oids_of, only_oid

BEAR = "t_rc_bear"
ROCK = "t_rc_rock"
SAPROLING = "saproling_1_1_g"

#: Ferrafor's blocked sentence, as a card author writes it.
AMONG_TARGET_PLAYERS_CREATURES = {
    "counters_on": {
        "counter": "any",
        "objects": {"zone": "battlefield", "types": ["Creature"], "controller": {"target": "t1"}},
    }
}


def position(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def among(game, player: int) -> int:
    ctx = EffectContext(
        state=game.state, controller=0, targets={"t1": (TargetRef.player(player),)}
    )
    return evaluate_value(ctx, AMONG_TARGET_PLAYERS_CREATURES)


def ferrafor_trigger(game, player: int) -> None:
    ctx = EffectContext(
        state=game.state, controller=0, targets={"t1": (TargetRef.player(player),)}
    )
    effects = [{"op": "create_token", "token": SAPROLING, "amount": AMONG_TARGET_PLAYERS_CREATURES}]
    for _ in execute(ctx, effects):
        raise AssertionError("create_token asked a question")


class TestEveryKindIsCounted:
    def test_kinds_are_summed_across_the_pool(self, builder):
        game = position(builder, theirs=[BEAR, BEAR])
        first, second = oids_of(game, BEAR, 1)
        add_counters(game.state, first, "+1/+1", 2)
        add_counters(game.state, first, "stun", 1)
        add_counters(game.state, second, "-1/-1", 1)
        assert among(game, 1) == 4

    def test_a_kind_nobody_listed_counts_too(self, builder):
        """The reason it is a sum over the object and not a list of kinds."""
        game = position(builder, theirs=[BEAR])
        add_counters(game.state, only_oid(game, BEAR, 1), "oil", 3)
        assert among(game, 1) == 3

    def test_no_counters_is_zero(self, builder):
        game = position(builder, theirs=[BEAR])
        assert among(game, 1) == 0

    def test_a_named_kind_still_counts_only_that_kind(self, builder):
        game = position(builder, theirs=[BEAR])
        oid = only_oid(game, BEAR, 1)
        add_counters(game.state, oid, "+1/+1", 2)
        add_counters(game.state, oid, "stun", 1)
        assert counters_of_kind(game.state.objects[oid], "+1/+1") == 2
        assert counters_of_kind(game.state.objects[oid], "any") == 3


class TestThePoolIsTheTargetPlayersCreatures:
    def test_another_players_creatures_are_not_counted(self, builder):
        game = position(builder, mine=[BEAR], theirs=[BEAR])
        add_counters(game.state, only_oid(game, BEAR, 0), "+1/+1", 5)
        add_counters(game.state, only_oid(game, BEAR, 1), "+1/+1", 1)
        assert among(game, 1) == 1
        assert among(game, 0) == 5

    def test_a_noncreature_with_counters_is_not_counted(self, builder):
        game = position(builder, theirs=[ROCK])
        add_counters(game.state, only_oid(game, ROCK, 1), "charge", 4)
        assert among(game, 1) == 0


class TestFerrafor:
    def test_it_creates_that_many_saprolings(self, builder):
        game = position(builder, theirs=[BEAR])
        add_counters(game.state, only_oid(game, BEAR, 1), "+1/+1", 2)
        add_counters(game.state, only_oid(game, BEAR, 1), "shield", 1)
        ferrafor_trigger(game, 1)
        assert count_on_battlefield(game, SAPROLING, 0) == 3

    def test_none_with_no_counters(self, builder):
        game = position(builder, theirs=[BEAR])
        ferrafor_trigger(game, 1)
        assert count_on_battlefield(game, SAPROLING, 0) == 0


def ferrafor(amount: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "When this enters, create a number of 1/1 green Saproling creature tokens equal to the number of counters among creatures target player controls.",
            "mana_cost": "{2}{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 3,
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "self_enters", "source": "self"},
                    "targets": [{"id": "t1", "kind": "player", "count": 1}],
                    "effects": [{"op": "create_token", "token": SAPROLING, "amount": amount}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_printed_card_loads(self):
        compile_card(ferrafor(AMONG_TARGET_PLAYERS_CREATURES))

    def test_a_kind_near_miss_is_still_refused(self):
        bad = {"counters_on": {"counter": "Shield", "objects": {"types": ["Creature"]}}}
        with pytest.raises(DslError, match="shield counter"):
            compile_card(ferrafor(bad))

    def test_any_still_needs_objects(self):
        bad = {"counters_on": {"counter": "any"}}
        with pytest.raises(DslError, match="needs 'objects'"):
            compile_card(ferrafor(bad))
