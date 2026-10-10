""""…and put the rest on the bottom of your library in a random order."

    Florian, Voldaren Scion — "look at the top X cards of your library … Exile
    one of those cards and put the rest on the bottom of your library in a
    random order."

`look_at_top` had two dispositions for what you did *not* take: leave it on top
in order (the default, and what "look at" means), or `shuffle` the library.
Neither is this one.

Shuffling is a different game action. It reorders the **whole** deck, and
everything underneath the cards you looked at was already in an order somebody
may be counting on — a scry, a tutor-to-top, a Brainstorm. Putting only the
looked-at remainder on the bottom leaves the rest exactly where it was, which is
the whole point of the printed wording.

"The rest" is what was *looked at* and not taken, which includes cards the
selector filtered out of the pool: Florian looks at X cards and may exile any one
of them, but a narrower card that could only take a creature still looked at the
lands and still buries them.
"""

from __future__ import annotations

from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext


def library_ids(game, pid: int = 0) -> list[str]:
    return [
        game.state.card_of(game.state.objects[o]).id
        for o in game.state.players[pid].library
    ]


def run(game, spec) -> None:
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    generator = execute(ctx, [spec])
    for _ in generator:
        # `count: 0` asks nothing, which keeps this test about the disposition
        # rather than about the choice.
        raise AssertionError("this look asks nothing")


def board(builder):
    """A library whose order is legible: three swamps on top, then forests."""
    return (
        builder(players=2)
        .library(0, ["swamp"] * 3 + ["forest"] * 5)
        .build()
    )


LOOK = {
    "op": "look_at_top",
    "player": "you",
    "amount": {"const": 3},
    "objects": {"count": 0},
    "rest_to_bottom": True,
}


class TestTheRestGoesToTheBottom:
    def test_the_looked_at_cards_leave_the_top(self, builder):
        game = board(builder)
        run(game, LOOK)
        assert library_ids(game)[:5] == ["forest"] * 5

    def test_they_are_at_the_bottom(self, builder):
        game = board(builder)
        run(game, LOOK)
        assert library_ids(game)[5:] == ["swamp"] * 3

    def test_the_library_is_the_same_size(self, builder):
        game = board(builder)
        before = len(game.state.players[0].library)
        run(game, LOOK)
        assert len(game.state.players[0].library) == before

    def test_the_untouched_cards_keep_their_order(self, builder):
        """The whole difference from `shuffle`, which would reorder these too."""
        game = (
            builder(players=2)
            .library(0, ["swamp"] * 3 + ["forest", "island", "mountain", "plains"])
            .build()
        )
        run(game, LOOK)
        assert library_ids(game)[:4] == ["forest", "island", "mountain", "plains"]

    def test_without_the_flag_nothing_moves(self, builder):
        """The default is still "they stay on top, in order"."""
        game = board(builder)
        run(game, {**LOOK, "rest_to_bottom": False})
        assert library_ids(game)[:3] == ["swamp"] * 3

    def test_a_short_library_is_handled(self, builder):
        game = builder(players=2).library(0, ["swamp"] * 2).build()
        run(game, LOOK)
        assert library_ids(game) == ["swamp"] * 2
