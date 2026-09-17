"""A "you may play it" permission with no clock: "for as long as it remains exiled".

    You may play lands and cast spells from among the exiled cards for as long as
    they remain exiled.  (Elder Brain)

Every `playable` duration the engine had ends or starts on a turn: `this_turn`,
`your_next_end_step` and `end_of_your_next_turn` all expire, and `later_turns`
(Plot) forbids the turn it was granted on. Elder Brain's cards are playable at
once -- its trigger resolves in the declare attackers step and a land can go down
in the second main phase -- and for ever after, so every existing clock is a
strictly worse card than printed, and the closest (`later_turns`) is wrong on the
one turn the player is most likely to use it.

The permission ends the way the printed words say: when the card stops being
exiled. `move_object` resets every `playable_*` field on every zone change
(400.7 -- a card that left exile is a new object), so `while_exiled` needs no
expiry hook, and the loader refuses it wherever the card is not being put into
or read out of exile -- on a graveyard card the same reset would read "for as
long as it remains in your graveyard", which is a different sentence.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import turn as turn_module
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.objects import PLAYABLE_DURATIONS
from automtg.engine.zones import move_object
from tests.conftest import pass_until

FOREVER = "t_brain_impulse"  # playable: "while_exiled"


def position(builder):
    """Seat 0 holds the instant; the card it exiles is always a Mountain.

    A land for the reason `test_playable_duration.py` gives: it needs no mana,
    so the permission is the only thing that makes playing it legal.
    """
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 4)
        .battlefield(1, ["mountain"] * 4)
        .library(0, ["mountain"] * 20)
        .library(1, ["mountain"] * 20)
        .hand(0, [FOREVER])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_it(game) -> int:
    game._advance()
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FOREVER
        )
    )
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    exiled = [o for o in game.state.objects.values() if o.zone is Zone.EXILE]
    assert len(exiled) == 1
    return exiled[0].oid


def playable(game, oid: int) -> bool:
    return any(a.source == oid for a in game.legal_actions())


def to_main(game, seat: int, after_turn: int) -> None:
    pass_until(
        game,
        lambda g: g.state.step is Step.PRECOMBAT_MAIN
        and g.state.active_player == seat
        and g.state.turn > after_turn,
    )


class TestTheClock:
    def test_it_is_a_known_duration(self):
        assert "while_exiled" in PLAYABLE_DURATIONS

    def test_it_starts_on_the_turn_it_is_granted(self, builder):
        """Plot's `later_turns` is the near miss, and this is where it is wrong."""
        game = position(builder)
        oid = cast_it(game)
        assert playable(game, oid)

    def test_it_reaches_your_next_turn(self, builder):
        game = position(builder)
        oid = cast_it(game)
        to_main(game, 0, game.state.turn)
        assert playable(game, oid)

    def test_it_reaches_the_turn_after_that(self, builder):
        """Where `end_of_your_next_turn`, the longest clock, has already ended."""
        game = position(builder)
        oid = cast_it(game)
        to_main(game, 0, game.state.turn)
        to_main(game, 0, game.state.turn)
        assert playable(game, oid)
        assert game.state.objects[oid].playable_by == 0

    @pytest.mark.parametrize(
        "duration", ["this_turn", "your_next_end_step", "end_of_your_next_turn", "later_turns"]
    )
    def test_no_expiry_hook_ends_it(self, builder, duration):
        game = position(builder)
        oid = cast_it(game)
        turn_module._expire_permissions(game.state, duration)
        turn_module._expire_permissions(game.state, duration, after_grant_turn=True)
        assert game.state.objects[oid].playable_by == 0


class TestLeavingExileEndsIt:
    def test_a_card_that_leaves_exile_is_not_playable_when_it_comes_back(self, builder):
        """400.7: back in exile it is a new object, and nothing granted it anything."""
        game = position(builder)
        oid = cast_it(game)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].playable_by is None
        move_object(game.state, oid, Zone.EXILE)
        assert not playable(game, oid)

    def test_playing_it_uses_it_up(self, builder):
        game = position(builder)
        oid = cast_it(game)
        game.apply(next(a for a in game.legal_actions() if a.source == oid))
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert game.state.objects[oid].playable_by is None


class TestTheLoader:
    def spell(self, effect):
        return {
            "id": "t_probe_forever",
            "name": "Probe Forever",
            "mana_cost": "{R}",
            "types": ["Instant"],
            "spell_effects": [effect],
        }

    def compile(self, effect):
        return compile_card(CardModel.model_validate(self.spell(effect)))

    def test_exile_accepts_it(self):
        self.compile({"op": "exile", "objects": {"zone": "graveyard", "count": 1},
                      "playable": "while_exiled"})

    def test_look_at_top_into_exile_accepts_it(self):
        self.compile({"op": "look_at_top", "player": "you", "amount": {"const": 1},
                      "objects": {"count": 1}, "destination": "exile",
                      "playable": "while_exiled"})

    def test_grant_playable_over_exile_accepts_it(self):
        self.compile({"op": "grant_playable",
                      "objects": {"zone": "exile", "controller": "any", "count": "all"},
                      "playable": "while_exiled"})

    def test_look_at_top_into_a_hand_refuses_it(self):
        with pytest.raises(DslError, match="while_exiled"):
            self.compile({"op": "look_at_top", "player": "you", "amount": {"const": 1},
                          "objects": {"count": 1}, "destination": "hand",
                          "playable": "while_exiled"})

    def test_grant_playable_over_a_graveyard_refuses_it(self):
        """The reset would read it as "while it remains in your graveyard"."""
        with pytest.raises(DslError, match="while_exiled"):
            self.compile({"op": "grant_playable",
                          "objects": {"zone": "graveyard", "controller": "you", "count": "all"},
                          "playable": "while_exiled"})


class TestAnOpponentsExiledCards:
    """Elder Brain exiles an *opponent's* hand: the cards sit in their owner's exile.

    The cast side already walked every seat's exile; the land drop walked only
    the player's own, so "you may play **lands** from among the exiled cards"
    offered nothing for the one card that prints it, silently. And a land played
    that way enters under the control of the player who played it (110.2), not
    its owner's.
    """

    def their_land_exiled_for_me(self, builder):
        game = position(builder)
        game._advance()
        oid = game.state.players[1].library[0]
        move_object(game.state, oid, Zone.EXILE)
        obj = game.state.objects[oid]
        obj.playable_by = 0
        obj.playable_turn = game.state.turn
        obj.playable_duration = "while_exiled"
        return game, oid

    def test_the_land_is_offered(self, builder):
        game, oid = self.their_land_exiled_for_me(builder)
        assert oid in game.state.players[1].exile
        assert any(
            a.kind is ActionKind.PLAY_LAND and a.source == oid for a in game.legal_actions()
        )

    def test_it_enters_under_your_control(self, builder):
        game, oid = self.their_land_exiled_for_me(builder)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND and a.source == oid)
        )
        obj = game.state.objects[oid]
        assert obj.zone is Zone.BATTLEFIELD
        assert obj.controller == 0
        assert obj.owner == 1


class TestTheWorkerIsShownIt:
    def test_the_packet_lists_every_duration(self):
        from automtg.cards.authoring.packet import reference

        assert set(reference()["playable_durations"]) == set(PLAYABLE_DURATIONS)
