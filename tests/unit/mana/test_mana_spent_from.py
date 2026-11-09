""""For each mana from a Desert spent to cast this spell" -- a count of units.

    Cataclysmic Prospecting — "Cataclysmic Prospecting deals X damage to each
    creature. For each mana from a Desert spent to cast this spell, create a
    tapped Treasure token."

Rule 106.3 makes mana an object of its own that a permanent's ability produced,
and "for each mana from a Desert" counts those units, not the Deserts. The
engine already remembered what each pip's source was (`mana.ManaOrigin`,
snapshotted because a Treasure is gone by the time anything asks), but only as
a **set** on the cast object, which `paid_by` asks "any?" of: two mana from one
Desert are one entry there, and a count read off it would make Cataclysmic
Prospecting a weaker card whenever a Desert taps for more than one.

So `pay_mana` also keeps one `ManaOrigin` per pip spent
(`GameObject.mana_spent_origins`), and the `mana_spent_from` value counts those
whose source matched a `paid_by`-style filter. Which pip of a colour is spent
is the pool's newest-first rule (rules-coverage "Which same-coloured mana gets
spent"), so a land tapped for this cast is the mana that paid for it. The
record belongs to this object's cast: it survives the move onto the
battlefield, so an enters trigger reads it, and is cleared on any other move,
so a card cast again starts over. `t_desert_prospect` is the witness on a fixed
cost.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, settle_completely

PROSPECT = "t_desert_prospect"
DIGGER = "t_desert_digger"
DESERT = "t_red_desert"
TWIN = "t_twin_desert"
TREASURE = "treasure_token"


def cast(builder, card_id: str, lands):
    game = builder(players=2).battlefield(0, list(lands)).hand(0, [card_id]).build()
    oid = action_for_card(game, ActionKind.CAST, card_id).source
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle_completely(game)
    return game, oid


def treasures(game):
    return [o for o in game.state.battlefield_objects(0) if o.def_id == TREASURE]


class TestTheCount:
    def test_every_mana_from_a_desert(self, builder):
        game, _ = cast(builder, PROSPECT, [DESERT] * 3)
        assert len(treasures(game)) == 3

    def test_only_the_desert_mana(self, builder):
        game, _ = cast(builder, PROSPECT, [DESERT, "mountain", "mountain"])
        assert len(treasures(game)) == 1

    def test_no_desert_no_treasure(self, builder):
        game, _ = cast(builder, PROSPECT, ["mountain"] * 3)
        assert treasures(game) == []

    def test_two_mana_from_one_desert_are_two(self, builder):
        """The set of sources holds one entry; the count is of units."""
        game, oid = cast(builder, PROSPECT, [TWIN, "mountain"])
        assert len(treasures(game)) == 2
        traits = game.state.objects[oid].mana_spent_traits
        assert len([t for t in traits if "Desert" in t.subtypes]) == 1

    def test_the_treasures_are_tapped(self, builder):
        game, _ = cast(builder, PROSPECT, [DESERT] * 3)
        assert all(t.tapped for t in treasures(game))


class TestWhoseCastItIs:
    def test_a_permanent_reads_its_own_cast(self, builder):
        """The record survives the move from the stack onto the battlefield."""
        game, _ = cast(builder, DIGGER, [DESERT, DESERT, "mountain"])
        assert len(treasures(game)) == 2

    def test_a_card_cast_again_starts_over(self, builder):
        game, oid = cast(builder, DIGGER, [DESERT] * 3)
        assert len(game.state.objects[oid].mana_spent_origins) == 3
        move_object(game.state, oid, Zone.HAND, to_player=0)
        assert game.state.objects[oid].mana_spent_origins == ()


class TestLoaderRefusals:
    def _card(self, amount) -> CardModel:
        return CardModel(
            id="t_mana_spent_from_probe",
            name="Mana Spent From Probe",
            mana_cost="{R}",
            types=["Sorcery"],
            spell_effects=[{"op": "create_token", "token": TREASURE, "amount": amount}],
        )

    def test_the_witness_shape_loads(self):
        compile_card(self._card({"mana_spent_from": {"subtypes": ["Desert"]}}))

    def test_an_empty_filter(self):
        with pytest.raises(DslError, match="mana_spent_of"):
            compile_card(self._card({"mana_spent_from": {}}))

    def test_a_key_a_memory_cannot_answer(self):
        with pytest.raises(DslError, match="tapped"):
            compile_card(self._card({"mana_spent_from": {"tapped": True}}))

    def test_an_unknown_controller(self):
        with pytest.raises(DslError, match="controller"):
            compile_card(self._card({"mana_spent_from": {"controller": "each_opponent"}}))
