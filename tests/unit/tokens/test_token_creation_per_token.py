"""Adding "that many" tokens to a token creation: an addition counted per token.

    Chatterfang, Squirrel General: "If one or more tokens would be created under
    your control, those tokens plus that many 1/1 green Squirrel creature tokens
    are created instead."

A 614.1a replacement of the creation, and `and_create` (Stridehangar
Automaton's "those tokens plus an additional …") with `and_create_per_token`:
the pending tokens are all kept and each listed id is added once per matched
token in the event rather than once per event. Without the flag three Treasures
bring one Squirrel, which is a weaker card; a doubler would double the Treasures
rather than add Squirrels, and a `token_created` trigger uses the stack and
re-triggers on its own Squirrels forever.

The rules claims:

* **That many.** One token brings one Squirrel, three bring three.
* **Under your control.** An opponent's tokens bring nothing.
* **614.5.** The Squirrels are part of the event Chatterfang already replaced,
  so they are not replaced again by it: one Treasure is one Treasure and one
  Squirrel, and the creation terminates.
* **616.1, the controller's order.** Not asked; additions go first, so beside
  Doubling Season in either battlefield order one Treasure is two Treasures and
  two Squirrels. A fixed addition goes before the per-token one, so a
  Stridehangar's Thopter is counted too.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.sandbox import GameBuilder

CHATTERFANG = "chatterfang_probe"
SECOND = "chatterfang_probe_two"
AUTOMATON = "stridehangar_probe"
DOUBLING_SEASON = "doubling_season"
SQUIRREL = "squirrel_1_1_g"
TREASURE = "treasure_token"
THOPTER = "thopter_1_1_c_flying"

LINE = (
    "If one or more tokens would be created under your control, those tokens plus "
    "that many 1/1 green Squirrel creature tokens are created instead."
)


def chatterfang(card_id: str = CHATTERFANG, **extra) -> dict:
    static = {
        "kind": "static",
        "text": LINE,
        "effect": "replace_token_creation",
        "and_create": [SQUIRREL],
        "and_create_per_token": True,
        **extra,
    }
    return {
        "id": card_id,
        "name": "Chatterfang, Squirrel General",
        "mana_cost": "{2}{G}",
        "types": ["Creature"],
        "supertypes": ["Legendary"],
        "subtypes": ["Squirrel", "Warrior"],
        "power": 3,
        "toughness": 3,
        "abilities": [static],
    }


def automaton() -> dict:
    return {
        "id": AUTOMATON,
        "name": "Stridehangar Automaton",
        "mana_cost": "{3}",
        "types": ["Artifact", "Creature"],
        "subtypes": ["Construct"],
        "power": 2,
        "toughness": 2,
        "abilities": [
            {
                "kind": "static",
                "text": "Those tokens plus an additional Thopter.",
                "effect": "replace_token_creation",
                "affects_token": {"types": ["Artifact"]},
                "and_create": [THOPTER],
            }
        ],
    }


def with_cards(*specs: dict) -> CardRegistry:
    cards = {
        card.id: card for card in CardRegistry.from_paths(authored_card_paths(Path("data/cards")))
    }
    for spec in specs:
        compiled = compile_card(CardModel.model_validate(spec))
        cards[compiled.id] = compiled
    validate_token_references(cards)
    return CardRegistry(cards)


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    return with_cards(chatterfang(), chatterfang(SECOND), automaton())


def board(pool: CardRegistry, mine: list[str]):
    return GameBuilder(pool, players=2, seed=0).battlefield(0, list(mine)).build(advance=False)


def tokens(game, pid: int | None = None) -> Counter:
    return Counter(obj.def_id for obj in game.state.battlefield_objects(pid) if obj.is_token)


class TestThatManySquirrels:
    def test_one_token_brings_one_squirrel(self, pool):
        game = board(pool, [CHATTERFANG])
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1, SQUIRREL: 1}

    def test_three_tokens_bring_three_squirrels(self, pool):
        game = board(pool, [CHATTERFANG])
        create_token(game.state, TREASURE, 0, 3)
        assert tokens(game) == {TREASURE: 3, SQUIRREL: 3}

    def test_the_squirrels_are_in_the_same_batch_and_nothing_uses_the_stack(self, pool):
        game = board(pool, [CHATTERFANG])
        mark = len(game.state.events)
        create_token(game.state, TREASURE, 0, 2)
        made = [e for e in game.state.events[mark:] if e.type == "token_created"]
        assert len(made) == 4
        assert len({e.data.get("batch") for e in made}) == 1
        assert not game.state.stack and not game.state.pending_triggers


class TestUnderYourControl:
    def test_an_opponents_tokens_bring_nothing(self, pool):
        game = board(pool, [CHATTERFANG])
        create_token(game.state, TREASURE, 1, 2)
        assert tokens(game, 1) == {TREASURE: 2}
        assert tokens(game, 0) == {}


class TestOncePerReplacement:
    """614.5: Chatterfang applies once to the event as the last one left it."""

    def test_its_own_squirrels_are_not_replaced_again(self, pool):
        game = board(pool, [CHATTERFANG])
        create_token(game.state, SQUIRREL, 0, 1)
        assert tokens(game) == {SQUIRREL: 2}

    def test_a_second_chatterfang_counts_the_first_ones_squirrels(self, pool):
        """1 Treasure → Treasure + Squirrel → that plus two more Squirrels."""
        game = board(pool, [CHATTERFANG, SECOND])
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1, SQUIRREL: 3}


class TestTheControllersOrder:
    """616.1 is not asked; additions go first, the battlefield order does not matter."""

    @pytest.mark.parametrize(
        "order", [[CHATTERFANG, DOUBLING_SEASON], [DOUBLING_SEASON, CHATTERFANG]]
    )
    def test_beside_a_doubler_the_squirrels_are_doubled_too(self, pool, order):
        game = board(pool, order)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 2, SQUIRREL: 2}

    @pytest.mark.parametrize("order", [[CHATTERFANG, AUTOMATON], [AUTOMATON, CHATTERFANG]])
    def test_a_fixed_addition_goes_first_and_is_counted(self, pool, order):
        game = board(pool, order)
        create_token(game.state, TREASURE, 0, 1)
        assert tokens(game) == {TREASURE: 1, THOPTER: 1, SQUIRREL: 2}


class TestTheCardFileMustSayWhatItMeans:
    def test_it_compiles(self):
        with_cards(chatterfang())

    def test_without_and_create_it_is_refused(self):
        spec = chatterfang(and_create=[], token_multiplier=2)
        with pytest.raises(DslError, match="needs 'and_create'"):
            compile_card(CardModel.model_validate(spec))

    def test_on_another_effect_it_is_refused(self):
        spec = chatterfang(
            effect="replace_dies", destination="exile", affects={"types": ["Creature"]}
        )
        with pytest.raises(DslError, match="only means anything on replace_token_creation"):
            compile_card(CardModel.model_validate(spec))

    def test_a_non_boolean_is_refused(self):
        with pytest.raises(ValueError):
            CardModel.model_validate(chatterfang(and_create_per_token="that many"))
