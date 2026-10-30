"""A lasting permission to play exiled cards without paying their mana costs.

    Look at the top card of each player's library, then exile those cards face
    down. You may play them without paying their mana costs for as long as they
    remain exiled.  (Extract Power)

Two facts the engine already had, and one it had wrong:

- **Whose permission it is.** "*You* may play them" names the effect's
  controller, for the cards taken off an opponent's library too. `look_at_top`
  wrote `playable_by` as the library's owner, so the opponent could play their
  own card and the caster could not -- the printed card inverted.
- **What it costs.** "Without paying their mana costs" is 601.2b, which plot
  already spelled as `playable_free`: the line is priced free, X is 0 (107.3b),
  and an additional cost is still owed (601.2f). Casting it this way grants no
  timing either -- a creature still waits for a main phase and an empty stack.
- **A land is played, not cast.** It needs no price, and it spends the land drop
  like any other land play (305.2), at sorcery speed (305.1).

The permission is `while_exiled`, so it outlives the turn and ends when the card
leaves exile (400.7). Face down, the card is shown to the player who may play it
and to nobody else.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _priority_actions
from commanderblitz.engine.serialize import player_view
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until, settle

EXTRACT = {
    "op": "look_at_top",
    "player": "each_player",
    "amount": {"const": 1},
    "objects": {"count": "all"},
    "destination": "exile",
    "face_down": True,
    "playable": "while_exiled",
    "playable_free": True,
}


def position(
    builder, top: str, *, active: int = 0, lands_played: int = 0, battlefield=()
):
    """Seat 0 resolves Extract Power with no mana at all; seat 1's top card is ``top``.

    No lands for seat 0, so any cast it is offered can only be the free one.
    Frozen rather than advanced: the auto-pass would roll a position with no
    real decision in it several turns forward.
    """
    game = (
        builder(players=2)
        .battlefield(0, list(battlefield))
        .battlefield(1, ["swamp"] * 6)
        .library(0, ["forest"] * 20)
        .library(1, [top] + ["swamp"] * 20)
        .lands_played(0, lands_played)
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    theirs = game.state.players[1].library[0]
    ctx = EffectContext(state=game.state, controller=0, source_oid=None, targets={}, bindings={})
    list(execute(ctx, [dict(EXTRACT)]))
    assert game.state.objects[theirs].zone is Zone.EXILE
    return game, theirs


def offers(game, oid: int, seat: int = 0):
    """What ``seat`` would be offered for ``oid`` if it held priority now."""
    return [a for a in _priority_actions(game.state, seat) if a.source == oid]


def to_main(game, seat: int) -> None:
    after = game.state.turn
    pass_until(
        game,
        lambda g: g.state.step is Step.PRECOMBAT_MAIN
        and g.state.active_player == seat
        and g.state.turn > after
        and not g.state.stack,
    )


class TestYouPlayTheirCard:
    def test_the_permission_is_the_controllers(self, builder):
        game, oid = position(builder, "grizzly_bears")
        obj = game.state.objects[oid]
        assert obj.owner == 1
        assert obj.playable_by == 0
        assert obj.playable_free

    def test_you_may_cast_it_without_mana(self, builder):
        game, oid = position(builder, "grizzly_bears")
        casts = [a for a in offers(game, oid) if a.kind is ActionKind.CAST]
        assert casts and all(a.cast_free for a in casts)
        game._advance()
        game.apply(casts[0])
        pass_until(game, lambda g: not g.state.stack)
        obj = game.state.objects[oid]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.controller == 0

    def test_its_owner_may_not(self, builder):
        """Not even in the owner's own main phase, with the stack empty."""
        game, oid = position(builder, "grizzly_bears", active=1)
        assert not offers(game, oid, seat=1)


class TestTimingIsTheCards:
    def test_no_flash_is_granted(self, builder):
        """A creature cast this way still waits for your main phase and an empty stack."""
        game, oid = position(builder, "grizzly_bears", active=1)
        assert not offers(game, oid)

    def test_an_instant_is_cast_at_instant_speed(self, builder):
        game, oid = position(builder, "t_plain_instant", active=1)
        casts = [a for a in offers(game, oid) if a.kind is ActionKind.CAST]
        assert casts and all(a.cast_free for a in casts)

    def test_x_is_zero(self, builder):
        game, oid = position(builder, "t_fireball", battlefield=["grizzly_bears"])
        casts = [a for a in offers(game, oid) if a.kind is ActionKind.CAST]
        assert casts and all(a.cast_free and not a.x for a in casts)


