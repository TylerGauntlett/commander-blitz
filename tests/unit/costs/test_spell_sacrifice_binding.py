"""A spell's additional sacrifice cost that names the creature it sacrificed.

    Life's Legacy: "As an additional cost to cast this spell, sacrifice a
    creature. Draw cards equal to the sacrificed creature's power."

`cost.sacrifice.as` already named the sacrificed permanent for an activated
ability (Ghoulcaller Gisa, `test_sacrifice_cost_binding.py`). The same name on
a spell's `additional_cost` is the same snapshot handed to a different reader:
`Game._cast` gives the payment a place to write it and binds it on the spell's
stack item, so the resolving `spell_effects` read it.

The rules argument is the activated ability's. The creature is sacrificed as
the spell is cast (601.2h), so by the time the spell resolves it is gone and
"the sacrificed creature's power" is its last-known information (608.2h): a
pump or counters it had count, a token that ceased to exist still has a power,
and nothing done in response changes the number. A copy of the spell (707.10)
copies the choices made in paying its additional costs, so it draws the same
number -- the copy carries the original's bindings, as it carries `as_cast`'s.

The near miss is the `sacrifice` **op** with `snapshot` in `spell_effects`,
which pays on resolution: the spell could be cast with no creature at all.

The witnesses are Life's Legacy and Rite of Consumption (`data/cards/auto/`);
`t_legacy` is their shape.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, pump
from tests.conftest import only_oid, settle_to_priority

LEGACY = "t_legacy"
OPTIONAL = "t_legacy_optional"
FORK = "t_fork"  # {U}{R}, copy target instant or sorcery spell
BEAR = "t_bear"  # 2/2
GIANT = "t_big"  # 6/6


def position(builder, *creatures: str, hand=(LEGACY,)):
    """Player 0 with mana for the spell and a Fork, ``creatures`` to feed it.

    The opponent's Bolt is never cast. It keeps their priority window from
    holding nothing but "pass", which would be passed automatically and let
    the spell resolve before a test could look at the stack.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest", "forest", "island", "mountain"])
        .battlefield(0, list(creatures))
        .battlefield(1, ["mountain"])
        .hand(1, ["t_bolt"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .hand(0, list(hand))
        .build()
    )
    return game


def cast_lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def cast(game, creature: int | None, *, card_id: str = LEGACY, times: int = 1) -> None:
    """Cast ``card_id`` paying its additional cost ``times``, sacrificing ``creature``."""
    game.apply(next(a for a in cast_lines(game, card_id) if a.additional_times == times))
    if creature is None:
        return
    choose = next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and creature in [t.id for t in a.targets]
        ),
        None,
    )
    if choose is not None:
        game.apply(choose)


def library(game) -> int:
    return len(game.state.players[0].library)


class TestWhenItIsOffered:
    def test_a_creature_makes_it_castable(self, builder):
        game = position(builder, BEAR)
        assert cast_lines(game, LEGACY)

    def test_with_no_creature_it_is_not_castable(self, builder):
        """The sacrifice is a cost: nothing to sacrifice, no cast."""
        game = position(builder)
        assert cast_lines(game, LEGACY) == []


class TestItReadsTheSacrificedCreature:
    def test_the_creature_is_gone_before_the_spell_resolves(self, builder):
        game = position(builder, BEAR)
        bear = only_oid(game, BEAR)

        cast(game, bear)

        assert game.state.stack, "the spell should still be on the stack"
        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_it_draws_cards_equal_to_the_sacrificed_creatures_power(self, builder):
        game = position(builder, GIANT)
        before = library(game)

        cast(game, only_oid(game, GIANT))
        settle_to_priority(game)

        assert before - library(game) == 6

    def test_it_reads_the_creature_that_was_sacrificed_not_another(self, builder):
        game = position(builder, BEAR, GIANT)
        before = library(game)

        cast(game, only_oid(game, BEAR))
        settle_to_priority(game)

        assert before - library(game) == 2
        assert game.state.objects[only_oid(game, GIANT)].on_battlefield

    def test_the_binding_rides_on_the_stack_item(self, builder):
        game = position(builder, BEAR)
        cast(game, only_oid(game, BEAR))

        assert game.state.stack[-1].bindings["sacrificed"]["power"] == 2


