"""Gau, Feral Youth — "if a card left your graveyard this turn".

    At the beginning of each end step, if a card left your graveyard this turn,
    Gau deals damage equal to its power to each opponent.

The engine kept exactly one this-turn graveyard fact, `cards_to_graveyard`, and
it is wrong for this sentence twice over. It counts movement in the **opposite**
direction, so it is true in precisely the wrong games — a turn where three
creatures died and nothing was reanimated reads as three. And it is a single
total across every graveyard at the table, where this has to be answered about
*your* graveyard alone.

Nothing else came close: `cast_from_graveyard` asks about the source spell
itself, `has_turn_flag` reads a flag the same source wrote, and
`exists`/`zone_is`/`cmp` read the graveyard's current *contents*, which say
nothing about what departed — a card returned to hand and a card that was never
there look identical.

So this is the mirror tally, `cards_from_graveyard`, keyed by the graveyard's
**owner**. 400.3 puts a card in its owner's graveyard, so an opponent
reanimating your creature still emptied your yard by one, and the fact belongs
to you rather than to whoever moved it.

Tokens are excluded, for the reason they are excluded from the arrival tally: a
token in a graveyard ceases to exist as a state-based action, and counting that
as "a card left" would make the condition true on every turn anything died.
"""

from __future__ import annotations

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.zones import move_object

BEAR = "t_bear"


def left_this_turn(game, who="you", controller: int = 0) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return evaluate_value(ctx, {"cards_from_graveyard_this_turn": who})


def board(builder, *, mine: int = 1, theirs: int = 0):
    return (
        builder(players=2)
        .graveyard(0, [BEAR] * mine)
        .graveyard(1, [BEAR] * theirs)
        .build(advance=False)
    )


class TestItCountsDepartures:
    def test_nothing_has_left_yet(self, builder):
        game = board(builder)
        assert left_this_turn(game) == 0

    def test_a_card_returned_to_hand_counts(self, builder):
        game = board(builder)
        oid = game.state.players[0].graveyard[0]
        move_object(game.state, oid, Zone.HAND, to_player=0, cause="test")
        assert left_this_turn(game) == 1

    def test_a_card_exiled_counts(self, builder):
        """"To any zone" -- exile, hand, library, battlefield all count."""
        game = board(builder)
        oid = game.state.players[0].graveyard[0]
        move_object(game.state, oid, Zone.EXILE, cause="test")
        assert left_this_turn(game) == 1

    def test_a_card_reanimated_counts(self, builder):
        game = board(builder)
        oid = game.state.players[0].graveyard[0]
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0, cause="test")
        assert left_this_turn(game) == 1

    def test_two_departures_count_twice(self, builder):
        game = board(builder, mine=2)
        for oid in list(game.state.players[0].graveyard):
            move_object(game.state, oid, Zone.EXILE, cause="test")
        assert left_this_turn(game) == 2


class TestItIsNotTheOppositeTally:
    """The failure mode that made the existing value unusable."""

    def test_a_card_arriving_does_not_count(self, builder):
        # Put a card *into* the graveyard and check the mirror tally stays at
        # zero. This is the direction `cards_to_graveyard` already counted, and
        # conflating the two is the whole bug: a turn where three creatures
        # died and nothing was reanimated would fire Gau.
        game = board(builder, mine=0)
        oid = game.state.players[0].library[0]
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="test")
        assert left_this_turn(game) == 0

    def test_the_arrival_tally_still_moves(self, builder):
        """Both directions are kept, and they are different numbers."""
        game = board(builder, mine=0)
        oid = game.state.players[0].library[0]
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="test")
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"cards_to_graveyard_this_turn": True}) == 1


class TestItIsPerGraveyard:
    """"**your** graveyard", not "a graveyard"."""

    def test_an_opponents_departure_is_not_yours(self, builder):
        game = board(builder, mine=0, theirs=1)
        oid = game.state.players[1].graveyard[0]
        move_object(game.state, oid, Zone.EXILE, cause="test")
        assert left_this_turn(game, "you") == 0

    def test_and_it_is_theirs(self, builder):
        game = board(builder, mine=0, theirs=1)
        oid = game.state.players[1].graveyard[0]
        move_object(game.state, oid, Zone.EXILE, cause="test")
        assert left_this_turn(game, "opponent") == 1


class TestTheTurnBoundary:
    def test_it_resets_between_turns(self, builder):
        game = board(builder)
        oid = game.state.players[0].graveyard[0]
        move_object(game.state, oid, Zone.EXILE, cause="test")
        assert left_this_turn(game) == 1

        game.state.turn_ledger.clear()

        assert left_this_turn(game) == 0, (
            "a turn-scoped fact that survived the turn would make Gau fire forever"
        )
