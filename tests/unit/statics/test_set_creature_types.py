"""The `set_creature_types` static -- "it loses all other creature types".

    Celebration -- As long as two or more nonland permanents entered the
    battlefield under your control this turn, Goddric is a Dragon with base
    power and toughness 4/4, flying, and ... (It loses all other creature
    types.)                                     -- Goddric, Cloaked Reveler
    Enchanted creature loses all abilities and is a green Elk creature with
    base power and toughness 3/3. (It loses all other card types and creature
    types.)                                     -- Kenrith's Transformation

613.1d puts type-changing effects in layer 4, and the parenthetical makes this
one a **replacement**: the creature types become exactly the printed list. Every
near miss is a stronger or weaker card. `set_types: ["Creature"]` keeps Human
and Noble because Creature stays (205.1b drops only the subtypes of a type that
went); `add_subtype` makes a Human Noble Dragon that a Human filter still finds;
`animate` with `exact` replaces the types but is a one-shot with a duration and
cannot switch off with a condition or an Aura.

What it must not touch is pinned beside what it changes: card types and
supertypes stay (a legendary Goddric stays legendary), and so do subtypes that
are not creature types (205.3m) -- an Equipment Cat is an Equipment Elk. The
named types arrive only on a creature (205.3d).

"Nonland permanents" is the entered-filter's `not_types`, which Celebration
needs and which is tested here because this card is its witness: a land drop
is a permanent entering and must not count.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars, creature_types_of
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import only_oid, static_probe

REVELER = "t_sct_reveler"
ELK_CURSE = "t_sct_elk_curse"
ELK_MARK = "t_sct_elk_mark"
SASH = "t_sct_sash"
IDOL = "t_sct_idol"
SPIRIT = "t_sct_spirit"


def position(builder, mine=(REVELER,), hand=(), aura: str | None = None):
    """A board standing since before this turn, ``hand`` held by player 0.

    ``aura`` is placed on player 0's side already attached to the first
    permanent, before the game is built -- an unattached Aura would be put
    into the graveyard by the first state-based check. Returns
    ``(game, first permanent's oid)``.
    """
    setup = (
        builder(players=2)
        .battlefield(0, list(mine))
        .hand(0, list(hand))
        .library(0, ["forest"] * 10)
    )
    host = next(
        o for o in setup.state.battlefield if setup.state.objects[o].def_id == mine[0]
    )
    if aura is not None:
        setup.battlefield(0, [aura])
        assert attach(setup.state, setup.state.battlefield[-1], host)
    game = setup.build()
    return game, host


def arrive(game, card_id: str) -> int:
    """Put one card from player 0's hand onto the battlefield -- an arrival."""
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)
    move_object(game.state, oid, Zone.BATTLEFIELD)
    return oid


class TestCelebration:
    def test_without_the_condition_it_is_its_printed_types(self, builder):
        game, reveler = position(builder)
        assert set(chars(game.state, reveler).subtypes) == {"Human", "Noble"}

    def test_two_nonland_arrivals_make_it_exactly_a_dragon(self, builder):
        game, reveler = position(builder, hand=(SPIRIT, SPIRIT))
        arrive(game, SPIRIT)
        assert "Dragon" not in chars(game.state, reveler).subtypes, "one is not two"
        arrive(game, SPIRIT)
        got = chars(game.state, reveler)
        assert set(got.subtypes) == {"Dragon"}, "Human and Noble are gone"
        assert creature_types_of(game.state, reveler) == {"Dragon"}

    def test_card_types_and_supertypes_are_untouched(self, builder):
        game, reveler = position(builder, hand=(SPIRIT, SPIRIT))
        arrive(game, SPIRIT)
        arrive(game, SPIRIT)
        got = chars(game.state, reveler)
        assert set(got.types) == {"Creature"}
        assert "Legendary" in got.supertypes

    def test_a_land_entering_does_not_count(self, builder):
        game, reveler = position(builder, hand=(SPIRIT, "forest"))
        arrive(game, SPIRIT)
        arrive(game, "forest")
        assert set(chars(game.state, reveler).subtypes) == {"Human", "Noble"}

    def test_an_arrival_that_died_still_entered(self, builder):
        game, reveler = position(builder, hand=(SPIRIT, SPIRIT))
        arrive(game, SPIRIT)
        destroy(game.state, arrive(game, SPIRIT))
        assert set(chars(game.state, reveler).subtypes) == {"Dragon"}

    def test_it_wears_off_with_the_turn(self, builder):
        game, reveler = position(builder, hand=(SPIRIT, SPIRIT))
        arrive(game, SPIRIT)
        arrive(game, SPIRIT)
        game.state.turn_ledger.permanents_entered.clear()
        game.state.bump_chars()
        assert set(chars(game.state, reveler).subtypes) == {"Human", "Noble"}


