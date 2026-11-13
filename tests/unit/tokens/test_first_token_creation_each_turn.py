"""A token replacement that applies only to the first creation of your turn.

Esix, Fractal Bloom: "**The first time you would create one or more tokens
during each of your turns**, you may instead choose a creature other than Esix
and create that many tokens that are copies of that creature."

`replace_token_creation`'s `copy_instead` with `first_during_your_turn`. The
window is a fact about the *event*, not about the static (614: the replacement
modifies an event as it happens), so:

* **The first event spends it, taken or not.** Declining the copy on the
  turn's first creation does not leave the option for the second; neither does
  a creation that happened before Esix arrived, nor one with no creature to
  choose. Counted by `TurnLedger.token_creations`, which is written by every
  `create_token` call whether or not anything is listening.
* **Your turns only.** On an opponent's turn nothing is asked.
* **Each of your turns.** The ledger is cleared at cleanup, so the next turn
  has a first time again.

Without the key the copy replacement applies to every creation, which is a
much stronger card than the printed one.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.linking import validate_token_references
from commanderblitz.cards.registry import CardRegistry, authored_card_paths
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import PendingDecision
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.zones import move_object

ESIX = "esix_window_probe"
BEARS = "grizzly_bears"
TREASURE = "treasure_token"

LINE = (
    "The first time you would create one or more tokens during each of your "
    "turns, you may instead choose a creature other than this creature and "
    "create that many tokens that are copies of that creature."
)


def esix(**extra) -> dict:
    static = {
        "kind": "static",
        "text": LINE,
        "effect": "replace_token_creation",
        "copy_instead": {"types": ["Creature"], "exclude_self": True},
        "first_during_your_turn": True,
        **extra,
    }
    return {
        "id": ESIX,
        "name": "Esix Window Probe",
        "oracle_text": LINE,
        "mana_cost": "{4}{G}{U}",
        "types": ["Creature"],
        "subtypes": ["Fractal"],
        "power": 4,
        "toughness": 4,
        "abilities": [static],
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
    return with_cards(esix())


def board(pool: CardRegistry, mine=(ESIX, BEARS), hand=()):
    """Player 0's turn with ``mine`` and ``hand``; returns ``(game, bears_oid)``."""
    game = (
        GameBuilder(pool, players=2, seed=0)
        .battlefield(0, list(mine))
        .hand(0, list(hand))
        .build(advance=False)
    )
    assert game.state.active_player == 0
    bears = next((o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEARS), None)
    return game, bears


def arrive(game, card_id: str) -> int:
    """Put player 0's ``card_id`` from hand onto the battlefield mid-turn."""
    oid = next(o for o in game.state.players[0].hand if game.state.objects[o].def_id == card_id)
    move_object(game.state, oid, Zone.BATTLEFIELD)
    return oid


def run(game, effects: list[dict], choose=None, controller: int = 0) -> list[PendingDecision]:
    """Resolve ``effects`` as ``controller``'s; ``choose`` is the oid to copy, or None."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    gen = execute(ctx, effects)
    asked: list[PendingDecision] = []
    answer = None
    while True:
        try:
            decision = gen.send(answer) if asked else next(gen)
        except StopIteration:
            return asked
        asked.append(decision)
        values = [opt.value for opt in decision.options]
        answer = [] if choose is None else [values.index(choose)]


def make(amount: int = 1, **extra) -> list[dict]:
    return [{"op": "create_token", "token": TREASURE, "amount": {"const": amount}, **extra}]


def tokens(game, pid: int = 0) -> Counter:
    return Counter(obj.def_id for obj in game.state.battlefield_objects(pid) if obj.is_token)


class TestTheFirstTime:
    def test_the_first_creation_is_asked_and_the_second_is_not(self, pool):
        game, bears = board(pool)
        assert len(run(game, make(2), choose=bears)) == 1
        assert run(game, make(1), choose=bears) == []
        assert tokens(game) == {BEARS: 2, TREASURE: 1}

    def test_declining_the_first_spends_it(self, pool):
        game, bears = board(pool)
        run(game, make(1), choose=None)
        assert run(game, make(1), choose=bears) == []
        assert tokens(game) == {TREASURE: 2}

    def test_a_creation_before_esix_arrived_spends_it(self, pool):
        game, bears = board(pool, mine=(BEARS,), hand=(ESIX,))
        run(game, make(1))
        arrive(game, ESIX)
        assert run(game, make(1), choose=bears) == []
        assert tokens(game) == {TREASURE: 2}

    def test_a_creation_with_nobody_to_copy_spends_it(self, pool):
        game, _ = board(pool, mine=(ESIX,), hand=(BEARS,))
        assert run(game, make(1)) == []
        bears = arrive(game, BEARS)
        assert run(game, make(1), choose=bears) == []
        assert tokens(game) == {TREASURE: 2}

    def test_a_creation_of_no_tokens_is_not_the_first_time(self, pool):
        game, bears = board(pool)
        run(game, make(0), choose=bears)
        assert len(run(game, make(1), choose=bears)) == 1
        assert tokens(game) == {BEARS: 1}


class TestYourTurnsOnly:
    def test_on_an_opponents_turn_nothing_is_asked(self, pool):
        game, bears = board(pool)
        game.state.active_idx = 1
        assert run(game, make(1), choose=bears) == []
        assert tokens(game) == {TREASURE: 1}

    def test_an_opponents_creation_on_your_turn_does_not_spend_yours(self, pool):
        game, bears = board(pool)
        run(game, make(1, controller="opponent"))
        assert len(run(game, make(1), choose=bears)) == 1
        assert tokens(game) == {BEARS: 1}


class TestEachOfYourTurns:
    def test_the_next_turn_has_a_first_time_again(self, pool):
        game, bears = board(pool)
        run(game, make(1), choose=None)
        game.state.turn_ledger.clear()  # cleanup's sweep, `turn._cleanup_step`
        assert len(run(game, make(1), choose=bears)) == 1
        assert tokens(game) == {TREASURE: 1, BEARS: 1}


class TestTheCardFileMustSayWhatItMeans:
    def test_it_compiles(self):
        with_cards(esix())

    def test_on_another_mode_it_is_refused(self):
        spec = esix(copy_instead=None, token_multiplier=2)
        with pytest.raises(DslError, match="first_during_your_turn"):
            compile_card(CardModel.model_validate(spec))
