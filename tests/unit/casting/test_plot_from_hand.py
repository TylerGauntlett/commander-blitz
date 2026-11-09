""""Plot {1}{R} (You may pay {1}{R} and exile this card from your hand. Cast it
as a sorcery on a later turn without paying its mana cost. Plot only as a
sorcery.)"

Lock and Load and Pyretic Charge (Quick Draw) print plot themselves, where Lilah
(`test_plot.py`) grants it to a resolving spell. The gap record asked for a
card-level cost, and it is foretell's special action with the price moved to
the front: the card names what plotting costs, the later cast is free. So it
shares `ActionKind.SUSPEND` -- nothing goes on the stack, nothing can respond
-- and leaves behind exactly the permission `grant_plot` leaves, so a plotted
card is one thing however it was plotted (702.171a).

Two timings, and they are different restrictions. **Plotting** is "only as a
sorcery" whatever the card's type, so an instant with plot may not be plotted
in response to anything (`TestPlottingIsSorcerySpeed`). **Casting** the plotted
card is "as a sorcery" too, which is the permission's own
`playable_sorcery_only` rather than the type line (`TestTheLaterCast`).
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step, Zone
from tests.conftest import pass_until, settle_to_priority

BOLT = "t_plotter"  # {3}{R}{R} instant, plot {1}{R}, 3 damage to any target
BEAR = "t_plotted_bear"  # {3}{G} 2/2, plot {G}


def position(builder, hand, *, lands=("mountain", "mountain")):
    return (
        builder(players=2)
        .battlefield(0, list(lands))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def plot_action(game, oid: int):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.SUSPEND and a.source == oid),
        None,
    )


def plotted(builder, hand=(BOLT,), **kw):
    game = position(builder, hand, **kw)
    game._advance()
    oid = game.state.players[0].hand[0]
    game.apply(plot_action(game, oid))
    settle_to_priority(game)
    return game, oid


def to_your_next_turn(game) -> None:
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.turn > turn
        and g.state.active_player == 0
        and g.state.step is Step.PRECOMBAT_MAIN
        and (d := g.pending()) is not None
        and d.player == 0,
    )


def cast_lines(game, oid: int):
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


class TestTheSpecialAction:
    def test_it_is_offered_from_hand(self, builder):
        game = position(builder, [BOLT])
        game._advance()
        oid = game.state.players[0].hand[0]

        action = plot_action(game, oid)
        assert action is not None and action.label.startswith("Plot ")

    def test_it_is_not_offered_without_the_price(self, builder):
        """The plot cost is the card's: {1}{R} off one Mountain is unpayable."""
        game = position(builder, [BOLT], lands=("mountain",))
        game._advance()

        assert plot_action(game, game.state.players[0].hand[0]) is None

    def test_it_pays_the_price_and_exiles_the_card(self, builder):
        game, oid = plotted(builder)

        assert game.state.objects[oid].zone is Zone.EXILE
        assert all(game.state.objects[m].tapped for m in game.state.battlefield)

    def test_it_uses_the_stack_for_nothing(self, builder):
        game, _ = plotted(builder)

        assert game.state.stack == []

    def test_it_is_exiled_face_up(self, builder):
        """Unlike foretell: nothing is hidden, so `revealed_to` stays empty."""
        game, oid = plotted(builder)

        assert not game.state.objects[oid].revealed_to

    def test_it_leaves_the_permission_grant_plot_leaves(self, builder):
        game, oid = plotted(builder)
        obj = game.state.objects[oid]

        assert obj.playable_by == 0
        assert obj.playable_duration == "later_turns"
        assert obj.playable_free and obj.playable_sorcery_only

    def test_a_card_without_plot_offers_none(self, builder):
        """The control: a plain Mountain in hand has no special action."""
        game = position(builder, ["mountain"])
        game._advance()

        assert plot_action(game, game.state.players[0].hand[0]) is None


class TestPlottingIsSorcerySpeed:
    def test_an_instant_is_not_plotted_on_an_opponents_turn(self, builder):
        """"Plot only as a sorcery" -- the type line says instant, and it does
        not matter."""
        game = position(builder, [BOLT])
        game._advance()
        oid = game.state.players[0].hand[0]
        pass_until(
            game,
            lambda g: g.state.active_player == 1
            and (d := g.pending()) is not None
            and d.player == 0,
        )

        assert plot_action(game, oid) is None


class TestTheLaterCast:
    def test_it_cannot_be_cast_the_turn_it_was_plotted(self, builder):
        game, oid = plotted(builder, lands=["mountain"] * 7)

        assert cast_lines(game, oid) == []

    def test_it_is_cast_free_on_a_later_turn(self, builder):
        """Every land tapped: the printed {3}{R}{R} is unpayable, the free line
        is not."""
        game, oid = plotted(builder)
        to_your_next_turn(game)
        for land in list(game.state.battlefield):
            game.state.objects[land].tapped = True
        game.state.bump_chars()

        lines = cast_lines(game, oid)
        assert lines, "a plotted card needs no mana"

        target = next(a for a in lines if any(t.kind == "player" and t.id == 1 for t in a.targets))
        life = game.state.players[1].life
        game.apply(target)
        settle_to_priority(game)

        assert game.state.players[1].life == life - 3
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_a_plotted_creature_enters_the_battlefield(self, builder):
        game, oid = plotted(builder, hand=(BEAR,), lands=("forest",))
        to_your_next_turn(game)
        (line,) = cast_lines(game, oid)
        game.apply(line)
        settle_to_priority(game)

        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
