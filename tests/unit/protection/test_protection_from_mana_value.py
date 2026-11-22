""""Protection from mana value 3 or less" -- 702.16, 202.3

    Reaver Titan -- "Void Shields — Protection from mana value 3 or less"
    Mistmeadow Skulk -- "Lifelink, protection from mana value 3 or greater"

Protection is "from [quality]" (702.16a), and mana value is a quality no
existing key could spell. `_matches_protection` intersects the qualities with
the source's types, subtypes and colours; mana value is a *number*, so the
quality has to be compared, not intersected. Without it, the closest an author
could get is protection from some list of types or colours -- which protects
from the wrong things in both directions.

The `protection` static takes ``from_mana_value: {"op": "<=", "value": 3}``,
stored as one more string in the flat set of qualities the four rules --
damage, enchant/equip, block, target -- already read.

The boundaries that matter: the comparison is inclusive at the printed number;
a token or a land is mana value 0 and so is "3 or less" (202.3a); a spell on
the stack counts the X it was cast with (202.3e).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import protected_from, protection_from
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach, damage_permanent
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.structs import (
    CombatState,
    StackItem,
    mana_value_quality,
    parse_mana_value_quality,
)
from commanderblitz.engine.targeting import can_be_targeted, target_refusal
from tests.conftest import only_oid

THREE = "t_mv3"  # {2}{G} 3/3
FOUR = "t_mv4"  # {3}{G} 4/4
APE = "ape_3_3_g"  # a 3/3 token -- mana value 0
FIREBALL = "t_fireball"  # {X}{R}


def shielded(op: str, value: int = 3) -> CardModel:
    return CardModel.model_validate(
        {
            "id": f"t_mv_shielded_{'le' if op == '<=' else 'ge'}",
            "name": "Mana Value Shielded",
            "oracle_text": f"Protection from mana value {value} or "
            f"{'less' if op == '<=' else 'greater'}",
            "mana_cost": "{4}{W}",
            "types": ["Creature"],
            "colors": ["W"],
            "color_identity": ["W"],
            "power": 5,
            "toughness": 5,
            "abilities": [
                {
                    "kind": "static",
                    "effect": "protection",
                    "affects": {"self_only": True},
                    "from_mana_value": {"op": op, "value": value},
                }
            ],
        }
    )


def board(registry, op: str = "<=", *, hand: list[str] | None = None):
    """Our shielded 5/5; their three-drop, four-drop and a 3/3 token."""
    model = shielded(op)
    cards = {card.id: card for card in registry}
    cards[model.id] = compile_card(model)
    game = (
        GameBuilder(CardRegistry(cards), players=2)
        .battlefield(0, [model.id])
        .battlefield(1, [THREE, FOUR, APE])
        .hand(1, hand or [])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .active(0)
        .build()
    )
    return (
        game,
        only_oid(game, model.id, 0),
        only_oid(game, THREE, 1),
        only_oid(game, FOUR, 1),
        only_oid(game, APE, 1),
    )


class TestTheQuality:
    def test_the_static_installs_the_printed_words(self, registry):
        game, me, _, _, _ = board(registry)
        assert protection_from(game.state, me) == frozenset({"mana value 3 or less"})

    @pytest.mark.parametrize("op", ["<=", ">="])
    def test_the_string_round_trips(self, op):
        assert parse_mana_value_quality(mana_value_quality(op, 3)) == (op, 3)

    @pytest.mark.parametrize("word", ["Wizard", "mana value", "mana value x or less"])
    def test_anything_else_is_not_a_comparison(self, word):
        assert parse_mana_value_quality(word) is None


class TestOrLessAcrossTheFourRules:
    """Reaver Titan: each rule paired with a source one over the line."""

    def test_damage_from_it_is_prevented(self, registry):
        game, me, three, four, _ = board(registry)
        assert damage_permanent(game.state, me, 2, three) == 0
        assert damage_permanent(game.state, me, 2, four) == 2

    def test_it_cannot_be_targeted_by_it(self, registry):
        game, me, three, four, _ = board(registry)
        assert not can_be_targeted(game.state, 1, me, source_oid=three)
        assert can_be_targeted(game.state, 1, me, source_oid=four)

    def test_the_reason_reads_like_the_card(self, registry):
        game, me, three, _, _ = board(registry)
        assert (
            target_refusal(game.state, 1, me, source_oid=three)
            == "Protection from mana value 3 or less"
        )

    def test_protection_stops_its_own_controller_too(self, registry):
        game, me, three, _, _ = board(registry)
        assert not can_be_targeted(game.state, 0, me, source_oid=three)

    def test_it_cannot_be_blocked_by_it(self, registry):
        game, me, three, four, _ = board(registry)
        game.state.combat = CombatState()
        game.state.combat.attackers[me] = 1
        game.state.bump_chars()

        assert not can_block(game.state, three, me, 1)
        assert can_block(game.state, four, me, 1)

    def test_it_cannot_be_enchanted_or_equipped_by_it(self, registry):
        """The attach primitive is asked directly, as the colorless test asks it:
        mana value 3 is refused, mana value 4 attaches."""
        game, me, three, four, _ = board(registry)
        assert not attach(game.state, three, me)
        assert game.state.objects[three].attached_to is None

        assert attach(game.state, four, me)


class TestTheBoundaries:
    def test_a_token_is_mana_value_zero(self, registry):
        """202.3a: a token's mana value is 0, so a 3/3 Ape is "3 or less"."""
        game, me, _, _, ape = board(registry)
        assert protected_from(game.state, me, ape)

    def test_or_greater_lets_the_token_through(self, registry):
        """Mistmeadow Skulk, from the other side of the same line."""
        game, me, three, four, ape = board(registry, ">=")
        assert protected_from(game.state, me, three), "3 is 3 or greater"
        assert protected_from(game.state, me, four)
        assert not protected_from(game.state, me, ape)

    def test_a_spell_on_the_stack_counts_its_x(self, registry):
        """202.3e: Fireball for X = 3 is mana value 4, and passes "3 or less";
        in hand it is mana value 1 and is stopped."""
        game, me, _, _, _ = board(registry, hand=[FIREBALL])
        (fireball,) = game.state.players[1].hand
        assert protected_from(game.state, me, fireball)

        game.state.stack.append(
            StackItem(sid=1, kind="spell", controller=1, def_id=FIREBALL, oid=fireball, x=3)
        )
        assert not protected_from(game.state, me, fireball)

    def test_a_missing_source_is_never_protection(self, registry):
        game, me, _, _, _ = board(registry)
        assert not protected_from(game.state, me, None)


