"""Tucking to the **bottom** of a library, and letting the owner pick which end.

Ice Magic's middle tier: "Target creature's owner puts it on their choice of the
top or bottom of their library." Two things `put_on_top` could not say.

`from_top` counts from the top and cannot reach the bottom: the depth that would
is the library's current length, which is a number the card does not print, that
nobody knows at authoring time, and that a shuffle invalidates. So `bottom` is
its own flag and `to_index=None` — which appends — rather than a computed
length, because a length read before the card has left its old zone is already
one short.

`owner_chooses` asks **the owner**, not the resolving player. That is the
printed line, and the difference is the whole value of the card: asking the
caster would hand them a tempo decision the card deliberately gives away.
`TestTheOwnerDecides` is that claim.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import only_oid, pass_until

BOTTOM = "t_tuck_bottom"  # always the bottom
CHOICE = "t_tuck_choice"  # the owner picks an end
TOP = "t_tuck_top"  # always the top -- the control
BEAR = "t_bear"


def position(builder, spell: str):
    """The opponent owns the creature and holds a five-card library.

    Theirs rather than mine so "its owner" and "the resolving player" are
    different people, which is the only board where `owner_chooses` can be told
    apart from asking the caster.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["island", "island"])
        .battlefield(1, [BEAR, "plains"])
        .library(0, ["forest"] * 10)
        .library(1, ["swamp"] * 5)
        .hand(0, [spell])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast_at_the_bear(game, spell: str, *, answer: bool | None = None) -> int:
    """Cast ``spell`` at the opponent's Bear; return its index in their library.

    ``answer`` is what the owner says to "put it on top?" when asked.
    """
    bear = only_oid(game, BEAR, 1)
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == spell
    )
    game.apply(action)

    if answer is not None:
        # The question is asked as the spell RESOLVES, so priority has to pass
        # first -- reading `pending()` straight after the cast finds the
        # opponent holding priority with the spell still on the stack.
        pass_until(
            game,
            lambda g: (g.pending() is not None and g.pending().kind is DecisionKind.MAY)
            or not g.state.stack,
        )
        pending = game.pending()
        assert pending is not None and pending.kind is DecisionKind.MAY, pending
        assert pending.player == 1, "the OWNER is asked, not the caster"
        kind = ActionKind.YES if answer else ActionKind.NO
        game.apply(next(a for a in game.legal_actions() if a.kind is kind))

    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    library = game.state.players[1].library
    assert bear in library, "the creature reached its owner's library"
    return library.index(bear)


class TestTheBottom:
    def test_it_goes_to_the_very_bottom(self, builder):
        """Index 5 of a six-card library -- the last card, not the second."""
        game = position(builder, BOTTOM)
        assert cast_at_the_bear(game, BOTTOM) == 5

    def test_the_top_is_the_control(self, builder):
        game = position(builder, TOP)
        assert cast_at_the_bear(game, TOP) == 0

    def test_it_is_the_owners_library_not_the_casters(self, builder):
        """"its owner's library" -- the caster's is untouched."""
        game = position(builder, BOTTOM)
        before = len(game.state.players[0].library)
        cast_at_the_bear(game, BOTTOM)
        assert len(game.state.players[0].library) == before


class TestTheOwnerDecides:
    def test_the_owner_may_choose_the_top(self, builder):
        game = position(builder, CHOICE)
        assert cast_at_the_bear(game, CHOICE, answer=True) == 0

    def test_the_owner_may_choose_the_bottom(self, builder):
        game = position(builder, CHOICE)
        assert cast_at_the_bear(game, CHOICE, answer=False) == 5

    def test_the_question_goes_to_the_owner(self, builder):
        """The caster would take the bottom every time; the card gives that away.

        A version that asked the wrong seat is strictly better than printed, and
        this is the only board that can tell them apart -- the creature is the
        opponent's, so owner and resolving player are different people.
        """
        game = position(builder, CHOICE)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == CHOICE
        )
        game.apply(action)
        pass_until(
            game,
            lambda g: (g.pending() is not None and g.pending().kind is DecisionKind.MAY)
            or not g.state.stack,
        )

        pending = game.pending()
        assert pending is not None and pending.kind is DecisionKind.MAY
        assert pending.player == 1, "the owner, not the caster"
