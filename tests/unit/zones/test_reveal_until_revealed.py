"""`reveal_until` with ``revealed_as``: "the number of cards revealed this way".

    Audacious Reshapers -- "{T}, Sacrifice an artifact: Reveal cards from the
    top of your library until you reveal an artifact card. Put that card onto
    the battlefield and the rest on the bottom of your library in a random
    order. This creature deals damage to you equal to the number of cards
    revealed this way."

A reveal (701.20) is every card shown, not only the one the walk stopped at.
The `as` binding records the matches that moved, so a count of it is one or
zero, and Reshapers would deal 1 damage whatever it walked past -- a strictly
better card than the printed one, whose cost is the depth of the walk.
``revealed_as`` records every revealed card: the match plus the cards walked
past, and on a scan that runs the library out with no match, every card in it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from tests.conftest import battlefield_ids, library_ids

FOREST = "forest"
BEAR = "t_bear"
RING = "sol_ring"

ARTIFACT = {"types": ["Artifact"]}


def board(builder, library: list[str], opponent_library: list[str] | None = None):
    """A position with stacked libraries; the source is the first permanent."""
    b = builder(players=2, seed=0).battlefield(0, [FOREST]).library(0, library)
    if opponent_library is not None:
        b = b.library(1, opponent_library)
    game = b.build(advance=False)
    src = next(o.oid for o in game.state.battlefield_objects(0))
    return game, src


def run(game, effects: list[dict], source: int) -> EffectContext:
    """Run the effects in one resolution and fail if anything asks a decision."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    for spec in effects:
        for _ in execute_one(ctx, spec):  # pragma: no cover - the loop body is the failure
            raise AssertionError(f"{spec['op']} asked a decision; it takes none")
    return ctx


def reshape(**extra) -> dict:
    return {
        "op": "reveal_until",
        "objects": ARTIFACT,
        "destination": "battlefield",
        "revealed_as": "revealed",
        **extra,
    }


DAMAGE = {"op": "damage", "player": "you", "amount": {"count": {"binding": "revealed"}}}


class TestItCountsEveryCardRevealed:
    def test_the_match_and_the_cards_walked_past(self, builder):
        game, src = board(builder, [FOREST, BEAR, FOREST, RING, BEAR])
        life = game.state.players[0].life

        ctx = run(game, [reshape(), DAMAGE], src)

        assert len(ctx.bindings["revealed"]) == 4
        assert game.state.players[0].life == life - 4
        assert RING in battlefield_ids(game, 0)
        assert library_ids(game)[0] == BEAR, "the card after the match was never revealed"

    def test_the_first_card_matching_is_one(self, builder):
        game, src = board(builder, [RING, FOREST])
        life = game.state.players[0].life

        run(game, [reshape(), DAMAGE], src)

        assert game.state.players[0].life == life - 1

    def test_a_scan_that_finds_nothing_still_revealed_the_library(self, builder):
        game, src = board(builder, [FOREST, BEAR, FOREST])
        life = game.state.players[0].life

        run(game, [reshape(), DAMAGE], src)

        assert game.state.players[0].life == life - 3
        assert sorted(library_ids(game)) == sorted([FOREST, BEAR, FOREST])

    def test_zero_matches_wanted_reveals_and_counts_nothing(self, builder):
        game, src = board(builder, [FOREST, RING])

        ctx = run(game, [reshape(amount={"const": 0})], src)

        assert ctx.bindings["revealed"] == []


class TestItIsNotAs:
    def test_as_holds_only_the_match(self, builder):
        """The near miss: `as` is the number found, not the number revealed."""
        game, src = board(builder, [FOREST, BEAR, RING])

        ctx = run(game, [reshape(**{"as": "found"})], src)

        assert len(ctx.bindings["found"]) == 1
        assert len(ctx.bindings["revealed"]) == 3
        assert set(ctx.bindings["found"]) <= set(ctx.bindings["revealed"])


class TestAcrossSeats:
    def test_each_walk_extends_the_record(self, builder):
        game, src = board(builder, [FOREST, RING], opponent_library=[BEAR, BEAR, RING])

        ctx = run(game, [reshape(player="each_player")], src)

        assert len(ctx.bindings["revealed"]) == 5


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_reveal_until_revealed_probe",
                "name": "Reveal Until Revealed Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect, DAMAGE],
            }
        )

    def test_reshapers_shape_loads(self):
        compile_card(self._card(reshape()))

    def test_the_name_is_a_string(self):
        with pytest.raises(DslError, match="'revealed_as' must be a non-empty binding name"):
            compile_card(self._card(reshape(revealed_as=True)))

    def test_only_reveal_until_reads_it(self):
        with pytest.raises(DslError, match="only reveal_until reads it"):
            compile_card(
                self._card({"op": "mill", "amount": {"const": 2}, "revealed_as": "revealed"})
            )
