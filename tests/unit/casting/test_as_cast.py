"""`as_cast` — a value fixed "as you cast this spell".

    "Draw X cards, where X is the greatest power among creatures you
    controlled as you cast this spell. If this spell was cast from exile, you
    gain twice X life."  — Lifestream's Blessing

Rule 601.2 is the casting of a spell, and a number the card says is determined
"as you cast this spell" is fixed then, not at resolution (608.2h reads
everything else as the spell resolves). `stack.push_spell` evaluates each named
`as_cast` value once, as the spell goes on the stack, and binds it on the stack
item, where `spell_effects` read it with ``{"binding": name}``.

Without it the only spelling is `extreme_value` inside the `draw`, evaluated at
resolution: an opponent who kills the big creature in response turns a draw-three
into a draw-nothing, which is a weaker card than the printed one, and pumping
the creature in response a stronger one. Witness: Lifestream's Blessing
(`data/cards/auto/`).

A copy carries the binding (707.10 copies the values determined as the
original was cast), the same way it carries `x`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import settle

FOREST = "forest"
GIANT = "hill_giant"  # 3/3
ANGEL = "serra_angel"  # 4/4
INSIGHT = "t_as_cast_insight"  # draw X, gain 2X; X fixed as cast
NEAR_MISS = "t_resolution_insight"  # draw X; X read at resolution

GREATEST_POWER = {
    "extreme_value": {"of": "power", "objects": {"types": ["Creature"], "controller": "you"}}
}


def position(builder, spell: str = INSIGHT, mine=(GIANT,), theirs=()):
    """A second copy and a second Forest keep the caster's window open after the
    cast -- with nothing else to do, auto-pass would resolve the spell before
    the test could respond to it."""
    game = (
        builder(players=2)
        .battlefield(0, [FOREST, FOREST, *mine])
        .battlefield(1, list(theirs))
        .hand(0, [spell, spell])
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )
    return game, game.state.players[0].hand[0]


def cast(game, oid: int):
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid)
    )
    return game.state.stack[-1]


def my_creature(game, def_id: str) -> int:
    return next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == def_id)


class TestTheValueIsFixedAsCast:
    def test_it_is_bound_on_the_stack_item(self, builder):
        game, oid = position(builder)
        item = cast(game, oid)
        assert item.bindings["greatest_power"] == 3

    def test_a_creature_gone_in_response_still_counts(self, builder):
        game, oid = position(builder)
        hand = len(game.state.players[0].hand)
        life = game.state.players[0].life
        cast(game, oid)
        move_object(game.state, my_creature(game, GIANT), Zone.GRAVEYARD)
        settle(game)
        # The spell left the hand; three cards came back.
        assert len(game.state.players[0].hand) == hand - 1 + 3
        assert game.state.players[0].life == life + 6

    def test_the_near_miss_reads_the_board_at_resolution(self, builder):
        """`extreme_value` written into the `draw` itself sees the empty board."""
        game, oid = position(builder, NEAR_MISS)
        hand = len(game.state.players[0].hand)
        cast(game, oid)
        move_object(game.state, my_creature(game, GIANT), Zone.GRAVEYARD)
        settle(game)
        assert len(game.state.players[0].hand) == hand - 1

    def test_a_creature_arriving_in_response_does_not_count(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST, FOREST])
            .graveyard(0, [GIANT])
            .hand(0, [INSIGHT, INSIGHT])
            .library(0, [FOREST] * 20)
            .library(1, [FOREST] * 20)
            .build()
        )
        oid = game.state.players[0].hand[0]
        giant = game.state.players[0].graveyard[0]
        hand = len(game.state.players[0].hand)
        assert cast(game, oid).bindings["greatest_power"] == 0
        move_object(game.state, giant, Zone.BATTLEFIELD)
        settle(game)
        assert len(game.state.players[0].hand) == hand - 1


class TestWhatItReads:
    def test_only_creatures_the_caster_controlled(self, builder):
        game, oid = position(builder, theirs=(ANGEL,))
        assert cast(game, oid).bindings["greatest_power"] == 3

    def test_the_greatest_of_several(self, builder):
        game, oid = position(builder, mine=(GIANT, ANGEL))
        assert cast(game, oid).bindings["greatest_power"] == 4

    def test_no_creatures_is_zero(self, builder):
        game, oid = position(builder, mine=())
        life = game.state.players[0].life
        assert cast(game, oid).bindings["greatest_power"] == 0
        settle(game)
        assert game.state.players[0].life == life


class TestACopy:
    def test_a_copy_carries_the_cast_value(self, builder):
        """707.10: the copy was never cast, so it has no moment of its own to
        read; it copies the value the original fixed."""
        game, oid = position(builder)
        item = cast(game, oid)
        move_object(game.state, my_creature(game, GIANT), Zone.GRAVEYARD)
        copy = put_copy_on_stack(game.state, 0, item)
        assert copy.bindings["greatest_power"] == 3


def card(**overrides):
    base = {
        "id": "t_as_cast_probe",
        "name": "Probe",
        "mana_cost": "{G}",
        "types": ["Instant"],
        "as_cast": {"n": GREATEST_POWER},
        "spell_effects": [{"op": "draw", "player": "you", "amount": {"binding": "n"}}],
    }
    base.update(overrides)
    return CardModel.model_validate(base)


class TestTheLoader:
    def test_the_written_form_loads(self):
        assert compile_card(card()).as_cast == {"n": GREATEST_POWER}

    def test_a_name_nothing_reads_is_refused(self):
        with pytest.raises(DslError, match="nothing in spell_effects reads"):
            compile_card(card(as_cast={"m": GREATEST_POWER}))

    def test_a_card_without_spell_effects_is_refused(self):
        """A permanent's triggers never see its spell's stack item."""
        with pytest.raises(DslError, match="has none"):
            compile_card(card(types=["Creature"], power=1, toughness=1, spell_effects=[]))

    def test_a_target_is_refused(self):
        with pytest.raises(DslError, match="cannot read a target"):
            compile_card(card(as_cast={"n": {"power_of": {"target": "t1"}}}))

    @pytest.mark.parametrize("name", ["convoked", "distribution", "warped"])
    def test_an_engine_binding_name_is_refused(self, name):
        effects = [{"op": "draw", "player": "you", "amount": {"binding": name}}]
        with pytest.raises(DslError, match="not a usable binding name"):
            compile_card(card(as_cast={name: GREATEST_POWER}, spell_effects=effects))

    def test_a_constant_is_refused(self):
        with pytest.raises(DslError, match="a constant"):
            compile_card(card(as_cast={"n": 3}))

    def test_a_malformed_value_is_refused(self):
        with pytest.raises(DslError):
            compile_card(card(as_cast={"n": {"no_such_value": 1}}))