class TestAdditionalCostsAreStillOwed:
    def test_without_a_creature_to_sacrifice_there_is_no_cast(self, builder):
        game, oid = position(builder, "village_rites")
        assert not offers(game, oid)

    def test_with_one_it_is_offered_free(self, builder):
        game, oid = position(builder, "village_rites", battlefield=["grizzly_bears"])
        casts = [a for a in offers(game, oid) if a.kind is ActionKind.CAST]
        assert casts and all(a.cast_free for a in casts)

    def test_casting_it_sacrifices_the_creature(self, builder):
        """Free of mana, not of the sacrifice: a line that skipped it is a free draw-two."""
        game, oid = position(builder, "village_rites", battlefield=["grizzly_bears"])
        bear = next(o.oid for o in game.state.battlefield_objects(0))
        game._advance()
        game.apply(next(a for a in game.legal_actions() if a.source == oid))
        settle(game)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestALandUsesYourLandDrop:
    def test_their_land_is_yours_to_play(self, builder):
        game, oid = position(builder, "swamp")
        drop = next(a for a in offers(game, oid) if a.kind is ActionKind.PLAY_LAND)
        game._advance()
        game.apply(drop)
        obj = game.state.objects[oid]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.controller == 0
        assert game.state.players[0].lands_played == 1

    def test_not_after_your_land_drop(self, builder):
        game, oid = position(builder, "swamp", lands_played=1)
        assert not offers(game, oid)

    def test_one_drop_between_the_two_exiled_lands(self, builder):
        game, theirs = position(builder, "swamp")
        mine = next(o for o in game.state.players[0].exile)
        game._advance()
        game.apply(next(a for a in offers(game, mine) if a.kind is ActionKind.PLAY_LAND))
        assert not offers(game, theirs)


class TestItLastsWhileExiled:
    def test_it_is_still_playable_on_your_next_turn(self, builder):
        game, oid = position(builder, "grizzly_bears")
        game._advance()
        to_main(game, 0)
        casts = [a for a in offers(game, oid) if a.kind is ActionKind.CAST]
        assert casts and all(a.cast_free for a in casts)

    def test_not_once_it_leaves_exile(self, builder):
        game, oid = position(builder, "grizzly_bears")
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert not offers(game, oid)
        move_object(game.state, oid, Zone.EXILE)
        assert not offers(game, oid)
        assert not game.state.objects[oid].playable_free


class TestFaceDown:
    def test_you_may_look_at_them(self, builder):
        game, oid = position(builder, "grizzly_bears")
        mine = player_view(game.state, 0)
        assert oid in {c["oid"] for c in mine["players"][1]["exile"]}

    def test_their_owner_may_not(self, builder):
        game, oid = position(builder, "grizzly_bears")
        theirs = player_view(game.state, 1)
        assert oid not in {c["oid"] for c in theirs["players"][1]["exile"]}
        assert theirs["players"][1]["exile_hidden_count"] == 1


class TestTheLoader:
    def compile(self, effect):
        return compile_card(
            CardModel.model_validate(
                {
                    "id": "t_probe_extract",
                    "name": "Probe Extract",
                    "mana_cost": "{U}",
                    "types": ["Sorcery"],
                    "spell_effects": [effect],
                }
            )
        )

    def test_extract_power_loads(self):
        self.compile(dict(EXTRACT))

    def test_exile_and_grant_playable_accept_it(self):
        self.compile({"op": "exile", "objects": {"zone": "graveyard", "count": 1},
                      "playable": "while_exiled", "playable_free": True})
        self.compile({"op": "grant_playable",
                      "objects": {"zone": "exile", "controller": "any", "count": "all"},
                      "playable": "while_exiled", "playable_free": True})

    def test_it_needs_a_permission(self):
        bare = {k: v for k, v in EXTRACT.items() if k != "playable"}
        with pytest.raises(DslError, match="playable_free"):
            self.compile(bare)

    def test_any_color_beside_it_is_refused(self):
        with pytest.raises(DslError, match="playable_free"):
            self.compile(dict(EXTRACT, any_color=True))
