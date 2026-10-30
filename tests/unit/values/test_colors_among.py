"""Colors among permanents and the turn's casts.

    "You draw X cards and gain X life, where X is the number of colors among
    permanents you control and spells you've cast this turn."  -- First Family

A count of *different colors* (105.1), so `count` cannot say it -- two green
creatures are one color -- and it reaches past the board: most of the spells
cast this turn have already left the stack. `{"distinct": {"of": "color", ...}}`
counts the derived colors of the `objects` pool, and an optional
``spells_cast_this_turn`` player spec unions in the printed colors of the faces
recorded in `TurnLedger.spells_cast_ids`. Colorless is not a color (105.2c), so
an artifact adds nothing, and a color seen on both sides counts once.

Without the ledger half, First Family would read only the board and be a weaker
card on exactly the turns it is built for.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType

BEAR = "t_ca_bear"  # green creature
AZORIUS = "t_ca_azorius"  # white-blue creature
ROCK = "t_ca_rock"  # colorless artifact
BOLT = "t_ca_bolt"  # red instant
GROWTH = "t_ca_growth"  # green sorcery

MINE = {"zone": "battlefield", "controller": "you"}


def colors_among(spells="you"):
    spec = {"of": "color", "objects": MINE}
    if spells is not None:
        spec["spells_cast_this_turn"] = spells
    return {"distinct": spec}


def value(game, expr, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), expr)


def board(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )


def cast(game, card_id: str, pid: int = 0) -> None:
    """Record a cast through the same fold a real one goes through."""
    game.state.emit(EventType.SPELL_CAST, player=pid, card=card_id)


class TestThePermanents:
    def test_colors_not_permanents(self, builder):
        game = board(builder, mine=[BEAR, BEAR, AZORIUS])
        assert value(game, colors_among(None)) == 3

    def test_colorless_counts_nothing(self, builder):
        game = board(builder, mine=[ROCK])
        assert value(game, colors_among(None)) == 0

    def test_an_opponents_permanents_are_not_yours(self, builder):
        game = board(builder, mine=[BEAR], theirs=[AZORIUS])
        assert value(game, colors_among(None)) == 1


class TestTheSpellsCastThisTurn:
    def test_a_resolved_spells_color_joins(self, builder):
        game = board(builder, mine=[BEAR])
        cast(game, BOLT)
        assert value(game, colors_among()) == 2

    def test_a_color_on_both_sides_counts_once(self, builder):
        game = board(builder, mine=[BEAR])
        cast(game, GROWTH)
        assert value(game, colors_among()) == 1

    def test_an_opponents_casts_are_not_yours(self, builder):
        game = board(builder, mine=[BEAR])
        cast(game, BOLT, pid=1)
        assert value(game, colors_among()) == 1

    def test_without_the_key_the_casts_are_not_read(self, builder):
        game = board(builder, mine=[BEAR])
        cast(game, BOLT)
        assert value(game, colors_among(None)) == 1

    def test_the_turn_boundary_clears_them(self, builder):
        game = board(builder, mine=[BEAR])
        cast(game, BOLT)
        game.state.turn_ledger.clear()
        assert value(game, colors_among()) == 1


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        validate_value(colors_among(), "test")

    def test_the_casts_join_colors_only(self):
        with pytest.raises(DslError, match="count of colors only"):
            validate_value(
                {"distinct": {"of": "power", "objects": MINE, "spells_cast_this_turn": "you"}},
                "test",
            )

    def test_an_empty_player_spec_is_refused(self):
        with pytest.raises(DslError, match="needs a player spec"):
            validate_value(colors_among(""), "test")
