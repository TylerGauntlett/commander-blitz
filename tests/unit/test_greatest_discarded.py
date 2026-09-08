""""…draws cards equal to the greatest number of cards a player discarded this way."

Windfall. The number is neither the total pitched nor the drawing player's own
count — it is the largest single hand that went — and every existing way to ask
was wrong in a way nobody would notice at the table:

- `{"count": {"binding": ...}}` over the discard's own binding is the **total**
  across all players. On two hands of 3 and 1 it draws four each instead of
  three.
- `cards_in_hand` and `max_count_of` read the board when the `draw` runs, and
  by then every hand is empty. Both evaluate to 0 and the card does nothing.
- `cards_to_graveyard_this_turn` is a turn-wide tally over every graveyard,
  which also counts what was already sitting in them.

So the leaf groups the discard binding by owner and takes the largest group.
Nothing new is recorded to make that possible: `discard`'s `as` already
accumulates oids across players, and an oid knows its owner.

The asymmetric position is the whole test — equal hands would pass under three
of the four wrong readings.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step
from tests.conftest import pass_until

WINDFALL = "t_windfall"


def position(builder, mine: int, theirs: int):
    """Hands of deliberately different sizes, plus the spell itself.

    ``mine`` and ``theirs`` count the cards each player holds *besides*
    Windfall, so the discard sees ``mine + 1`` and ``theirs``.
    """
    return (
        builder(players=2)
        .battlefield(0, ["island", "island", "island"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .hand(0, [WINDFALL, *["forest"] * mine])
        .hand(1, ["forest"] * theirs)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_it(game):
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == WINDFALL
    )
    game.apply(action)
    # Stop the moment the spell has finished resolving, not at the next priority
    # window. With every hand emptied there is nothing for anyone to do, so
    # auto-pass runs on into the opponent's turn and their draw step hands them
    # a card -- which read as "the draw fired for one player and not the other".
    pass_until(game, lambda g: not g.state.stack)


def hands(game) -> tuple[int, int]:
    return len(game.state.players[0].hand), len(game.state.players[1].hand)


class TestItIsTheGreatest:
    def test_the_bigger_hand_sets_the_draw_for_everyone(self, builder):
        """Mine is 3 after the cast, theirs is 1. Both draw 3, not 4 and not 1."""
        game = position(builder, mine=3, theirs=1)
        cast_it(game)

        assert hands(game) == (3, 3)

    def test_the_opponents_hand_can_be_the_greatest(self, builder):
        """It is not "your" count -- I pitch 1, they pitch 5, everyone draws 5."""
        game = position(builder, mine=0, theirs=5)
        cast_it(game)

        assert hands(game) == (5, 5)


class TestItIsNotTheTotal:
    def test_three_and_one_draws_three_not_four(self, builder):
        """The reading `{"count": {"binding": ...}}` would give: 3 + 1 = 4.

        Separate from the test above because it is a different claim about the
        same board -- that one says the number is right, this one says which
        wrong number it is not.
        """
        game = position(builder, mine=3, theirs=1)
        cast_it(game)

        assert hands(game)[0] != 4, "the total, not the greatest"
        assert hands(game) == (3, 3)


class TestEmptyHands:
    def test_nobody_holding_anything_draws_nothing(self, builder):
        """The boundary: greatest of nothing is zero, so no draw at all.

        Asserted on the caster's library rather than on both hands. With every
        hand empty there is nothing for anyone to do, so the turn rolls on and
        the opponent's own draw step hands them a card -- which is the game
        working, not this card, and would read as a phantom draw here.
        """
        game = position(builder, mine=0, theirs=0)
        before = len(game.state.players[0].library)
        cast_it(game)

        assert len(game.state.players[0].library) == before, "no draw fired"
        assert game.state.players[0].hand == []

    def test_one_empty_hand_still_takes_the_others_count(self, builder):
        game = position(builder, mine=0, theirs=2)
        cast_it(game)

        assert hands(game) == (2, 2)
