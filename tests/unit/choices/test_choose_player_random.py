"""Choosing a player at random: `choose_player` with `random: true`.

    Wildfire Devils — "When this creature enters and at the beginning of your
    upkeep, choose a player at random. That player exiles an instant or
    sorcery card from their graveyard. …"

"At random" means nobody chooses: the game draws the seat, uniformly among the
eligible players, off the seeded `state.rng` so a replay draws the same one.
Without the option the controller would be asked and would always pick the
seat that suits them, which is a different (and stronger) card in a pod. It is
a choice on resolution, not a target (115.1), so it asks no question, is not
re-checked and is not stopped by hexproof; "target opponent chosen at random"
is the random target spec instead (`stack._random_trigger_targets`).
"""

from __future__ import annotations

from collections import Counter

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.rng import Rng


def position(builder, players: int = 4):
    game = (
        builder(players=players)
        .library(0, ["island"] * 5)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game


def run(game, spec: dict) -> dict:
    """Run one ``choose_player``; fail if it asks anybody anything."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, [{"op": "choose_player", "as": "picked", **spec}])
    with pytest.raises(StopIteration):
        next(gen)
    return ctx.bindings


class TestNobodyIsAsked:
    def test_it_binds_a_seat_from_the_pool_without_a_decision(self, builder):
        game = position(builder)
        bindings = run(game, {"random": True})
        assert bindings["picked"] in (1, 2, 3)

    def test_the_pool_can_include_the_controller(self, builder):
        game = position(builder)
        seen = set()
        for seed in range(60):
            game.state.rng = Rng(seed)
            seen.add(run(game, {"random": True, "players": "each_player"})["picked"])
        assert seen == {0, 1, 2, 3}

    def test_the_asked_form_still_asks(self, builder):
        game = position(builder)
        ctx = EffectContext(state=game.state, controller=0)
        decision = next(execute(ctx, [{"op": "choose_player", "as": "picked"}]))
        assert decision.player == 0
        assert len(decision.options) == 3


class TestTheDraw:
    def test_it_is_uniform_over_the_opponents(self, builder):
        game = position(builder)
        counts = Counter()
        for seed in range(600):
            game.state.rng = Rng(seed)
            counts[run(game, {"random": True})["picked"]] += 1
        assert set(counts) == {1, 2, 3}
        assert all(150 <= n <= 250 for n in counts.values()), counts

    def test_the_same_seed_draws_the_same_seat(self, builder):
        game = position(builder)
        game.state.rng = Rng(7)
        first = run(game, {"random": True})["picked"]
        game.state.rng = Rng(7)
        assert run(game, {"random": True})["picked"] == first

    def test_a_player_who_left_is_never_drawn(self, builder):
        game = position(builder)
        game.state.players[2].has_lost = True
        for seed in range(40):
            game.state.rng = Rng(seed)
            assert run(game, {"random": True})["picked"] in (1, 3)

    def test_a_lone_eligible_seat_is_bound(self, builder):
        game = position(builder, players=2)
        assert run(game, {"random": True})["picked"] == 1

    def test_an_empty_pool_binds_nothing(self, builder):
        game = position(builder, players=2)
        game.state.players[1].has_lost = True
        assert "picked" not in run(game, {"random": True})


def probe(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe_random_player",
            "name": "Probe",
            "types": ["Sorcery"],
            "mana_cost": "{R}",
            "oracle_text": "Choose a player at random.",
            "spell_effects": [effect],
        }
    )


class TestLoadTime:
    def test_the_random_form_loads(self):
        compile_card(probe({"op": "choose_player", "as": "p", "random": True}))

    def test_random_is_a_boolean(self):
        with pytest.raises(DslError, match="boolean"):
            compile_card(probe({"op": "choose_player", "as": "p", "random": "yes"}))

    def test_a_prompt_beside_random_is_refused(self):
        with pytest.raises(DslError, match="prompt"):
            compile_card(
                probe({"op": "choose_player", "as": "p", "random": True, "prompt": "Pick"})
            )