class TestTheAuraReplacesBothLines:
    def enchant(self, builder, creature: str):
        game, host = position(builder, mine=(creature,), aura=ELK_CURSE)
        return game, host, only_oid(game, ELK_CURSE, 0)

    def test_a_human_noble_is_an_elk(self, builder):
        game, host, _ = self.enchant(builder, REVELER)
        got = chars(game.state, host)
        assert set(got.subtypes) == {"Elk"}
        assert set(got.types) == {"Creature"}

    def test_an_artifact_equipment_cat_loses_artifact_and_its_creature_types(self, builder):
        """`set_types` takes Artifact and its Equipment; this takes Cat and Samurai."""
        game, host, _ = self.enchant(builder, SASH)
        got = chars(game.state, host)
        assert set(got.types) == {"Creature"}
        assert set(got.subtypes) == {"Elk"}

    def test_it_ends_when_the_aura_leaves(self, builder):
        game, host, curse = self.enchant(builder, REVELER)
        destroy(game.state, curse)
        assert set(chars(game.state, host).subtypes) == {"Human", "Noble"}


class TestOnlyCreatureTypesMove:
    def test_a_non_creature_subtype_and_the_card_types_stay(self, builder):
        """205.3m: Equipment is an artifact type, not a creature type."""
        game, sash = position(builder, mine=(SASH,), aura=ELK_MARK)
        got = chars(game.state, sash)
        assert set(got.subtypes) == {"Equipment", "Elk"}
        assert set(got.types) == {"Artifact", "Creature"}

    def test_a_noncreature_gains_no_creature_type(self, builder):
        """205.3d: an object can't have a subtype of a card type it lacks."""
        game, idol = position(builder, mine=(IDOL,))
        assert set(chars(game.state, idol).subtypes) == set()


class TestTheLoaderRefuses:
    def _compile(self, **static):
        return compile_card(
            CardModel.model_validate(
                static_probe({"effect": "set_creature_types", "affects": {"self_only": True}, **static})
            )
        )

    def test_it_needs_the_types_it_sets(self):
        with pytest.raises(DslError, match="needs the creature types"):
            self._compile()

    def test_a_non_creature_subtype_is_refused(self):
        with pytest.raises(DslError, match="not a creature type"):
            self._compile(subtypes=["Equipment"])

    def test_the_chosen_type_leaf_is_refused(self):
        with pytest.raises(DslError, match="add_subtype"):
            self._compile(subtypes=[{"chosen_type_of": "self"}])

    def test_card_types_belong_to_set_types(self):
        with pytest.raises(DslError, match="takes no 'types'"):
            self._compile(subtypes=["Elk"], types=["Creature"])

    def test_the_printed_shape_loads(self):
        self._compile(subtypes=["Dragon"])

    def test_an_empty_entered_not_types_is_refused(self):
        with pytest.raises(DslError, match="not_types"):
            self._compile(
                subtypes=["Dragon"],
                condition={
                    "cmp": ">=",
                    "left": {"permanents_entered_this_turn": {"controller": "you", "not_types": []}},
                    "right": {"const": 2},
                },
            )
