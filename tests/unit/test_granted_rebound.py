""""Whenever you cast an instant spell from your hand, **it gains rebound**."

Ojer Pakpatiq, Deepest Epoch. Rebound (702.87a) was never the missing part --
the mechanic has been complete for as long as `CardDef.rebound` has existed:
the resolution rider that exiles the spell instead of binning it, `rebound_by`
recorded on the exiled card, and `suspend.rebound_tick` making the free cast at
its controller's next upkeep. What could not be said was somebody *else*
granting it, because the rider read the flag off the **card**, and a card either
prints rebound or it does not.

So `granted_rebound` sits on the spell's object beside `card.rebound`, exactly
as `playable_exiles` already sits beside `card.graveyard_cast_exiles`: one is
what a spell says about itself, the other is what somebody said about it, and
the rider cannot tell the difference. `TestPrintedReboundIsUnchanged` is the
control that keeps the two honest -- a passing grant test could otherwise be
explained by the bait card having had rebound all along.

Two boundaries, and they are the same boundary read twice. The rider is gated on
`cast_from_hand`, which is 702.87a's own wording *and* the loop guard: the free
cast at the next upkeep is made from **exile**, so without that gate a single
instant would rebound every upkeep for the rest of the game.
`TestItDoesNotReboundTwice` is that claim, and it is the reason the grant is left
deliberately inert -- rather than refused -- on a spell cast from anywhere but a
hand.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from tests.conftest import pass_until

GRANTER = "t_rebound_granter"  # "...it gains rebound."
BAIT = "t_reb_gain"  # {R} instant, gain 2 life -- prints no rebound
BAIT_SORCERY = "t_reb_gain_sorcery"  # the same card as a sorcery
PRINTED = "t_printed_rebound"  # {R} instant that prints rebound, and draws


def position(builder, *, granter: bool, spell: str):
    board = ["mountain"] * 4
    if granter:
        board = [GRANTER, *board]
    return (
        builder(players=2)
        .battlefield(0, board)
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [spell])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def cast_it(game, card_id: str) -> int:
    """Cast ``card_id`` from hand and let it resolve. Returns its oid."""
    game._advance()
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    oid = action.source
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )
    return oid


def to_your_next_upkeep(game) -> None:
    """Pass to seat 0's *next* upkeep and let what happens there resolve.

    Two waits, not one. `rebound_tick` runs as the upkeep begins and puts the
    card on the **stack**; stopping at the step itself reads the spell mid-cast,
    which looks exactly like a rebound that resolved and did nothing.
    """
    turn = game.state.turn
    pass_until(
        game,
        lambda g: g.state.step is Step.UPKEEP
        and g.state.active_player == 0
        and g.state.turn > turn,
    )
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


class TestTheGrantRedirectsTheSpell:
    def test_it_is_exiled_instead_of_binned(self, builder):
        """The half the rider does: "exile it as it resolves"."""
        game = position(builder, granter=True, spell=BAIT)
        oid = cast_it(game, BAIT)

        assert game.state.objects[oid].zone is Zone.EXILE

    def test_the_spell_still_resolves_on_the_way(self, builder):
        """Rebound is not a counter. The gain happens, then the exile."""
        game = position(builder, granter=True, spell=BAIT)
        cast_it(game, BAIT)

        assert game.state.players[0].life == 42


class TestWithoutTheGrant:
    def test_the_same_instant_goes_to_the_graveyard(self, builder):
        """The control. Without it there is nothing to attribute the rest to."""
        game = position(builder, granter=False, spell=BAIT)
        oid = cast_it(game, BAIT)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_and_is_never_cast_again(self, builder):
        game = position(builder, granter=False, spell=BAIT)
        cast_it(game, BAIT)
        to_your_next_upkeep(game)

        assert game.state.players[0].life == 42, "gained once, not twice"


class TestTheFreeCastAtYourNextUpkeep:
    def test_the_spell_is_cast_again(self, builder):
        """The other half: 2 life on the cast, 2 more at the upkeep."""
        game = position(builder, granter=True, spell=BAIT)
        cast_it(game, BAIT)
        to_your_next_upkeep(game)

        assert game.state.players[0].life == 44

    def test_it_does_not_happen_on_the_opponents_upkeep(self, builder):
        """"your next upkeep" -- seat 1's comes first and is not it."""
        game = position(builder, granter=True, spell=BAIT)
        cast_it(game, BAIT)
        pass_until(
            game,
            lambda g: g.state.step is Step.UPKEEP and g.state.active_player == 1,
        )

        assert game.state.players[0].life == 42


class TestItDoesNotReboundTwice:
    def test_the_rebounded_cast_is_binned(self, builder):
        """The loop guard, and the reason `cast_from_hand` is in the rider.

        The free cast is made from **exile**, so the rider does not fire for it
        and the card finally reaches the graveyard. Without the gate this card
        would rebound at every upkeep for the rest of the game.
        """
        game = position(builder, granter=True, spell=BAIT)
        oid = cast_it(game, BAIT)
        to_your_next_upkeep(game)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_and_gains_no_life_a_third_time(self, builder):
        game = position(builder, granter=True, spell=BAIT)
        cast_it(game, BAIT)
        to_your_next_upkeep(game)
        turn = game.state.turn
        pass_until(
            game,
            lambda g: g.state.step is Step.UPKEEP
            and g.state.active_player == 0
            and g.state.turn > turn,
        )

        assert game.state.players[0].life == 44, "twice, not three times"


class TestOnlyWhatTheTriggerNamed:
    def test_a_sorcery_is_not_granted(self, builder):
        """The granter says "an **instant** spell", and the filter is what says so."""
        game = position(builder, granter=True, spell=BAIT_SORCERY)
        oid = cast_it(game, BAIT_SORCERY)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD


class TestPrintedReboundIsUnchanged:
    def test_a_card_that_prints_it_still_rebounds(self, builder):
        """The regression the disjunction could have broken.

        `card.rebound or obj.granted_rebound` has to keep meaning what
        `card.rebound` alone meant, with no granter anywhere on the board.
        """
        game = position(builder, granter=False, spell=PRINTED)
        oid = cast_it(game, PRINTED)

        assert game.state.objects[oid].zone is Zone.EXILE

    def test_and_is_recast_at_the_next_upkeep(self, builder):
        game = position(builder, granter=False, spell=PRINTED)
        before = len(game.state.players[0].library)
        cast_it(game, PRINTED)
        to_your_next_upkeep(game)

        # One card for the cast, one for the rebound, one for the draw step of
        # the turn in between -- the seat that drew is seat 1, not this one.
        assert len(game.state.players[0].library) == before - 2
