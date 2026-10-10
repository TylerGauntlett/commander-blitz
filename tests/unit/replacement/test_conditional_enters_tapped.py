"""Enters tapped *unless* — a replacement effect that stops to look at the board.

    "This land enters tapped unless you control a Mountain or a Plains." (614.12)

The engine has always had `self_enters_tapped`, and `zones._enter_battlefield`
applied it unconditionally. That is not a rounding error on a checkland: it is a
different card. The whole reason Clifftop Retreat is played over a Guildgate is
that on turn three it is usually untapped, and a version that never is has been
downgraded to the worst dual in the format while still claiming to be the card
in the deck list.

The proxy generator made the honest choice here and it is worth saying why the
fix went this way round. `proxy._enters_tapped` deliberately generated these
lands as **always tapped**, never as always untapped, because a free untapped
dual is a strict upgrade over the printed card and distorts a game far more than
a tapped one does. So the bug this closes was always a card that was too weak,
never one that was too strong — and the same asymmetry is why
`_unless_condition` returns `None` rather than guessing when it does not
recognise a printed shape.

**Nothing new evaluates the condition.** `evaluate_condition` in
`effects/conditions.py` was already the standalone evaluator for trigger
intervening-if clauses; it simply had no caller on the enters-the-battlefield
path. The condition is stored as the clause the permanent enters *tapped* under
— the negation of what is printed — so that `condition` here means what
`condition` means everywhere else in the DSL: when this applies.

The one thing that genuinely had to be got right is **ordering**. `move_object`
calls `_add_to_zone` before `_enter_battlefield`, so the land is already on the
battlefield when its own condition is evaluated. "Two or more *other* lands"
therefore needs `exclude_self`, and a version without it counts the arriving
land and enters untapped a turn early, every time. The witnesses are Clifftop
Retreat (subtype test), Sundown Pass (count of other lands) and the fastland
cycle, which reads the same count the other way round.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Zone
from commanderblitz.engine.zones import move_object

CHECKLAND = "t_checkland"  # tapped unless you control a Mountain or a Plains
SLOWLAND = "t_slowland"  # tapped unless you control two or more other lands
FASTLAND = "t_fastland"  # tapped unless you control two or fewer other lands


def position(builder, board: list[str], land: str):
    """``(game, oid)`` for ``land`` put onto a battlefield already holding ``board``."""
    game = builder(players=2).battlefield(0, board).hand(0, [land]).build()
    oid = next(
        o.oid
        for o in game.state.objects.values()
        if o.zone is Zone.HAND and game.state.card_of(o).id == land
    )
    move_object(game.state, oid, Zone.BATTLEFIELD)
    return game, oid


def entered_tapped(builder, board: list[str], land: str) -> bool:
    game, oid = position(builder, board, land)
    return game.state.objects[oid].tapped


class TestASubtypeTest:
    def test_it_enters_tapped_with_neither_subtype(self, builder):
        assert entered_tapped(builder, ["island", "swamp"], CHECKLAND)

    def test_it_enters_untapped_with_the_first_subtype(self, builder):
        assert not entered_tapped(builder, ["mountain"], CHECKLAND)

    def test_it_enters_untapped_with_the_second_subtype(self, builder):
        """The clause is a disjunction, so either half alone is enough."""
        assert not entered_tapped(builder, ["plains"], CHECKLAND)

    def test_an_empty_board_enters_tapped(self, builder):
        assert entered_tapped(builder, [], CHECKLAND)

    def test_it_does_not_read_the_opponents_board(self, builder):
        """"You control" — a Mountain across the table is not yours."""
        game = builder(players=2).battlefield(1, ["mountain"]).hand(0, [CHECKLAND]).build()
        oid = next(
            o.oid
            for o in game.state.objects.values()
            if o.zone is Zone.HAND and game.state.card_of(o).id == CHECKLAND
        )
        move_object(game.state, oid, Zone.BATTLEFIELD)
        assert game.state.objects[oid].tapped


class TestACountOfOtherLands:
    def test_one_other_land_is_not_enough(self, builder):
        assert entered_tapped(builder, ["island"], SLOWLAND)

    def test_two_other_lands_is_the_boundary(self, builder):
        assert not entered_tapped(builder, ["island", "swamp"], SLOWLAND)

    def test_it_does_not_count_itself(self, builder):
        """The land is already in `state.battlefield` when its condition runs.

        Without `exclude_self` one other land plus itself reads as two and the
        slowland enters untapped a full turn early.
        """
        assert entered_tapped(builder, ["island"], SLOWLAND)

    def test_nonland_permanents_do_not_count(self, builder):
        assert entered_tapped(builder, ["island", "t_bear", "t_bear"], SLOWLAND)


class TestTheSameCountReadTheOtherWay:
    """A fastland is untapped *early* — the comparison is inverted, not the count."""

    def test_two_other_lands_still_enters_untapped(self, builder):
        assert not entered_tapped(builder, ["island", "swamp"], FASTLAND)

    def test_three_other_lands_enters_tapped(self, builder):
        assert entered_tapped(builder, ["island", "swamp", "forest"], FASTLAND)

    def test_an_empty_board_enters_untapped(self, builder):
        assert not entered_tapped(builder, [], FASTLAND)


class TestTheReplacementStillAppliesWithoutACondition:
    """An unconditional tapland must not have been broken by any of this."""

    def test_a_plain_tapland_still_enters_tapped(self, builder):
        assert entered_tapped(builder, ["island", "swamp", "forest"], "t_bounce_land")
