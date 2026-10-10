"""Fact or Fiction: the one effect whose first decision is somebody else's.

"An opponent separates those cards into two piles. Put one pile into your hand
and the other into your graveyard."

The card is entirely that tension — the splitter wants both piles to be bad, the
caster takes the better one — so the property worth pinning is *who is asked*.
An implementation that let the caster do the splitting would be a strictly
better spell than the one printed, and it would look completely normal on
screen.

The rest is bookkeeping that is easy to get wrong in ways nobody would notice:
every revealed card has to end up somewhere, and it must be five cards, not
five *draws*.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import _default_answer


def board(builder):
    return (
        builder(players=2)
        .battlefield(0, ["island"] * 4)
        .hand(0, ["fact_or_fiction"])
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_it(game):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == "fact_or_fiction"
    )
    top_five = list(game.state.players[0].library[:5])
    game.apply(action)
    return action.source, top_five


def run(game, *, split: int, take_first: bool) -> None:
    """Answer the split with ``split`` cards, then take one pile or the other."""
    picked = 0
    for _ in range(200):
        decision = game.pending()
        if decision is None:
            return
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            if picked < split:
                choose = next(
                    a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE
                )
                picked += 1
                game.apply(choose)
                continue
            done = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.FINISH_DECLARATION
                ),
                None,
            )
            game.apply(done or _default_answer(game, decision))
            continue
        if decision.kind is DecisionKind.MAY:
            want = ActionKind.YES if take_first else ActionKind.NO
            game.apply(next(a for a in game.legal_actions() if a.kind is want))
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            return
        game.apply(_default_answer(game, decision))


class TestWhoIsAsked:
    def test_the_opponent_makes_the_piles(self, builder):
        """The decision that makes the card. It must not be the caster's."""
        game = board(builder)
        cast_it(game)
        # Both players pass, the spell resolves, and the split is asked for.
        for _ in range(50):
            decision = game.pending()
            if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
                assert decision.player == 1, "an *opponent* separates the cards"
                return
            game.apply(_default_answer(game, decision))
        raise AssertionError("the split was never asked for")

    def test_the_caster_chooses_which_pile(self, builder):
        game = board(builder)
        cast_it(game)
        seen_split = False
        for _ in range(50):
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                seen_split = True
            if decision.kind is DecisionKind.MAY:
                assert seen_split, "the split comes first"
                assert decision.player == 0, "the *caster* picks a pile"
                return
            game.apply(_default_answer(game, decision))
        raise AssertionError("the pile choice was never asked for")


class TestWhereTheCardsGo:
    def test_five_leave_the_library_and_all_five_land_somewhere(self, builder):
        game = board(builder)
        spell, five = cast_it(game)
        library_before = len(game.state.players[0].library)

        run(game, split=2, take_first=True)

        assert len(game.state.players[0].library) == library_before - 5
        landed = [
            oid
            for oid in five
            if game.state.objects[oid].zone in (Zone.HAND, Zone.GRAVEYARD)
        ]
        assert len(landed) == 5, "no card may be left in limbo"
        assert game.state.objects[spell].zone is Zone.GRAVEYARD

    def test_taking_the_first_pile_puts_that_many_in_hand(self, builder):
        game = board(builder)
        _, five = cast_it(game)
        run(game, split=2, take_first=True)

        in_hand = [oid for oid in five if game.state.objects[oid].zone is Zone.HAND]
        in_yard = [oid for oid in five if game.state.objects[oid].zone is Zone.GRAVEYARD]
        assert len(in_hand) == 2
        assert len(in_yard) == 3

    def test_declining_takes_the_other_pile_instead(self, builder):
        game = board(builder)
        _, five = cast_it(game)
        run(game, split=2, take_first=False)

        in_hand = [oid for oid in five if game.state.objects[oid].zone is Zone.HAND]
        assert len(in_hand) == 3, "the pile the opponent did not name"

    def test_an_empty_pile_is_a_legal_split(self, builder):
        """Making one pile empty is the standard way to play against it."""
        game = board(builder)
        _, five = cast_it(game)
        run(game, split=0, take_first=True)

        in_hand = [oid for oid in five if game.state.objects[oid].zone is Zone.HAND]
        in_yard = [oid for oid in five if game.state.objects[oid].zone is Zone.GRAVEYARD]
        assert (len(in_hand), len(in_yard)) == (0, 5), "took the empty pile"
