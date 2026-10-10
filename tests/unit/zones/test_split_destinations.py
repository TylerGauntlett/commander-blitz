"""One look at the top, three cards, three different destinations.

Expressive Iteration: "Look at the top three cards of your library. Put one of
them into your hand, put one of them on the bottom of your library, and exile
one of them. You may play the exiled card this turn."

`look_at_top` resolved exactly one `destination`, and its only remainder key —
`rest_to_bottom` — is hardwired to the bottom and takes *everything* not picked.
So it could say hand-plus-bottom, or exile-plus-bottom, and never all three.

Two sequential looks is the tempting workaround and is a different card: the
second reads a top the first has already changed, and `as` binds only what was
taken, so nothing can name "the other two". `destinations` keeps it one window —
each step draws from what the earlier ones left, which is what makes the three
choices one decision.

The library is stocked with three distinguishable cards so the test can say
which went where, rather than only counting.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import pass_until

ITERATION = "t_iteration"
#: Three different top cards, so "which one went where" is answerable.
TOP_THREE = ["t_bear", "t_stormbolt", "t_casualty"]


def position(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island", "mountain"])
        .battlefield(1, ["plains"])
        .library(0, [*TOP_THREE, *["forest"] * 10])
        .hand(0, [ITERATION])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_and_settle(game):
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == ITERATION
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def zones_of(game, oids) -> list[Zone]:
    return [game.state.objects[o].zone for o in oids]


class TestAllThreeDestinationsAreReached:
    def test_one_card_goes_to_each(self, builder):
        """The claim `rest_to_bottom` cannot make: hand AND bottom AND exile."""
        game = position(builder)
        top = list(game.state.players[0].library[:3])

        cast_and_settle(game)

        landed = zones_of(game, top)
        assert sorted(z.value for z in landed) == ["exile", "hand", "library"]

    def test_the_hand_gains_exactly_one(self, builder):
        game = position(builder)
        cast_and_settle(game)
        # The sorcery left the hand and one looked card arrived.
        assert len(game.state.players[0].hand) == 1

    def test_the_bottom_card_is_at_the_bottom(self, builder):
        """Not merely "in the library" -- the printed word is bottom."""
        game = position(builder)
        top = list(game.state.players[0].library[:3])

        cast_and_settle(game)

        library = game.state.players[0].library
        tucked = [o for o in top if o in library]
        assert len(tucked) == 1
        assert library.index(tucked[0]) == len(library) - 1


class TestTheExiledCardIsPlayable:
    def test_it_carries_the_play_permission(self, builder):
        """"You may play the exiled card this turn" belongs to the exile step."""
        game = position(builder)
        top = list(game.state.players[0].library[:3])

        cast_and_settle(game)

        exiled = [o for o in top if game.state.objects[o].zone is Zone.EXILE]
        assert len(exiled) == 1
        obj = game.state.objects[exiled[0]]
        assert obj.playable_by == 0
        assert obj.playable_turn == game.state.turn

    def test_the_hand_card_carries_no_such_flag(self, builder):
        """The permission is on one step, not on the whole op."""
        game = position(builder)
        top = list(game.state.players[0].library[:3])

        cast_and_settle(game)

        in_hand = [o for o in top if game.state.objects[o].zone is Zone.HAND]
        assert len(in_hand) == 1
        assert game.state.objects[in_hand[0]].playable_by is None


class TestTheRestOfTheLibraryIsUndisturbed:
    def test_only_the_three_looked_at_cards_moved(self, builder):
        game = position(builder)
        before = list(game.state.players[0].library)
        top = set(before[:3])

        cast_and_settle(game)

        after = [o for o in game.state.players[0].library if o not in top]
        assert after == before[3:], "everything under the window kept its order"
