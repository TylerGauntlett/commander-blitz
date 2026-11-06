"""`cast_from_exile` — "if this spell was cast from exile".

    "Permanents you control gain indestructible until end of turn. If this
    spell was cast from exile, prevent all damage that would be dealt to you
    this turn."  — Ultimate Magic: Holy

The third sibling of `cast_from_hand` and `cast_from_graveyard`, and like them a
fact about the moment of casting: 601.2a moves the card to the stack first, so by
resolution every spell is "on the stack" and `zone_is` answers the same for all
of them. `stack.push_spell` records the zone the card left as `cast_from_zone`,
and this key reads it.

It is the printed words and nothing narrower or wider:

- **Not `foretold`** (Haunting Voyage's "if this spell was foretold"). A plotted
  card, an Adventure cast from exile and a card cast under any exile play
  permission were all cast from exile without being foretold.
- **Not `not cast_from_hand`.** A spell cast off a library top or from the
  command zone was cast from neither hand nor exile, and a copy was never cast
  at all (707.10): it is backed by a token whose `cast_from_zone` is never
  written.

Without it the Ultimate Magic cycle loses the half of each card that foretell
pays for. Witnesses: Ultimate Magic: Holy and Ultimate Magic: Meteor
(`data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.conditions import (
    evaluate,
    evaluate_condition,
    validate_condition,
)
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import pass_until, settle

PLAINS = "plains"
BLESSING = "t_exile_blessing"  # {1}{W}, foretell {W}: gain 1, +4 if cast from exile


def position(builder, lands: int = 4):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * lands)
        .hand(0, [BLESSING])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )


def to_my_main(game, turn: int) -> None:
    pass_until(
        game,
        lambda g: (
            g.state.turn >= turn
            and g.state.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN)
            and (d := g.pending()) is not None
            and d.player == 0
        ),
    )


def cast_blessing(game) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BLESSING
    )
    game.apply(action)
    settle(game)


def asks(game, oid: int, cond) -> bool:
    return evaluate_condition(game.state, cond, controller=0, source=oid)


class TestTheStamp:
    def test_a_card_cast_out_of_exile_answers_true(self, builder):
        game = position(builder)
        oid = game.state.players[0].hand[0]
        game.state.objects[oid].cast_from_zone = Zone.EXILE.value
        assert asks(game, oid, {"cast_from_exile": True}) is True
        assert asks(game, oid, {"cast_from_exile": False}) is False

    @pytest.mark.parametrize("zone", [Zone.HAND, Zone.GRAVEYARD, Zone.LIBRARY, Zone.COMMAND])
    def test_any_other_zone_answers_false(self, builder, zone):
        """A Citadel top or a commander is not "from exile" either -- which is
        why the key is not `not cast_from_hand`."""
        game = position(builder)
        oid = game.state.players[0].hand[0]
        game.state.objects[oid].cast_from_zone = zone.value
        assert asks(game, oid, {"cast_from_exile": True}) is False

    def test_a_spell_never_cast_answers_false(self, builder):
        """A copy is backed by a token whose stamp is never written (707.10)."""
        game = position(builder)
        oid = game.state.players[0].hand[0]
        assert game.state.objects[oid].cast_from_zone is None
        assert asks(game, oid, {"cast_from_exile": True}) is False

    def test_of_asks_a_binding_instead_of_the_source(self, builder):
        game = position(builder)
        oid = game.state.players[0].hand[0]
        land = next(iter(game.state.battlefield_objects(0))).oid
        game.state.objects[oid].cast_from_zone = Zone.EXILE.value
        ctx = EffectContext(state=game.state, controller=0, source_oid=land)
        ctx.bindings["it"] = oid
        assert evaluate(ctx, {"cast_from_exile": True, "of": "it"}) is True
        assert evaluate(ctx, {"cast_from_exile": True}) is False


class TestTheCast:
    def test_a_cast_from_hand_takes_only_the_first_half(self, builder):
        game = position(builder)
        to_my_main(game, 3)
        life = game.state.players[0].life
        cast_blessing(game)
        assert game.state.players[0].life == life + 1

    def test_a_foretold_cast_takes_both_halves(self, builder):
        """The stamp is written by `push_spell` as the card leaves exile, and
        read while the spell resolves -- the stack zone in between is the
        reason `zone_is` cannot answer it."""
        game = position(builder)
        to_my_main(game, 3)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.SUSPEND))
        to_my_main(game, 5)
        life = game.state.players[0].life
        cast_blessing(game)
        assert game.state.players[0].life == life + 5


class TestTheLoaderRefusesANonBoolean:
    def test_a_string_is_refused(self):
        """`"false"` is a non-empty string and would read as true."""
        with pytest.raises(DslError, match="cast_from_exile"):
            validate_condition({"cast_from_exile": "false"}, "card")

    def test_a_boolean_loads(self):
        validate_condition({"cast_from_exile": False}, "card")
