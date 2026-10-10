"""Two ways a token leaves your control, told apart from every other way.

    Mirkwood Bats — "Whenever you create or sacrifice a token, each opponent
    loses 1 life."

One printed line, two events, and neither existed as a DSL trigger.

**`sacrificed`.** `dies`, `creature_dies` and `leaves_battlefield` are the only
departure triggers and not one of them can tell a sacrifice from a removal
spell — which is most of what this card is about, since sacrificing is a choice
the controller makes and dying is not. `move_object` already tagged the move
`cause="sacrificed"`, but that tag reached only the `zone_change` payload.

Fired **beside** `dies` rather than instead of it. A sacrificed creature really
does die, and everything already listening for a death must still hear one;
replacing the event would silently break every Blood Artist in the pool.

`player` is the controller snapshotted *before* the move, not the owner.
`reset_permanent_state` hands control back on the way out, and "whenever **you**
sacrifice" is a different question from "whenever a permanent you own is
sacrificed" the moment anybody steals anything.

**`token_created`.** The event has existed since tokens did and nothing was
subscribed to it — `state.emit` records in the log, `fire` reaches the trigger
bus, and it was the former. `permanent_enters` with `{"is_token": true}` is the
near miss and is close enough to be tempting, because rule 111.1 makes creating
a token and putting it onto the battlefield one act. It is still the wrong
question: it also fires for a token that left and returned, and it reads the
*entering permanent's* controller rather than the creator's.

Frontend: `sacrificed` joins the silent set beside `dies`, for the same reason
`dies` is there — `zone_change` already owns the departure line, and a third
event for one creature would toll three times.
"""

from __future__ import annotations

from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.zones import destroy, sacrifice
from tests.conftest import oids_of, settle

BATS = "t_bats"  # "whenever you create or sacrifice a token, each opponent loses 1"
TOKEN = "vampire_1_1_b"
BEAR = "t_bear"


def board(builder, extra=()):
    return (
        builder(players=2)
        .battlefield(0, [BATS, *extra])
        .library(0, ["swamp"] * 20)
        .build()
    )


class TestCreatingAToken:
    def test_it_drains_each_opponent(self, builder):
        game = board(builder)
        life = game.state.players[1].life

        create_token(game.state, TOKEN, 0, 1)
        settle(game)

        assert game.state.players[1].life == life - 1

    def test_two_tokens_drain_twice(self, builder):
        """One event per token, which is what `create_token` already emitted."""
        game = board(builder)
        life = game.state.players[1].life

        create_token(game.state, TOKEN, 0, 2)
        settle(game)

        assert game.state.players[1].life == life - 2

    def test_an_opponents_token_does_not(self, builder):
        """"Whenever **you** create" -- the creator, not the table."""
        game = board(builder)
        life = game.state.players[1].life

        create_token(game.state, TOKEN, 1, 1)
        settle(game)

        assert game.state.players[1].life == life


class TestSacrificingAToken:
    def test_it_drains_each_opponent(self, builder):
        game = board(builder)
        token = create_token(game.state, TOKEN, 0, 1)[0]
        settle(game)
        life = game.state.players[1].life

        sacrifice(game.state, token)
        settle(game)

        assert game.state.players[1].life == life - 1

    def test_destroying_the_same_token_does_not(self, builder):
        """The whole distinction: a removal spell is not a sacrifice."""
        game = board(builder)
        token = create_token(game.state, TOKEN, 0, 1)[0]
        settle(game)
        life = game.state.players[1].life

        destroy(game.state, token)
        settle(game)

        assert game.state.players[1].life == life

    def test_sacrificing_a_nontoken_does_not(self, builder):
        """The filter is `is_token`, read off the object."""
        game = board(builder, extra=(BEAR,))
        bear = oids_of(game, BEAR)[0]
        life = game.state.players[1].life

        sacrifice(game.state, bear)
        settle(game)

        assert game.state.players[1].life == life


class TestTheDeathIsStillADeath:
    """Firing `sacrificed` beside `dies` rather than instead of it."""

    def test_a_sacrificed_creature_still_fires_dies(self, builder):
        from commanderblitz.engine.events import EventType

        game = board(builder, extra=(BEAR,))
        bear = oids_of(game, BEAR)[0]
        before = len(game.state.events)

        sacrifice(game.state, bear)

        kinds = [e.type for e in game.state.events[before:]]
        assert EventType.DIES in kinds
        assert EventType.SACRIFICED in kinds
