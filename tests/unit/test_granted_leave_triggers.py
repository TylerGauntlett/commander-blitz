"""An ability granted until end of turn, firing on its own creature's death.

    Malakir Rebirth — "Until end of turn, that creature gains 'When this
    creature dies, return it to the battlefield tapped under its owner's
    control.'"

Granting a triggered ability already worked, and so did the until-end-of-turn
duration; Herd Heirloom is the shipped precedent. What did not work was the one
combination this card is: a granted ability that fires on the *departure* of the
creature it was granted to. Two independent defects, and either alone was fatal.

**1. The grant was gone before the event.** `move_object` calls
`reset_permanent_state`, which empties `until_eot`, and only *then* fires
`LEAVES_BATTLEFIELD` and `DIES`. So `granted_abilities` returned nothing at the
moment it was asked. `left_with` is the departure snapshot, in the same style as
`had_counters`, `was_creature` and `last_attached_to` — written by `move_object`
before the reset, cleared as the object next enters the battlefield so it can
only ever answer for the departure it describes.

**2. The scan never looked.** Every other branch of `_candidates` pairs a
`card.abilities` walk with `granted_abilities`. The leave-the-battlefield branch
walked printed abilities only, so even an intact grant could not have queued.

The witness for both being needed is that the *byte-identical printed* ability on
the same creature always worked — which is what made this look like a card
problem rather than an engine one.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Zone
from automtg.engine.zones import destroy
from tests.conftest import oids_of, pass_until

REBIRTH = "t_rebirth"  # grants "when this dies, return it tapped"
BEAR = "t_bear"
SWAMP = "swamp"


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, [SWAMP, BEAR])
        .hand(0, [REBIRTH])
        .library(0, [SWAMP] * 20)
        .active(0)
        .max_turns(2)
        .build()
    )


def settle(game):
    pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)


def cast_it(game) -> int:
    """Cast the grant at the Bear, and return the Bear's oid."""
    bear = oids_of(game, BEAR)[0]
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == REBIRTH
            and any(t.id == bear for t in a.targets)
        )
    )
    settle(game)
    return bear


class TestTheGrantSurvivesTheDeath:
    def test_the_creature_comes_back(self, builder):
        game = board(builder)
        bear = cast_it(game)

        destroy(game.state, bear)
        settle(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_it_comes_back_tapped(self, builder):
        game = board(builder)
        bear = cast_it(game)

        destroy(game.state, bear)
        settle(game)

        assert game.state.objects[bear].tapped

    def test_an_ungranted_creature_stays_dead(self, builder):
        """The control. Without it this proves nothing about the grant."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]

        destroy(game.state, bear)
        settle(game)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD


class TestTheDepartureSnapshot:
    def test_the_grant_is_remembered_across_the_move(self, builder):
        game = board(builder)
        bear = cast_it(game)
        assert game.state.objects[bear].until_eot, "granted while alive"

        destroy(game.state, bear)

        assert game.state.objects[bear].left_with, "and remembered on the way out"

    def test_it_is_cleared_when_the_creature_returns(self, builder):
        """Otherwise the snapshot would answer for a departure long past."""
        game = board(builder)
        bear = cast_it(game)

        destroy(game.state, bear)
        settle(game)

        assert game.state.objects[bear].left_with == ()

    def test_it_returns_only_once(self, builder):
        """The grant was until end of turn and has been spent.

        A snapshot that outlived its departure would return the creature every
        time it died for the rest of the game.
        """
        game = board(builder)
        bear = cast_it(game)
        destroy(game.state, bear)
        settle(game)

        destroy(game.state, bear)
        settle(game)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD
