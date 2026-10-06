"""Foretell — suspend's special action with a price on the later cast.

    "Foretell {R} (During your turn, you may pay {2} and exile this card from
    your hand face down. Cast it on a later turn for its foretell cost.)"

The census filed this as blocked: "a special action putting a card in exile to
be cast later; suspend is the nearest shape". Suspend was not merely the nearest
shape — it is the *same* shape, and foretell shares its `ActionKind`. Both exile
a card from hand to be cast later, neither uses the stack, and neither can be
countered. What differs is only the ticking rule and whether the later cast
costs anything.

**"Face down" here is `revealed_to`**, the engine's existing channel for
information one seat holds and the others do not. That is a much smaller claim
than a face-down *permanent*: a card in exile that nobody may interact with is
hidden by simply not being shown, where a face-down creature is a 2/2 shell over
a real card and a characteristics problem. Foretell needs only the first, which
is why it ships and morph does not.

**"On a later turn" is the whole price.** A card foretold and cast on the same
turn is the printed cost paid in two instalments with the discount thrown in, so
`foretold_turn` is recorded and `foretold_cards` compares it.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import pass_until

MOUNTAIN = "mountain"
BOLT = "t_foreteller"      # {2}{R}, foretell {R}


def position(builder, lands: int = 2):
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * lands)
        .hand(0, [BOLT])
        .library(0, [MOUNTAIN] * 20)
        .library(1, [MOUNTAIN] * 20)
        .build()
    )


def to_my_main(game, turn: int):
    pass_until(
        game,
        lambda g: (
            g.state.turn >= turn
            and g.state.step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN)
            and (d := g.pending()) is not None
            and d.player == 0
        ),
    )


def foretell_action(game):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.SUSPEND), None
    )


def cast_lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == BOLT
    ]


class TestTheSpecialAction:
    def test_it_is_offered_on_your_turn(self, builder):
        game = position(builder)
        to_my_main(game, 3)
        assert foretell_action(game) is not None

    def test_it_is_not_offered_without_the_two(self, builder):
        """The {2} is fixed by 702.143a, not by the card."""
        game = position(builder, lands=1)
        to_my_main(game, 3)
        assert foretell_action(game) is None

    def test_it_exiles_the_card(self, builder):
        game = position(builder)
        to_my_main(game, 3)
        bolt = game.state.players[0].hand[0]

        game.apply(foretell_action(game))

        assert game.state.objects[bolt].zone is Zone.EXILE
        assert game.state.objects[bolt].foretold_by == 0

    def test_only_its_controller_may_see_it(self, builder):
        """"Face down" is `revealed_to` -- one seat, and no characteristics."""
        game = position(builder)
        to_my_main(game, 3)
        bolt = game.state.players[0].hand[0]

        game.apply(foretell_action(game))

        assert game.state.objects[bolt].revealed_to == {0}

    def test_it_uses_the_stack_for_nothing(self, builder):
        """A special action: nothing to respond to, and it cannot be countered."""
        game = position(builder)
        to_my_main(game, 3)

        game.apply(foretell_action(game))

        assert game.state.stack == []


class TestTheLaterCast:
    def _foretold(self, builder, lands: int = 3):
        game = position(builder, lands=lands)
        to_my_main(game, 3)
        bolt = game.state.players[0].hand[0]
        game.apply(foretell_action(game))
        return game, bolt

    def test_it_cannot_be_cast_the_same_turn(self, builder):
        """Otherwise foretell is the printed cost in instalments, discounted."""
        game, _ = self._foretold(builder, lands=6)
        assert cast_lines(game) == []

    def test_it_can_be_cast_on_a_later_turn(self, builder):
        game, _ = self._foretold(builder)
        to_my_main(game, 5)

        assert any(a.foretold for a in cast_lines(game))

    def test_it_is_cast_for_the_foretell_cost(self, builder):
        """One Mountain untapped: {R} is payable, the printed {2}{R} is not."""
        game, _bolt = self._foretold(builder, lands=3)
        to_my_main(game, 5)
        for obj in game.state.battlefield_objects(0):
            obj.tapped = True
        # Leave exactly one source of red.
        next(iter(game.state.battlefield_objects(0))).tapped = False
        game.state.bump_chars()

        assert any(a.foretold for a in cast_lines(game))

    def test_casting_it_resolves_the_spell(self, builder):
        game, bolt = self._foretold(builder)
        to_my_main(game, 5)
        action = next(
            a
            for a in cast_lines(game)
            if a.foretold
            and any(t.kind == "player" and t.id == 1 for t in a.targets)
        )
        life = game.state.players[1].life
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.players[1].life == life - 3
        assert game.state.objects[bolt].zone is Zone.GRAVEYARD

    def test_an_unforetold_copy_is_unaffected(self, builder):
        """Nothing in exile is castable unless it was foretold by that player."""
        game = position(builder)
        to_my_main(game, 3)
        bolt = game.state.players[0].hand[0]
        from automtg.engine.zones import exile

        exile(game.state, bolt)
        to_my_main(game, 5)

        assert cast_lines(game) == []
