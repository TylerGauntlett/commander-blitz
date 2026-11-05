"""`keywords_had` -- the keywords a creature had as it left the battlefield.

"Whenever a creature you control **without flying** dies, return it to the
battlefield under its owner's control with a flying counter on it" (Luminous
Broodmoth). A leaves-the-battlefield ability looks back in time (603.10a): the
question is asked about the creature as it last existed on the battlefield,
with every keyword it had there -- printed, granted, or from a keyword counter.

A trigger filter's `keywords` reads the printed face, and that is wrong both
ways. A creature Broodmoth returned wears a flying counter and so dies *with*
flying, but its printed face has none: it would be returned again for ever. A
creature an anthem gave flying dies with flying too, and must stay dead.

`zones.move_object` snapshots `chars().keywords` before the wipe onto the
departure event as `had_keywords`, beside `had_power` and `had_counters`, and
the `keywords_had` value reads it back. The witness is Luminous Broodmoth;
`t_kh_broodmoth` is its trigger on its printed body.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import oids_of, settle

MOTH = "t_kh_broodmoth"
WINGS = "t_kh_wings"  # creatures you control have flying
BEAR = "t_bear"  # a vanilla 2/2
FLYER = "t_flyer"  # a 2/2 with printed flying


def position(builder, mine=(BEAR,), theirs=()):
    """Player 0 has Broodmoth and ``mine``; player 1 has ``theirs``."""
    b = builder(players=2).battlefield(0, [MOTH, *mine])
    if theirs:
        b.battlefield(1, list(theirs))
    return b.build()


def on_battlefield(game, card_id, pid=0) -> list[int]:
    return [
        oid for oid in oids_of(game, card_id, pid)
        if game.state.objects[oid].zone is Zone.BATTLEFIELD
    ]


def kill(game, card_id, pid=0) -> None:
    (oid,) = on_battlefield(game, card_id, pid)
    destroy(game.state, oid, cause="test")
    settle(game)


class TestACreatureWithoutFlyingComesBack:
    def test_a_vanilla_creature_returns_with_a_flying_counter(self, builder):
        game = position(builder)
        kill(game, BEAR)
        (bear,) = on_battlefield(game, BEAR)
        assert game.state.objects[bear].counters.get("flying") == 1
        assert "flying" in chars(game.state, bear).keywords

    def test_an_opponents_creature_is_not_returned(self, builder):
        game = position(builder, mine=(), theirs=(BEAR,))
        kill(game, BEAR, pid=1)
        assert on_battlefield(game, BEAR, 1) == []


class TestACreatureThatHadFlyingStaysDead:
    def test_printed_flying(self, builder):
        game = position(builder, mine=(FLYER,))
        kill(game, FLYER)
        assert on_battlefield(game, FLYER) == []

    def test_the_flying_counter_it_came_back_with(self, builder):
        """The loop the printed face would make: second death is final."""
        game = position(builder)
        kill(game, BEAR)
        assert len(on_battlefield(game, BEAR)) == 1
        kill(game, BEAR)
        assert on_battlefield(game, BEAR) == []

    def test_flying_granted_by_an_anthem(self, builder):
        """Printed face has no flying; the creature as it left did."""
        game = position(builder, mine=(BEAR, WINGS))
        kill(game, BEAR)
        assert on_battlefield(game, BEAR) == []


class TestTheValue:
    def test_a_trigger_that_never_fired_reads_zero(self, builder):
        game = position(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        assert evaluate_value(ctx, {"keywords_had": "flying"}) == 0

    def test_it_reads_the_snapshot(self, builder):
        game = position(builder)
        ctx = EffectContext(
            state=game.state, controller=0, source_oid=None,
            bindings={"had_keywords": ["flying", "vigilance"]},
        )
        assert evaluate_value(ctx, {"keywords_had": "vigilance"}) == 1
        assert evaluate_value(ctx, {"keywords_had": "trample"}) == 0


class TestTheLoaderRefuses:
    @pytest.mark.parametrize("word", ["flyng", True, ["flying"], {"keyword": "flying"}])
    def test_anything_but_one_implemented_keyword(self, word):
        card = CardModel.model_validate({
            "id": "t_kh_bad", "name": "Bad", "types": ["Creature"],
            "power": 1, "toughness": 1,
            "abilities": [{
                "kind": "triggered", "text": "x",
                "trigger": {"event": "creature_dies", "controller": "you", "condition": {
                    "cmp": "==", "left": {"keywords_had": word}, "right": {"const": 0}}},
                "effects": [{"op": "gain_life", "amount": 1}],
            }],
        })
        with pytest.raises(DslError, match="keywords_had"):
            compile_card(card)
