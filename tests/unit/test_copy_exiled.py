"""Copying a card that is not on the stack, and binning what was not cast.

Two cards, two small additions, both about the long tail of "cast it for free
from somewhere that is not your hand".

**`cast_copy` can name what it copies.** It was hardcoded to the ability's own
card, which is cipher — the only shape that had needed it. Mizzix's Mastery
copies a card it has just exiled from a graveyard, and Arcane Bombardment copies
"each card exiled with this enchantment", a pile that grows every turn.
`copy_spell` cannot serve either: it copies something on the **stack**, and
these cards are in exile with nothing on the stack to point at.

The original staying put is the load-bearing half, and `TestTheOriginalStaysInExile`
is the test for it: Mizzix's Mastery exiles the card permanently and copies it,
so the graveyard does not refill. A version that cast the card itself would hand
it back every time it resolved.

**`look_at_top` can send its remainder somewhere other than the library
bottom.** Epic Experiment's "put all cards exiled this way that weren't cast
into your graveyard" had no spelling: `rest_to_bottom` is hardwired, so the
misses would have stayed on top of the library where they can be drawn — a
strictly better card.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import pass_until

MASTERY = "t_mastery"  # exile a graveyard card, copy it, cast the copy free
EPIC = "t_epic_exp"  # look at three, cast free, bin the rest
BAIT = "t_demo_draw"  # {R} instant, draws a card


def settle(game):
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def cast(game, card_id: str):
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    settle(game)


class TestCopyingAnExiledCard:
    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["mountain"] * 6)
            .battlefield(1, ["plains"])
            .graveyard(0, [BAIT])
            .library(0, ["forest"] * 20)
            .hand(0, [MASTERY])
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_the_copy_resolves(self, builder):
        """The copied instant draws a card, so the library moves."""
        game = self.position(builder)
        before = len(game.state.players[0].library)

        cast(game, MASTERY)

        assert len(game.state.players[0].library) == before - 1

    def test_the_original_stays_in_exile(self, builder):
        """Copied, not cast. The graveyard does not refill.

        A version that cast the card itself would return it to the graveyard on
        resolution and hand it back every time -- which is the difference
        between Mizzix's Mastery and a repeatable engine.
        """
        game = self.position(builder)
        bait = game.state.players[0].graveyard[0]

        cast(game, MASTERY)

        assert game.state.objects[bait].zone is Zone.EXILE
        assert bait not in game.state.players[0].graveyard


class TestBinningTheRemainder:
    def position(self, builder):
        return (
            builder(players=2)
            .battlefield(0, ["mountain"] * 4 + ["island"] * 4)
            .battlefield(1, ["plains"])
            .library(0, ["forest", "forest", "forest", *["swamp"] * 10])
            .hand(0, [EPIC])
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )

    def test_the_uncast_cards_go_to_the_graveyard(self, builder):
        """Three Forests on top: none is an instant, so all three are binned."""
        game = self.position(builder)
        top = list(game.state.players[0].library[:3])

        cast(game, EPIC)

        for oid in top:
            assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_they_do_not_stay_on_the_library(self, builder):
        """The failure `rest_to` prevents: misses left where they can be drawn."""
        game = self.position(builder)
        top = set(game.state.players[0].library[:3])

        cast(game, EPIC)

        assert not (top & set(game.state.players[0].library))

    def test_the_rest_of_the_library_is_untouched(self, builder):
        game = self.position(builder)
        before = list(game.state.players[0].library)

        cast(game, EPIC)

        assert list(game.state.players[0].library) == before[3:]
