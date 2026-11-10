"""A permission to **cast** an exiled card, which is narrower than one to play it.

    When this creature enters, exile another target creature or artifact until
    this creature leaves the battlefield. You may cast that card for as long as
    it remains exiled, and mana of any type can be spent to cast that spell.
    (Hostage Taker)

"Play" is the wider verb: a card is played as a land or cast as a spell, and a
land is never cast (305.9 -- a land that is also an artifact "can be played only
as a land. It can't be cast."). So "you may cast that card" reaches no land at
all. Without `playable_cast_only` the exiled card carries a play permission, and
Hostage Taker exiling Seat of the Synod would hand its controller a land drop
the printed card never grants; Gonti and Thief of Sanity would let a land among
an opponent's top cards be played instead of staying in exile.

The flag rides on the permission (`GameObject.playable_cast_only`), as
`playable_sorcery_only` does, and only the land-play walk in
`legality._land_plays` reads it -- the cast path already offers no land. It is
written by `exile`, `look_at_top` (to exile) and `grant_playable`, and wiped
with the rest of the permission when the card leaves exile (400.7) or the
permission ends.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import turn as turn_module
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

CAST_ONLY = "t_hostage_heist"  # exile + playable while_exiled + playable_cast_only
PLAY = "t_play_heist"  # the same permission spelled "play", the counterfactual
LOOK = "t_gonti_heist"  # look_at_top to exile, face down, cast only


def heist(builder, card: str, *, theirs=(), top: str = "forest"):
    """Seat 0 casts ``card`` in its main phase with its land drop unused.

    It also holds an instant it can afford, so it keeps a real choice after the
    heist resolves and the engine does not pass its turn away for it.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["plains", "plains"])
        .hand(0, [card, "t_plain_instant"])
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


def lines(game, oid: int, kind: ActionKind):
    return [a for a in game.legal_actions() if a.kind is kind and a.source == oid]


class TestALandStaysExiled:
    def test_an_artifact_land_is_no_land_drop(self, builder):
        """Hostage Taker's own case: Seat of the Synod is a legal target and stays put."""
        game = heist(builder, CAST_ONLY, theirs=["seat_of_the_synod"])
        oid = exiled(game, "seat_of_the_synod")
        assert (game.state.turn, game.state.active_player) == (1, 0)
        assert game.state.players[0].lands_played == 0
        assert not lines(game, oid, ActionKind.PLAY_LAND)
        assert not lines(game, oid, ActionKind.CAST)

    def test_the_play_permission_offers_the_same_land(self, builder):
        """The counterfactual: "play" reaches the land, so the flag is what refuses it."""
        game = heist(builder, PLAY, theirs=["seat_of_the_synod"])
        assert lines(game, exiled(game, "seat_of_the_synod"), ActionKind.PLAY_LAND)

    def test_a_basic_land_off_the_top_stays_exiled(self, builder):
        """Gonti and Thief of Sanity: a land among the cards looked at is not played."""
        game = heist(builder, LOOK, top="mountain")
        oid = exiled(game, "mountain")
        assert game.state.objects[oid].playable_by == 0
        assert not lines(game, oid, ActionKind.PLAY_LAND)


class TestASpellIsStillCast:
    def test_an_artifact_is_cast_from_exile(self, builder):
        game = heist(builder, CAST_ONLY, theirs=["ornithopter", "seat_of_the_synod"])
        oid = exiled(game, "ornithopter")
        cast = lines(game, oid, ActionKind.CAST)
        assert cast
        game.apply(cast[0])
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert game.state.objects[oid].controller == 0

    def test_a_card_off_the_top_is_cast(self, builder):
        game = heist(builder, LOOK, top="ornithopter")
        assert lines(game, exiled(game, "ornithopter"), ActionKind.CAST)

    def test_the_flag_is_on_the_permission(self, builder):
        game = heist(builder, CAST_ONLY, theirs=["ornithopter"])
        assert game.state.objects[exiled(game, "ornithopter")].playable_cast_only


class TestItEndsWithThePermission:
    def test_leaving_exile_wipes_it(self, builder):
        """400.7: a card that left exile is a new object with nothing granted."""
        game = heist(builder, CAST_ONLY, theirs=["seat_of_the_synod"])
        oid = exiled(game, "seat_of_the_synod")
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert not game.state.objects[oid].playable_cast_only

    def test_an_expiry_hook_wipes_it(self, builder):
        game = heist(builder, CAST_ONLY, theirs=["seat_of_the_synod"])
        oid = exiled(game, "seat_of_the_synod")
        game.state.objects[oid].playable_duration = "your_next_end_step"
        turn_module._expire_permissions(game.state, "your_next_end_step")
        assert game.state.objects[oid].playable_by is None
        assert not game.state.objects[oid].playable_cast_only


class TestTheLoader:
    def compile(self, effect):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe_cast_only",
                    "name": "Probe Cast Only",
                    "mana_cost": "{0}",
                    "types": ["Sorcery"],
                    "spell_effects": [effect],
                }
            )
        )

    EXILE = {"op": "exile", "objects": {"zone": "hand", "controller": "opponent", "count": "all"}}

    def test_on_each_granting_op_it_loads(self):
        self.compile({**self.EXILE, "playable": "while_exiled", "playable_cast_only": True})
        self.compile(
            {
                "op": "look_at_top",
                "player": "each_opponent",
                "amount": {"const": 1},
                "objects": {"count": "all"},
                "destination": "exile",
                "playable": "while_exiled",
                "playable_cast_only": True,
            }
        )
        self.compile(
            {
                "op": "grant_playable",
                "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
                "playable_cast_only": True,
            }
        )

    def test_without_a_permission_it_is_refused(self):
        with pytest.raises(DslError, match="playable_cast_only"):
            self.compile({**self.EXILE, "playable_cast_only": True})

    def test_on_an_op_that_grants_nothing_it_is_refused(self):
        with pytest.raises(DslError, match="playable_cast_only"):
            self.compile({"op": "draw", "playable_cast_only": True})

    def test_only_true(self):
        with pytest.raises(DslError, match="playable_cast_only"):
            self.compile({**self.EXILE, "playable": "while_exiled", "playable_cast_only": False})
