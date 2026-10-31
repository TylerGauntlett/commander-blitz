"""Which arrivals this turn were **nontoken** -- rule 111.1, read off the ledger.

    "At the beginning of your end step, create a number of Food tokens equal to
     the number of nontoken creatures you had enter the battlefield under your
     control this turn."                               -- Gyome, Master Chef

A count of *arrivals*, so it belongs to `permanents_entered_this_turn` and its
`EnteredPermanent` snapshots, and the snapshot has to say whether the arrival was
a token. Without the clause the value counts every creature token too: a turn
that made three Soldiers hands Gyome three extra Food.

The near miss is the board, and it is wrong for the reason the ledger exists:
`{"count": {"zone": "battlefield", "is_token": false, "entered_this_turn": true}}`
forgets a creature that entered and then died, was sacrificed or was flickered
away before the end step -- and Gyome's deck sacrifices its creatures for value.
Reading the token flag off the snapshot is also the only way to ask it at all
after a token has left: the token state-based action (704.5d) pops it out of
`state.objects`.

`is_token` is the selector language's spelling: `false` is "nontoken", `true` is
"token", and the clause left out asks neither.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.characteristics import _static_value
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.state import new_object
from commanderblitz.engine.zones import move_object

BEAR = "t_bear"  # {1}{G} 2/2 Bear -- a nontoken creature
SOLDIER_TOKEN = "soldier_1_1_w"  # a 1/1 white Soldier creature token
FOOD_TOKEN = "food_token"  # a token, and not a creature

#: Gyome's count, as a card writes it.
NONTOKEN_CREATURES = {"controller": "you", "types": ["Creature"], "is_token": False}

#: The board-shaped near miss, kept beside it so both are measured on one board.
NONTOKEN_CREATURES_STANDING = {
    "count": {
        "zone": "battlefield",
        "controller": "you",
        "types": ["Creature"],
        "is_token": False,
        "entered_this_turn": True,
    }
}


# ----------------------------------------------------------------------
# the position
# ----------------------------------------------------------------------


def board(builder):
    b = builder(players=2)
    b.battlefield(0, ["forest"] * 3)
    return b.build()


def ctx(game, controller: int = 0) -> EffectContext:
    return EffectContext(state=game.state, controller=controller, source_oid=None)


def entered(game, spec, controller: int = 0) -> int:
    return evaluate_value(ctx(game, controller), {"permanents_entered_this_turn": spec})


def enter(game, card_id: str, pid: int = 0) -> int:
    """A card from hand onto the battlefield, through the real enters event."""
    obj = new_object(game.state, card_id, owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD)
    return obj.oid


# ----------------------------------------------------------------------
# the snapshot
# ----------------------------------------------------------------------


class TestTheSnapshotRecordsTheToken:
    def test_a_card_arrives_as_a_nontoken(self, builder):
        game = board(builder)
        enter(game, BEAR)
        [record] = game.state.turn_ledger.permanents_entered
        assert record.is_token is False

    def test_a_token_arrives_as_a_token(self, builder):
        game = board(builder)
        create_token(game.state, SOLDIER_TOKEN, 0, 1)
        [record] = game.state.turn_ledger.permanents_entered
        assert record.is_token is True


# ----------------------------------------------------------------------
# the count
# ----------------------------------------------------------------------


class TestNontokenCountsOnlyCards:
    def test_a_token_creature_that_entered_is_not_counted(self, builder):
        """The boundary the clause exists for: without it, every Soldier made
        this turn is one more Food."""
        game = board(builder)
        create_token(game.state, SOLDIER_TOKEN, 0, 3)
        assert entered(game, NONTOKEN_CREATURES) == 0
        assert entered(game, {"controller": "you", "types": ["Creature"]}) == 3, (
            "the unfiltered value does count them -- which is the extra Food"
        )

    def test_a_nontoken_creature_is_counted_beside_tokens(self, builder):
        game = board(builder)
        enter(game, BEAR)
        create_token(game.state, SOLDIER_TOKEN, 0, 2)
        assert entered(game, NONTOKEN_CREATURES) == 1

    def test_true_asks_for_the_tokens(self, builder):
        game = board(builder)
        enter(game, BEAR)
        create_token(game.state, SOLDIER_TOKEN, 0, 2)
        create_token(game.state, FOOD_TOKEN, 0, 1)
        assert entered(game, {"controller": "you", "is_token": True}) == 3
        assert entered(game, {"controller": "you", "types": ["Creature"], "is_token": True}) == 2

    def test_the_opponents_arrivals_are_theirs(self, builder):
        game = board(builder)
        enter(game, BEAR, pid=1)
        assert entered(game, NONTOKEN_CREATURES) == 0
        assert entered(game, NONTOKEN_CREATURES, controller=1) == 1


class TestItIsTheArrivalAndNotTheBoard:
    def test_a_nontoken_creature_that_entered_and_left_still_counts(self, builder):
        """The case the ledger exists for. The Bear entered and was sacrificed
        before the end step; it still entered, and the board has forgotten it."""
        game = board(builder)
        oid = enter(game, BEAR)
        move_object(game.state, oid, Zone.GRAVEYARD)

        assert entered(game, NONTOKEN_CREATURES) == 1
        assert evaluate_value(ctx(game), NONTOKEN_CREATURES_STANDING) == 0, (
            "the battlefield count is the near miss this value refuses"
        )

    def test_a_token_that_entered_and_left_is_still_a_token(self, builder):
        """A token that has left is popped out of `state.objects`, so only the
        snapshot can still say what it was -- and it was not a nontoken."""
        game = board(builder)
        [oid] = create_token(game.state, SOLDIER_TOKEN, 0, 1)
        move_object(game.state, oid, Zone.GRAVEYARD)
        game.state.objects.pop(oid, None)

        assert entered(game, NONTOKEN_CREATURES) == 0
        assert entered(game, {"controller": "you", "is_token": True}) == 1


class TestTheStaticSideReadsTheSameClause:
    def test_a_static_magnitude_honours_is_token(self, builder):
        """The value is admissible in `STATIC_VALUE_KEYS` too, and evaluated by
        a second reader; both must pass the clause through."""
        game = board(builder)
        bear = enter(game, BEAR)
        create_token(game.state, SOLDIER_TOKEN, 0, 2)
        source = game.state.objects[bear]
        expr = {"permanents_entered_this_turn": NONTOKEN_CREATURES}
        assert _static_value(game.state, expr, source) == 1


# ----------------------------------------------------------------------
# load time
# ----------------------------------------------------------------------


class TestTheClauseIsCheckedAtLoadTime:
    def validate(self, spec):
        validate_value({"permanents_entered_this_turn": spec}, "test")

    def test_the_printed_shape_validates(self):
        self.validate(NONTOKEN_CREATURES)

    def test_is_token_must_be_a_boolean(self):
        """`"false"` is a non-empty string, so truthiness would turn
        "nontoken creatures" into "creature tokens"."""
        with pytest.raises(DslError, match="is_token"):
            self.validate({"controller": "you", "is_token": "false"})
