""""Exile that spell instead of putting it into your graveyard as it resolves.
If you do, it becomes plotted."

Lilah, Undefeated Slickshot. Plot (702.171a) is "you may cast it as a sorcery on
a later turn without paying its mana cost", and the gap record filed three needs
for it. Two of them turned out to be shapes this session had already built for
other cards, which is the useful part:

**The rider** is `grant_rebound`'s slot exactly — a flag on the spell's object,
written while it is still on the stack, read by `_place_after_resolution`, and
turned into what it leaves behind *after* the move, because
`reset_permanent_state` runs on the way to exile and wipes anything set first.
Rebound leaves one free cast owed at the next upkeep; plot leaves a standing
permission with no end. `TestItIsNotAnExileOp` is why it has to be a rider at all.

**The permission** is `playable_by` with a fourth duration. `later_turns` is the
only one with a *start* rather than an end — nothing expires a plotted card, and
the turn it was plotted on is the one turn it may not be cast.
`TestNotTheTurnItWasPlotted` is that half, and it is also the loop guard: the
plotted card is cast from **exile**, so `cast_from_hand` on the rider is what
stops a plotted spell re-plotting itself for ever.

Only the third need was new, and it is one word. "Multicolored" is two or more
colors (202.2b), and `colors` cannot say it: that is a membership test, so
`["U","R"]` matches a mono-red spell. `TestOnlyMulticolouredSpells` keeps the
mono-coloured near miss as a live card, because it is the card `colors` would
have given.

"If you do" needs no expression of its own: the exile and the plotting are one
rider, so there is no state where the first happened and the second did not.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import pass_until

LILAH = "t_lilah"
GOLD = "t_gold_bolt"  # {U}{R} instant -- multicoloured
MONO = "t_mono_bolt"  # {R} instant -- the near miss
GOLD_CREATURE = "t_gold_creature"  # multicoloured, but a creature


def position(builder, hand, *, lilah: bool = True):
    board = ["island"] * 4 + ["mountain"] * 4
    if lilah:
        board = [LILAH, *board]
    return (
        builder(players=2)
        .battlefield(0, board)
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .hand(0, list(hand))
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def settle(game):
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def cast_it(game, card_id: str) -> int:
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    oid = action.source
    game.apply(action)
    settle(game)
    return oid


def to_your_next_turn(game) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn > turn
        and g.state.active_player == 0
        and g.state.step is Step.PRECOMBAT_MAIN,
    )


def castable(game, oid: int) -> bool:
    return any(a.kind is ActionKind.CAST and a.source == oid for a in game.legal_actions())


class TestTheSpellIsExiledInsteadOfBinned:
    def test_it_goes_to_exile(self, builder):
        game = position(builder, [GOLD])
        oid = cast_it(game, GOLD)

        assert game.state.objects[oid].zone is Zone.EXILE

    def test_it_still_resolves_on_the_way(self, builder):
        """"instead of putting it into your graveyard **as it resolves**"."""
        game = position(builder, [GOLD])
        cast_it(game, GOLD)

        assert game.state.players[0].life == 42

    def test_without_lilah_it_is_binned(self, builder):
        """The control."""
        game = position(builder, [GOLD], lilah=False)
        oid = cast_it(game, GOLD)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestOnlyMulticolouredSpells:
    def test_a_mono_coloured_instant_is_binned(self, builder):
        """The card `colors` would have given.

        `{"colors": ["U", "R"]}` is a membership test and matches this spell,
        which is why `min_colors` is a separate clause rather than a spelling of
        that one.
        """
        game = position(builder, [MONO])
        oid = cast_it(game, MONO)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_a_multicoloured_creature_is_not_plotted(self, builder):
        """"instant or sorcery" -- and a creature spell is neither."""
        game = position(builder, [GOLD_CREATURE])
        oid = cast_it(game, GOLD_CREATURE)

        assert game.state.objects[oid].zone is Zone.BATTLEFIELD


class TestNotTheTurnItWasPlotted:
    def test_it_cannot_be_cast_the_same_turn(self, builder):
        """"on a **later** turn" -- the only duration with a start."""
        game = position(builder, [GOLD])
        oid = cast_it(game, GOLD)
        game._advance()

        assert not castable(game, oid)

    def test_and_can_be_on_the_next_one(self, builder):
        game = position(builder, [GOLD])
        oid = cast_it(game, GOLD)
        to_your_next_turn(game)

        assert castable(game, oid)


class TestItCostsNothing:
    def test_it_is_castable_with_no_mana_available(self, builder):
        """"without paying its mana cost."

        Every land is tapped, so the printed {U}{R} is unpayable and the only
        line that can be offered is the free one.
        """
        game = position(builder, [GOLD])
        oid = cast_it(game, GOLD)
        to_your_next_turn(game)
        for land in list(game.state.battlefield):
            game.state.objects[land].tapped = True
        game.state.bump_chars()

        assert castable(game, oid), "a plotted card needs no mana"

    def test_and_casting_it_actually_resolves(self, builder):
        """Offered free and billed the printed cost is a cast that does nothing.

        The bug the `from_library_top` branch in `game._cast` records, which is
        why both sides read the same flag off the same card.
        """
        game = position(builder, [GOLD])
        oid = cast_it(game, GOLD)
        to_your_next_turn(game)
        for land in list(game.state.battlefield):
            game.state.objects[land].tapped = True
        game.state.bump_chars()
        before = game.state.players[0].life
        action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid)
        game.apply(action)
        settle(game)

        assert game.state.players[0].life == before + 2


class TestAsASorcery:
    def test_it_is_not_offered_with_something_on_the_stack(self, builder):
        """"as a sorcery" is a restriction on the **permission**, not the card.

        The plotted card is an instant and its type line still says so, so
        `_timing_ok` alone would happily offer it in response to something.
        """
        # The bait is the mono-coloured instant: castable off these Mountains,
        # and deliberately one Lilah does not plot, so the only thing this test
        # changes is that the stack is no longer empty.
        game = position(builder, [GOLD, MONO])
        oid = cast_it(game, GOLD)
        to_your_next_turn(game)
        assert castable(game, oid), "the premise: it is castable at sorcery speed"

        bait = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == MONO
        )
        game.apply(bait)

        assert not castable(game, oid), "there is something on the stack"


class TestItDoesNotPlotItselfAgain:
    def test_the_plotted_cast_goes_to_the_graveyard(self, builder):
        """The loop guard, and `cast_from_hand`'s second job.

        The plotted card is cast from **exile**, so the rider does not fire for
        it. Without that gate a single multicoloured instant would plot itself
        for ever and never reach a graveyard.
        """
        game = position(builder, [GOLD])
        oid = cast_it(game, GOLD)
        to_your_next_turn(game)
        action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid)
        game.apply(action)
        settle(game)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestItIsNotAnExileOp:
    def test_the_permission_survives_the_move_to_exile(self, builder):
        """Why the rider has to be a rider.

        `move_object` runs `reset_permanent_state` on the way into exile, which
        clears every `playable_*` field. Writing the permission before the move
        -- or writing the exile as an ordinary `exile` op in the ability's
        effects, which runs after the stack list is already popped -- leaves a
        card in exile with nothing on it and a printed line that did nothing.
        """
        game = position(builder, [GOLD])
        oid = cast_it(game, GOLD)
        obj = game.state.objects[oid]

        assert obj.playable_by == 0
        assert obj.playable_duration == "later_turns"
        assert obj.playable_free and obj.playable_sorcery_only