class TestItIsTheLastKnownPower:
    def test_a_pump_before_the_sacrifice_counts(self, builder):
        """608.2h: read off the graveyard card it would be the printed 2."""
        game = position(builder, BEAR)
        bear = only_oid(game, BEAR)
        pump(game.state, bear, 3, 3)
        before = library(game)

        cast(game, bear)
        settle_to_priority(game)

        assert before - library(game) == 5

    def test_counters_on_it_count(self, builder):
        game = position(builder, BEAR)
        bear = only_oid(game, BEAR)
        add_counters(game.state, bear, "+1/+1", 2)
        before = library(game)

        cast(game, bear)
        settle_to_priority(game)

        assert before - library(game) == 4


class TestACopySeesTheSameCreature:
    def test_a_copy_draws_the_same_number(self, builder):
        """707.10: the copy copies the choices made paying the original's
        additional cost, so it reads the same sacrificed creature."""
        game = position(builder, BEAR, hand=(LEGACY, FORK))
        before = library(game)

        cast(game, only_oid(game, BEAR))
        game.apply(next(iter(cast_lines(game, FORK))))
        settle_to_priority(game)

        assert before - library(game) == 2 + 2


class TestAnOptionalCost:
    def test_declining_it_draws_nothing(self, builder):
        """"You may sacrifice": declined, there is no sacrificed creature and
        no power to read."""
        game = position(builder, BEAR, hand=(OPTIONAL,))
        before = library(game)

        cast(game, None, card_id=OPTIONAL, times=0)
        settle_to_priority(game)

        assert before - library(game) == 0
        assert game.state.objects[only_oid(game, BEAR)].on_battlefield

    def test_paying_it_draws_its_power(self, builder):
        game = position(builder, BEAR, hand=(OPTIONAL,))
        before = library(game)

        cast(game, only_oid(game, BEAR), card_id=OPTIONAL, times=1)
        settle_to_priority(game)

        assert before - library(game) == 2


SPELL = {
    "id": "t_legacy_guard",
    "name": "Test Legacy Guard",
    "oracle_text": "As an additional cost, sacrifice a creature. Draw X.",
    "mana_cost": "{G}",
    "types": ["Sorcery"],
    "additional_cost": {"sacrifice": {"types": ["Creature"], "as": "eaten"}},
    "spell_effects": [{"op": "draw", "amount": {"power_of": {"binding": "eaten"}}}],
}


class TestLoadTimeGuards:
    def test_the_named_additional_cost_loads(self):
        card = compile_card(CardModel.model_validate(SPELL))
        assert card.additional_cost.sacrifice["as"] == "eaten"

    def test_a_named_branch_of_additional_cost_options_loads(self):
        spell = copy.deepcopy(SPELL)
        spell["additional_cost_options"] = [
            spell.pop("additional_cost"),
            {"pay_life": 3},
        ]
        card = compile_card(CardModel.model_validate(spell))
        assert card.additional_cost_options[0].sacrifice["as"] == "eaten"

    def test_a_repeatable_cost_is_refused(self):
        """Paid any number of times, no one creature is *the* sacrificed one."""
        spell = copy.deepcopy(SPELL)
        spell["additional_optional"] = True
        spell["additional_repeatable"] = True
        with pytest.raises(DslError, match="repeatable"):
            compile_card(CardModel.model_validate(spell))

    def test_naming_one_of_several_is_refused(self):
        spell = copy.deepcopy(SPELL)
        spell["additional_cost"]["sacrifice"]["count"] = 2
        with pytest.raises(DslError, match="exactly one"):
            compile_card(CardModel.model_validate(spell))

    def test_an_alternative_cost_still_names_it_for_nothing(self):
        """Only the additional cost's payment is handed a place to write it."""
        spell = copy.deepcopy(SPELL)
        spell["alternative_cost"] = spell.pop("additional_cost")
        with pytest.raises(DslError, match="names it for nothing"):
            compile_card(CardModel.model_validate(spell))
