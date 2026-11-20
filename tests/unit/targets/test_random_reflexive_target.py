"""A reflexive ability's target chosen at random -- still a target, chosen by nobody.

    Explosion of Riches -- "Draw a card, then each other player may draw a
    card. Whenever a card is drawn this way, Explosion of Riches deals 5 damage
    to target opponent chosen at random from among your opponents."

"Whenever a card is drawn this way" is a reflexive triggered ability (603.12):
it names an instruction of the spell, not an event the board can be watched
for, so the spell fires it (`reflexive_trigger`) once per card drawn. Each one
goes on the stack after the spell has resolved, through the same
`stack.push_triggered_ability` every trigger takes, and 603.3d declares its
target there -- which is where `stack._random_trigger_targets` draws it off the
seeded `state.rng` (115.1: still a target, so it is announced and re-checked).

Without this the loader refused `random` on a reflexive ability, so the only
spelling left was `choose_player` with `random: true` on resolution: a choice,
not a target, which nothing could respond to and no hexproof would stop. And
written as a plain player target the caster would pick the opponent -- a
strictly better card than the printed one.

"This way" counts cards actually drawn: `draw`'s ``as`` names the seats that
drew, so a declined draw and an empty library (121.4) fire nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.sandbox import GameBuilder
from tests.conftest import event_types

EXPLOSION = "explosion_of_riches_probe"
TEXT = (
    "Draw a card, then each other player may draw a card. Whenever a card is "
    "drawn this way, Explosion of Riches deals 5 damage to target opponent "
    "chosen at random from among your opponents."
)
REFLEX = (
    "Whenever a card is drawn this way, Explosion of Riches deals 5 damage to "
    "target opponent chosen at random from among your opponents."
)


def explosion(target: dict | None = None, kind: str = "reflexive") -> dict:
    ability = {
        "kind": kind,
        "id": "boom",
        "text": REFLEX,
        "targets": [
            target
            or {
                "id": "t1",
                "kind": "player",
                "count": 1,
                "selector": {"controller": "opponent", "random": True},
            }
        ],
        "effects": [{"op": "damage", "amount": {"const": 5}, "target": "t1"}],
    }
    return {
        "id": EXPLOSION,
        "name": "Explosion of Riches",
        "oracle_text": TEXT,
        "mana_cost": "{5}{R}",
        "types": ["Sorcery"],
        "abilities": [ability],
        "spell_effects": [
            {"op": "draw", "amount": {"const": 1}, "player": "you", "as": "drew"},
            {
                "op": "for_each_player",
                "players": "each_opponent",
                "effects": [
                    {
                        "op": "may",
                        "player": {"binding": "each_player"},
                        "effects": [
                            {
                                "op": "draw",
                                "amount": {"const": 1},
                                "player": {"binding": "each_player"},
                                "as": "drew",
                            }
                        ],
                    }
                ],
            },
            {
                "op": "for_each_player",
                "players": {"binding": "drew"},
                "effects": [{"op": "reflexive_trigger", "ability": "boom"}],
            },
        ],
    }


@pytest.fixture(scope="module")
def pool() -> CardRegistry:
    cards = {
        card.id: card
        for card in CardRegistry.from_paths([Path("data/cards/basics.cards.json")])
    }
    compiled = compile_card(CardModel.model_validate(explosion()))
    cards[compiled.id] = compiled
    return CardRegistry(cards)


def board(pool, *, players: int = 3, seed: int = 0, empty: tuple[int, ...] = ()):
    builder = (
        GameBuilder(pool, players=players, seed=seed)
        .hand(0, [EXPLOSION])
        .battlefield(0, ["mountain"] * 6)
    )
    for pid in empty:
        builder = builder.library(pid, [])
    return builder.build()


def cast(game, accept: tuple[int, ...]):
    """Cast it, answer each opponent's "may draw", and resolve everything.

    Returns the decisions the table was asked after the yes/no answers --
    which, for a target drawn at random, must not include a target choice.
    """
    state = game.state
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and state.card(a.source).id == EXPLOSION
        )
    )
    asked: list[DecisionKind] = []
    for _ in range(200):
        decision = game.pending()
        if decision is None or game.over:
            break
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if decision.player in accept else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
        elif decision.kind is DecisionKind.PRIORITY:
            if not state.stack and not state.pending_triggers:
                break
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        else:
            asked.append(decision.kind)
            game.apply(game.legal_actions()[0])
    return asked


def damage(game, before: dict[int, int]) -> dict[int, int]:
    return {p.pid: before[p.pid] - p.life for p in game.state.players}


def lives(game) -> dict[int, int]:
    return {p.pid: p.life for p in game.state.players}


class TestOneTriggerPerCardDrawn:
    def test_everyone_draws_three_hits(self, pool):
        game = board(pool)
        before = lives(game)
        mark = len(game.state.events)
        cast(game, accept=(1, 2))
        dealt = damage(game, before)
        assert dealt[0] == 0, "the caster is never an opponent"
        assert dealt[1] + dealt[2] == 15
        assert event_types(game.state.events[mark:]).count("ability_resolved") == 3

    def test_a_declined_draw_fires_nothing(self, pool):
        game = board(pool)
        before = lives(game)
        cast(game, accept=(1,))
        dealt = damage(game, before)
        assert dealt[1] + dealt[2] == 10

    def test_your_own_draw_always_fires(self, pool):
        game = board(pool)
        before = lives(game)
        cast(game, accept=())
        dealt = damage(game, before)
        assert dealt[1] + dealt[2] == 5

    def test_an_empty_library_draws_no_card(self, pool):
        """121.4: an attempt to draw from an empty library draws nothing, so
        nothing was drawn "this way"."""
        game = board(pool, empty=(2,))
        before = lives(game)
        cast(game, accept=(1, 2))
        dealt = damage(game, before)
        assert dealt[1] + dealt[2] == 10


class TestTheTargetIsDrawnAtRandom:
    def test_nobody_is_asked_for_the_target(self, pool):
        game = board(pool)
        asked = cast(game, accept=(1, 2))
        assert DecisionKind.CHOOSE_OBJECTS not in asked

    def test_it_is_announced_as_a_target(self, pool):
        game = board(pool)
        mark = len(game.state.events)
        cast(game, accept=())
        events = event_types(game.state.events[mark:])
        assert events.index("became_target") > events.index("spell_resolved")

    def test_different_seeds_hit_different_opponents(self, pool):
        hit = set()
        for seed in range(12):
            game = board(pool, seed=seed)
            before = lives(game)
            cast(game, accept=())
            dealt = damage(game, before)
            hit.add(next(pid for pid, n in dealt.items() if n))
        assert hit == {1, 2}, "the same opponent every time is a choice, not a draw"

    def test_the_same_seed_hits_the_same_opponents(self, pool):
        def run():
            game = board(pool, seed=5)
            before = lives(game)
            cast(game, accept=(1, 2))
            return damage(game, before)

        assert run() == run()


class TestTheLoader:
    def test_a_reflexive_random_target_loads(self):
        compile_card(CardModel.model_validate(explosion()))

    def test_an_activated_random_target_is_still_refused(self):
        card = explosion(kind="activated")
        ability = card["abilities"][0]
        del ability["id"]
        ability["cost"] = {"tap": True}
        card["spell_effects"] = [{"op": "draw", "amount": {"const": 1}}]
        with pytest.raises(DslError, match="random"):
            compile_card(CardModel.model_validate(card))

    def test_optional_is_refused_on_a_reflexive_ability(self):
        target = {
            "id": "t1",
            "kind": "player",
            "optional": True,
            "selector": {"controller": "opponent", "random": True},
        }
        with pytest.raises(DslError, match="random"):
            compile_card(CardModel.model_validate(explosion(target=target)))
