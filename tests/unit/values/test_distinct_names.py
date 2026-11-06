"""`{"distinct": {"of": "name"}}` -- how many *names* a pool holds.

    Neriv, Crackling Vanguard -- "exile a number of cards from the top of your
    library equal to **the number of differently named tokens you control**."

`count` over tokens counts objects, and `most_sharing_a_name` measures the
largest group sharing one name; neither says how many names there are. Two
Goblin tokens and a Treasure are three tokens, a largest group of two, and two
names.

A token's name is the one its definition carries (111.4): its subtypes plus
"Token" unless the creating effect names it. That is why two Soldier tokens that
differ in colour and abilities are still **one** name -- they are both "Soldier
Token" -- and the reading here is `card_of(...).name`, the same one
`shares_a_name_with` and `most_sharing_a_name` take, because nothing in the
characteristics layer renames an object. A face-down permanent has no name
(708.2a) and adds none.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token

GOBLIN = "goblin_1_1_r"                    # "Goblin Token"
TREASURE = "treasure_token"                # "Treasure"
SOLDIER = "soldier_1_1_c"                  # "Soldier Token"
LIFELINK_SOLDIER = "soldier_1_1_w_lifelink"  # also "Soldier Token"
BEAR = "t_bear"

MY_TOKENS = {"controller": "you", "is_token": True}


def names(objects=None):
    return {"distinct": {"of": "name", "objects": objects or MY_TOKENS}}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def board(builder, tokens: dict[int, list[str]], cards: list[str] = ()):
    game = builder(players=2).battlefield(0, list(cards)).build(advance=False)
    made: list[int] = []
    for pid, ids in tokens.items():
        for def_id in ids:
            made += create_token(game.state, def_id, pid)
    return game, made


class TestCountsNamesNotTokens:
    def test_tokens_sharing_a_name_count_once(self, builder):
        game, _ = board(builder, {0: [GOBLIN, GOBLIN]})
        assert value(game, names()) == 1, "two Goblin tokens are one name"

    def test_each_different_name_adds_one(self, builder):
        game, _ = board(builder, {0: [GOBLIN, GOBLIN, TREASURE]})
        assert value(game, names()) == 2

    def test_differently_built_tokens_with_one_name_are_one(self, builder):
        """111.4: the name is the subtypes plus "Token", not the whole token."""
        game, _ = board(builder, {0: [SOLDIER, LIFELINK_SOLDIER]})
        assert value(game, names()) == 1

    def test_no_tokens_is_zero(self, builder):
        game, _ = board(builder, {}, cards=[BEAR])
        assert value(game, names()) == 0


class TestThePool:
    def test_a_nontoken_is_outside_the_selector(self, builder):
        game, _ = board(builder, {0: [GOBLIN]}, cards=[BEAR])
        assert value(game, names()) == 1

    def test_an_opponents_tokens_are_not_yours(self, builder):
        game, _ = board(builder, {0: [GOBLIN], 1: [TREASURE, SOLDIER]})
        assert value(game, names()) == 1
        assert value(game, names(), controller=1) == 2

    def test_a_face_down_permanent_has_no_name(self, builder):
        """708.2a: a face-down permanent has no name, so it adds none."""
        game, made = board(builder, {0: [GOBLIN, TREASURE]})
        game.state.objects[made[1]].face_down = True
        assert value(game, names()) == 1


class TestValidation:
    def test_name_is_accepted(self):
        validate_value(names(), "t")

    def test_spells_cast_this_turn_stays_colors_only(self):
        with pytest.raises(DslError, match="colors only"):
            validate_value(
                {"distinct": {"of": "name", "objects": MY_TOKENS, "spells_cast_this_turn": "you"}},
                "t",
            )