class TestTheLoaderRefusesNonsense:
    def _static(self, static: dict):
        return CardModel.model_validate(
            {
                "id": "t_bad_static",
                "name": "Bad Static",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [{"kind": "static", "affects": {"self_only": True}, **static}],
            }
        )

    def test_the_comparison_alone_is_a_quality(self):
        compile_card(
            self._static({"effect": "protection", "from_mana_value": {"op": ">=", "value": 3}})
        )

    @pytest.mark.parametrize(
        "spec",
        [{"value": 3}, {"op": "<=", "value": 3, "or": 1}],
    )
    def test_the_shape_is_op_and_value(self, spec):
        with pytest.raises(DslError, match="from_mana_value is"):
            compile_card(self._static({"effect": "protection", "from_mana_value": spec}))

    @pytest.mark.parametrize("op", ["<", ">", "==", "less"])
    def test_only_the_printed_operators(self, op):
        with pytest.raises(DslError, match="is not one of"):
            compile_card(
                self._static({"effect": "protection", "from_mana_value": {"op": op, "value": 3}})
            )

    @pytest.mark.parametrize("value", [-1, "3", True, {"count": "x"}])
    def test_the_value_is_a_literal_number(self, value):
        with pytest.raises(DslError, match="literal non-negative integer"):
            compile_card(
                self._static(
                    {"effect": "protection", "from_mana_value": {"op": "<=", "value": value}}
                )
            )

    def test_it_needs_the_protection_effect(self):
        with pytest.raises(DslError, match="need effect 'protection'"):
            compile_card(
                self._static(
                    {
                        "effect": "grant_keyword",
                        "keywords": ["flying"],
                        "from_mana_value": {"op": "<=", "value": 3},
                    }
                )
            )

    def test_the_quality_string_is_not_a_subtype(self):
        """`from_subtypes` is not checked against a subtype list, so the
        printed words would otherwise load as the quality without the key."""
        with pytest.raises(DslError, match="is not a subtype"):
            compile_card(
                self._static({"effect": "protection", "from_subtypes": ["mana value 3 or less"]})
            )
