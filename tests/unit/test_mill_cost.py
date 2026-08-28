"""Milling as a *cost*, and why it cannot be an effect.

"{T}, Mill a card: Add {C}" -- Millikin, Deranged Assistant, The Warring Triad.

Rule 601.2h/602.2b: costs are paid as the ability is put on the stack. Writing
the mill into the ability's `effects` instead moves it to resolution, and the
gap between those two moments is observable: the ability could be activated and
responded to with the cards still on top of the library. The Warring Triad is
the card that makes it undeniable, because its *other* ability counts the cards
in the very graveyard this cost fills. On Millikin it is not merely wrong but
unwritable -- a mana ability may contain only `add_mana`, so a `mill` op cannot
legally appear in its effects at all.

The second claim here is a rules boundary that goes the other way from the
obvious guess. **Mill as a cost is payable with an empty library.** 701.13b:
"If a player is instructed to mill a number of cards greater than the number of
cards in their library, that player mills their entire library." Milling more
than you have is a legal action that mills fewer, so the cost can always be
paid. Discarding has no such rule, which is why an empty hand *does* make a
`discard` cost unpayable -- and that asymmetry is asserted below, because both
gap records that asked for this capability assumed the strict reading.

The third is a trap specific to mana abilities: `costs.solver_taps` reads
`Cost.is_tap_only()` to decide which abilities the payment solver may tap on its
own, without asking anybody. A mill cost that did not disqualify an ability
there would let the solver take the {C} and never mill -- a strictly better
Millikin, silently.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind
from tests.conftest import only_oid


def rock(builder, card_id: str, *, library: int = 20):
    """The rock on the battlefield, and a land in hand.

    The land is not decoration. `build()` runs the engine's auto-pass, and a
    player whose only available action is a *mana* ability has nothing worth
    stopping for -- correctly, or every land on every board would halt the game
    -- so priority would sail past player 0 and the ability would never be
    offered. A land in hand is the cheapest real decision that keeps the
    position where the assertions can see it.
    """
    game = (
        builder(players=2)
        .battlefield(0, [card_id])
        .hand(0, ["forest"])
        .library(0, ["forest"] * library)
        .build()
    )
    return game, only_oid(game, card_id)


def activate(game, oid: int):
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
    )
    game.apply(action)
    return game


def can_activate(game, oid: int) -> bool:
    return any(
        a.kind is ActionKind.ACTIVATE and a.source == oid for a in game.legal_actions()
    )


def graveyard(game, pid: int = 0) -> int:
    return len(game.state.players[pid].graveyard)


def library(game, pid: int = 0) -> int:
    return len(game.state.players[pid].library)


class TestTheCostIsPaidOnActivation:
    def test_activating_mills(self, builder):
        game, oid = rock(builder, "t_mill_rock")
        assert (library(game), graveyard(game)) == (20, 0)
        activate(game, oid)
        assert (library(game), graveyard(game)) == (19, 1)

    def test_it_mills_exactly_what_the_cost_says(self, builder):
        game, oid = rock(builder, "t_mill_two_rock")
        activate(game, oid)
        assert (library(game), graveyard(game)) == (18, 2)

    def test_the_card_milled_is_the_top_one(self, builder):
        """Off the top, so there is nothing to choose and nobody to ask."""
        game, oid = rock(builder, "t_mill_rock")
        top = game.state.players[0].library[0]
        activate(game, oid)
        assert game.state.players[0].graveyard[-1] == top

    def test_the_mana_still_arrives(self, builder):
        """The cost is charged, but the ability is not thereby broken."""
        game, oid = rock(builder, "t_mill_rock")
        activate(game, oid)
        assert game.state.players[0].mana_pool.total() >= 1


class TestTheEmptyLibraryBoundary:
    """701.13b, and the asymmetry with discard that it creates."""

    def test_an_empty_library_does_not_forbid_activation(self, builder):
        game, oid = rock(builder, "t_mill_rock", library=0)
        assert can_activate(game, oid)

    def test_and_it_mills_nothing_rather_than_erroring(self, builder):
        game, oid = rock(builder, "t_mill_rock", library=0)
        activate(game, oid)
        assert (library(game), graveyard(game)) == (0, 0)

    def test_a_short_library_mills_what_is_there(self, builder):
        """"Mill two" with one card left mills the one, per 701.13b."""
        game, oid = rock(builder, "t_mill_two_rock", library=1)
        activate(game, oid)
        assert (library(game), graveyard(game)) == (0, 1)


class TestTheSolverMustNotTapItForFree:
    """`is_tap_only` is what keeps the payment solver's hands off this."""

    def test_a_mill_cost_is_not_tap_only(self, builder):
        game, oid = rock(builder, "t_mill_rock")
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert not cost.is_tap_only()

    def test_the_same_rock_without_the_mill_is(self, builder):
        """The counterfactual: nothing else about the two cards differs."""
        game, oid = rock(builder, "t_plain_rock")
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert cost.is_tap_only()

    def test_the_solver_declines_it_and_offers_it_instead(self, builder):
        """`solver_taps` and `offerable_mana_ability` are complements.

        An ability neither claims can never be activated at all; one they both
        claim could be spent twice. So the mill rock must land in exactly one.
        """
        from automtg.engine.costs import offerable_mana_ability, solver_taps

        game, oid = rock(builder, "t_mill_rock")
        ability = game.state.card_of(game.state.objects[oid]).abilities[0]
        assert not solver_taps(ability)
        assert offerable_mana_ability(ability)

    def test_paying_a_generic_cost_never_mills_behind_your_back(self, builder):
        """The whole point: the solver may not spend this rock silently.

        If it could, a player casting anything would find cards in their
        graveyard they never agreed to put there.
        """
        game, _ = rock(builder, "t_mill_rock")
        before = graveyard(game)
        game.legal_actions()
        assert graveyard(game) == before


class TestTheCostDescribesItself:
    def test_describe_names_the_mill(self, builder):
        game, oid = rock(builder, "t_mill_rock")
        cost = game.state.card_of(game.state.objects[oid]).abilities[0].cost
        assert "Mill 1" in cost.describe()
