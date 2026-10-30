"""Flipping a coin -- rule 705.

    "At the beginning of your upkeep, if there are four or more creature cards
    exiled with this artifact, flip a coin. If you lose the flip, sacrifice this
    artifact and return a card exiled with it at random to its owner's hand."
                                                     -- Negative Zone Portal

`flip_coin` flips one coin for the controller and runs ``effects`` on a win and
``else`` on a loss. A d2 from `roll_dice` is the near miss and the wrong one: a
coin is not a die, so it would answer "whenever you roll one or more dice" and
nothing that asks about a coin. The outcome comes from ``state.rng``, the
engine's single seeded source, so a replay flips the same way; one
``coin_flipped`` event carries ``won`` for the log, because a lost flip's
sacrifice otherwise appears with no reason beside it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.rng import Rng

WIN = [{"op": "gain_life", "player": "you", "amount": {"const": 3}}]
LOSE = [{"op": "lose_life", "player": "you", "amount": {"const": 2}}]


def seed_that(won: bool) -> int:
    """A seed whose first flip comes down the way asked."""
    return next(s for s in range(100) if (Rng(s).randint(0, 1) == 1) is won)


def flip(builder, *, seed: int, spec: dict | None = None):
    game = builder(players=2, seed=seed).build(advance=False)
    game.state.rng = Rng(seed)
    ctx = EffectContext(state=game.state, controller=0)
    mark = len(game.state.events)
    gen = OPS["flip_coin"](ctx, {"op": "flip_coin", **(spec or {"effects": WIN, "else": LOSE})})
    assert list(gen) == [], "a flip asks nobody anything"
    return game, game.state.events[mark:]


def flips(events) -> list:
    return [e for e in events if e.type == EventType.COIN_FLIPPED]


class TestTheBranches:
    def test_a_win_runs_effects(self, builder):
        game, events = flip(builder, seed=seed_that(True))
        assert game.state.players[0].life == 43
        assert [e.data["won"] for e in flips(events)] == [True]

    def test_a_loss_runs_else(self, builder):
        game, events = flip(builder, seed=seed_that(False))
        assert game.state.players[0].life == 38
        assert [e.data["won"] for e in flips(events)] == [False]

    def test_a_loss_with_no_else_does_nothing(self, builder):
        game, events = flip(builder, seed=seed_that(False), spec={"effects": WIN})
        assert game.state.players[0].life == 40
        assert len(flips(events)) == 1, "the coin was still flipped"


class TestDeterminism:
    def test_the_same_seed_flips_the_same_way(self, builder):
        seed = seed_that(True)
        first, _ = flip(builder, seed=seed)
        second, _ = flip(builder, seed=seed)
        assert first.state.players[0].life == second.state.players[0].life

    def test_it_is_no_dice_roll(self, builder):
        _, events = flip(builder, seed=0)
        assert not [e for e in events if e.type == EventType.DICE_ROLLED]


class TestTheLoader:
    def _compile(self, effect: dict):
        model = CardModel.model_validate(
            {
                "id": "t_fc_bad",
                "name": "Bad Coin",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "flip_coin", **effect}],
            }
        )
        return compile_card(model)

    def test_a_flip_with_no_branch_is_refused(self):
        with pytest.raises(DslError, match="flip_coin needs 'effects'"):
            self._compile({})

    def test_a_branch_must_be_a_list(self):
        with pytest.raises(DslError, match="a list of effects"):
            self._compile({"else": {"op": "draw"}})

    def test_the_printed_shape_loads(self):
        self._compile({"else": LOSE})
