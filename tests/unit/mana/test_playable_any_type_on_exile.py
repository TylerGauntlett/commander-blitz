"""Klaw, Master of Sound: "Mana of any type can be spent to cast a spell this way."

    Whenever Klaw deals combat damage to a player, look at the top card of that
    player's library, then exile it face down. You may play it for as long as it
    remains exiled. Mana of any type can be spent to cast a spell this way.

The card Klaw takes is an *opponent's*, so without the waiver it is mostly
uncastable: the printed ability is the theft plus the means to use it.

609.4b. "Mana of any **type**" names the colourless type too, so it is broader
than Elder Brain's "as though it were mana of any **color**": coloured mana pays
``{C}`` here and not there. Both ride the same permission, and the waiver is
`grant_playable`'s `any_type` (Esper Valigarmanda) written by `look_at_top` and
`exile` -- `obj.playable_any_type`, read by the cast path only while the
permission is live, and wiped with it when the card leaves exile (400.7).

A land is played, never cast (305.1), so the waiver has nothing to reach there:
the exiled land is played with the land drop exactly as without it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import pass_until

HEIST = "t_sound_heist"  # look_at_top + playable + any_type
PLAIN = "t_plain_heist"  # the same without the waiver
TINTED = "t_tinted_heist"  # the narrower any_color waiver
EXILE_HEIST = "t_klaw_heist"  # exile + playable + any_type
ONYX = "t_onyx_draw"  # {B}{B}
VOID = "t_void_draw"  # {C}


def heist(builder, *, card=HEIST, lands=("plains", "plains"), top=ONYX, theirs=()):
    """Seat 0 casts ``card`` off whatever ``lands`` it has; seat 1's top card is ``top``."""
    game = (
        builder(players=2)
        .battlefield(0, list(lands))
        .hand(0, [card])
        .hand(1, list(theirs))
        .library(0, ["forest"] * 10)
        .library(1, [top] + ["forest"] * 10)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card
        )
    )
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return game


def exiled(game, card_id: str) -> int:
    return next(
        oid for oid in game.state.players[1].exile if game.state.objects[oid].def_id == card_id
    )


def cast_lines(game, oid: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


class TestTheWrongColour:
    def test_plains_pay_black_black(self, builder):
        game = heist(builder)
        assert cast_lines(game, exiled(game, ONYX))

    def test_without_the_waiver_they_do_not(self, builder):
        game = heist(builder, card=PLAIN)
        oid = exiled(game, ONYX)
        assert game.state.objects[oid].playable_by == 0, "the permission itself is there"
        assert cast_lines(game, oid) == []

    def test_it_is_actually_paid_and_resolves(self, builder):
        game = heist(builder, lands=("plains", "plains", "plains"))
        oid = exiled(game, ONYX)
        game.apply(cast_lines(game, oid)[0])
        assert sum(1 for o in game.state.battlefield_objects(0) if o.tapped) == 2
        pass_until(game, lambda g: not g.state.stack)
        assert oid in game.state.players[1].graveyard


class TestColourlessMana:
    def test_a_sol_ring_pays_black_black(self, builder):
        game = heist(builder, lands=("sol_ring",))
        assert cast_lines(game, exiled(game, ONYX))

    def test_plains_pay_the_colourless_symbol(self, builder):
        """The difference from `any_color`: "any type" names colourless too."""
        game = heist(builder, top=VOID)
        assert cast_lines(game, exiled(game, VOID))

    def test_the_colour_waiver_does_not(self, builder):
        game = heist(builder, card=TINTED, top=VOID)
        assert cast_lines(game, exiled(game, VOID)) == []


class TestOnExile:
    def test_the_exile_op_carries_it_too(self, builder):
        game = heist(builder, card=EXILE_HEIST, theirs=(VOID,))
        assert cast_lines(game, exiled(game, VOID))


class TestTheBoundary:
    def test_it_leaves_with_the_permission(self, builder):
        from commanderblitz.engine.zones import move_object

        game = heist(builder)
        oid = exiled(game, ONYX)
        assert game.state.objects[oid].playable_any_type is True
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].playable_any_type is False

    def test_a_land_is_played_as_ever(self, builder):
        game = heist(builder, top="forest")
        oid = exiled(game, "forest")
        lands = [
            a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.source == oid
        ]
        assert len(lands) == 1
        assert cast_lines(game, oid) == []
        game.apply(lands[0])
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert game.state.objects[oid].controller == 0
        assert game.state.players[0].lands_played == 1


class TestTheLoader:
    def compile(self, effect):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe_any_type",
                    "name": "Probe Any Type",
                    "mana_cost": "{0}",
                    "types": ["Sorcery"],
                    "spell_effects": [effect],
                }
            )
        )

    LOOK = {
        "op": "look_at_top",
        "player": "each_opponent",
        "amount": {"const": 1},
        "objects": {"count": "all"},
        "destination": "exile",
        "face_down": True,
    }

    def test_on_a_permission_it_loads(self):
        self.compile({**self.LOOK, "playable": "while_exiled", "any_type": True})

    def test_without_a_permission_it_is_refused(self):
        with pytest.raises(DslError, match="any_type"):
            self.compile({**self.LOOK, "any_type": True})

    def test_on_a_bare_exile_it_is_refused(self):
        with pytest.raises(DslError, match="any_type"):
            self.compile(
                {
                    "op": "exile",
                    "objects": {"zone": "hand", "controller": "opponent", "count": "all"},
                    "any_type": True,
                }
            )

    def test_beside_any_color_it_is_refused(self):
        with pytest.raises(DslError, match="any_color"):
            self.compile(
                {**self.LOOK, "playable": "while_exiled", "any_type": True, "any_color": True}
            )

    def test_beside_playable_free_it_is_refused(self):
        with pytest.raises(DslError, match="playable_free"):
            self.compile(
                {**self.LOOK, "playable": "while_exiled", "any_type": True, "playable_free": True}
            )

    def test_only_true(self):
        with pytest.raises(DslError, match="any_type"):
            self.compile({**self.LOOK, "playable": "while_exiled", "any_type": "yes"})
