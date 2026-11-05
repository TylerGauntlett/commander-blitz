"""Doubling token creation until end of turn -- the `multiply_token_creation` op.

    Kaya, Geist Hunter — "-2: Until end of turn, if one or more tokens would be
    created under your control, twice that many of those tokens are created
    instead."

A `replace_token_creation` static says the same sentence without "until end of
turn", and it is read off a permanent for as long as that permanent is on the
battlefield. Kaya's -2 is a resolved ability, and the continuous effect it
creates lasts for its stated duration whatever becomes of the walker (611.2a).
Granting the static to Kaya would be a weaker card, ending the doubling the
moment she is attacked down or bounced in response to the token maker.

The rules claims:

* **611.2a -- it outlives its source.** Kaya dying, being exiled or returned to
  hand leaves the doubling in force for the rest of the turn.
* **514.2 -- it ends at cleanup.** The next turn's tokens are made at the
  printed count.
* **614.5 -- it is one more replacement, applied once.** It compounds with a
  Parallel Lives (four), and two of them in one turn are two effects (four),
  never merged into one.
* **"Under your control" is the ability's controller**, fixed as it resolves:
  an opponent's tokens are untouched.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, pass_until, settle

WALKER = "t_token_doubling_walker"
LIVES = "parallel_lives_doubler"
SOLDIER = "human_soldier_1_1_w"

DOUBLE_LINE = (
    "-2: Until end of turn, if one or more tokens would be created under your "
    "control, twice that many of those tokens are created instead."
)


def walker(**op_extra) -> dict:
    return {
        "id": WALKER,
        "name": "Token Doubling Walker",
        "mana_cost": "{3}{W}{B}",
        "types": ["Planeswalker"],
        "subtypes": ["Kaya"],
        "loyalty": 5,
        "abilities": [
            {
                "kind": "activated",
                "text": DOUBLE_LINE,
                "cost": {"loyalty": -2},
                "effects": [
                    {"op": "multiply_token_creation", "duration": "this_turn", **op_extra}
                ],
            }
        ],
    }


def parallel_lives() -> dict:
    return {
        "id": LIVES,
        "name": "Parallel Lives",
        "mana_cost": "{3}{G}",
        "types": ["Enchantment"],
        "abilities": [
            {
                "kind": "static",
                "text": (
                    "If one or more tokens would be created under your control, "
                    "twice that many of those tokens are created instead."
                ),
                "effect": "replace_token_creation",
                "token_multiplier": 2,
            }
        ],
    }


def compile_spec(spec: dict):
    return compile_card(CardModel.model_validate(spec))


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    cards = {
        card.id: card for card in CardRegistry.from_paths(authored_card_paths(Path("data/cards")))
    }
    for spec in (walker(), parallel_lives()):
        compiled = compile_spec(spec)
        cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


def position(pool: CardRegistry, mine=(WALKER,)):
    return (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, ["plains", *mine])
        .battlefield(1, ["plains"])
        # A land to play keeps the engine from auto-passing the turn away the
        # moment the -2 resolves.
        .hand(0, ["plains"])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def minus_two(game) -> None:
    oid = only_oid(game, WALKER)
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)
    settle(game)


def tokens(game, pid: int = 0) -> Counter:
    return Counter(obj.def_id for obj in game.state.battlefield_objects(pid) if obj.is_token)


class TestTwiceThatManyThisTurn:
    def test_without_it_the_printed_count(self, pool):
        game = position(pool)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 1}

    def test_after_the_minus_two_one_token_is_two(self, pool):
        game = position(pool)
        minus_two(game)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 2}

    def test_the_count_asked_for_is_what_is_doubled(self, pool):
        game = position(pool)
        minus_two(game)
        create_token(game.state, SOLDIER, 0, 3)
        assert tokens(game) == {SOLDIER: 6}

    def test_an_opponents_tokens_are_untouched(self, pool):
        game = position(pool)
        minus_two(game)
        create_token(game.state, SOLDIER, 1, 1)
        assert tokens(game, 1) == {SOLDIER: 1}

    def test_a_token_an_opponents_effect_gives_you_is_doubled(self, pool):
        """ "Created under your control", not "you create"."""
        game = position(pool)
        minus_two(game)
        ctx = EffectContext(state=game.state, controller=1, source_oid=None)
        list(execute(ctx, [{"op": "create_token", "token": SOLDIER, "controller": "opponent"}]))
        assert tokens(game, 0) == {SOLDIER: 2}


class TestItOutlivesItsSource:
    """611.2a: the effect of a resolved ability is not tied to the walker."""

    @pytest.mark.parametrize("zone", [Zone.GRAVEYARD, Zone.EXILE, Zone.HAND])
    def test_kaya_leaving_does_not_end_it(self, pool, zone):
        game = position(pool)
        minus_two(game)
        move_object(game.state, only_oid(game, WALKER), zone)
        assert not [o for o in game.state.battlefield_objects(0) if o.def_id == WALKER]
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 2}


class TestItEndsAtCleanup:
    def test_the_next_turn_makes_the_printed_count(self, pool):
        game = position(pool)
        minus_two(game)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert game.state.token_multipliers == []
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 1}

    def test_it_lasts_past_combat_into_the_second_main_phase(self, pool):
        game = position(pool)
        minus_two(game)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        assert game.state.turn == turn
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 2}


class TestItCompounds:
    """One more replacement of the creation, each applied once (614.5)."""

    def test_with_parallel_lives_one_token_is_four(self, pool):
        game = position(pool, mine=(WALKER, LIVES))
        minus_two(game)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 4}

    def test_two_resolutions_are_two_effects(self, pool):
        """Not deduplicated: a copied -2 is a second replacement, not the same one."""
        game = position(pool)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        spec = [{"op": "multiply_token_creation", "duration": "this_turn"}]
        list(execute(ctx, spec))
        list(execute(ctx, spec))
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 4}

    def test_it_does_not_redouble_its_own_output(self, pool):
        game = position(pool)
        minus_two(game)
        create_token(game.state, SOLDIER, 0, 1)
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 4}


    def test_the_multiplier_is_a_number(self, pool):
        """Not a constant 2: a `token_multiplier` of 3 makes three."""
        game = position(pool)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        spec = {"op": "multiply_token_creation", "duration": "this_turn", "token_multiplier": 3}
        list(execute(ctx, [spec]))
        create_token(game.state, SOLDIER, 0, 1)
        assert tokens(game) == {SOLDIER: 3}


class TestTheLoaderRefuses:
    def test_a_missing_duration(self, pool):
        spec = walker()
        del spec["abilities"][0]["effects"][0]["duration"]
        with pytest.raises(DslError, match="duration"):
            compile_spec(spec)

    def test_an_unknown_duration(self, pool):
        with pytest.raises(DslError, match="duration"):
            compile_spec(walker(duration="until_your_next_turn"))

    @pytest.mark.parametrize("bad", [1, 0, True, "2"])
    def test_a_multiplier_below_two_or_not_a_number(self, pool, bad):
        with pytest.raises(DslError, match="token_multiplier"):
            compile_spec(walker(token_multiplier=bad))

    @pytest.mark.parametrize(
        "key, value",
        [
            ("affects_token", {"types": ["Creature"]}),
            ("create_instead", [SOLDIER]),
            ("amount", 2),
        ],
    )
    def test_the_static_only_keys(self, pool, key, value):
        with pytest.raises(DslError, match=key):
            compile_spec(walker(**{key: value}))
