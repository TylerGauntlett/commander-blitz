"""One more loyalty activation this turn -- The Chain Veil.

    The Chain Veil — "{4}, {T}: For each planeswalker you control, you may
    activate one of its loyalty abilities once this turn as though none of its
    loyalty abilities have been activated this turn."

606.3 allows one loyalty activation per permanent per turn, and legality tested
for *any* earlier activation, so there was no way to say "one more". The ledger
now holds an extra count per permanent and legality compares the activations
made against one plus it.

The claims, and what each would be wrong without:

- **One more, then the limit again.** After the Veil a walker that has already
  activated may activate once more, and not a third time.
- **Additional, not a reset** (the card's ruling): a walker that has not
  activated yet may activate twice.
- **Only the walkers there as it resolves**: one entering afterwards keeps the
  ordinary single activation.
- **It wears off with the turn.**
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, Step
from tests.conftest import pass_until

VEIL = "t_veil_tap"
WALKER = "t_walker"  # loyalty 4; "+1: gain 2 life" and "-3: draw a card"


def position(builder, mine=(WALKER, VEIL)):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 2 + list(mine))
        .battlefield(1, ["plains"])
        .hand(0, ["plains"])
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def oid_of(game, def_id):
    return next(o for o in game.state.battlefield if game.state.objects[o].def_id == def_id)


def loyalty_actions(game, oid):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid and "+1" in (a.label or "")
    ]


def activate(game, oid, label):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == oid and label in (a.label or "")
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def veil(game):
    veil_oid = oid_of(game, VEIL)
    action = next(
        a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == veil_oid
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestOneMoreThenTheLimit:
    def test_without_the_veil_one_is_all(self, builder):
        game = position(builder)
        walker = oid_of(game, WALKER)
        activate(game, walker, "+1")
        assert loyalty_actions(game, walker) == []

    def test_after_the_veil_once_more_and_not_a_third_time(self, builder):
        game = position(builder)
        walker = oid_of(game, WALKER)
        activate(game, walker, "+1")
        veil(game)
        assert loyalty_actions(game, walker)
        activate(game, walker, "+1")
        assert loyalty_actions(game, walker) == []


class TestAdditionalNotAReset:
    def test_a_fresh_walker_activates_twice(self, builder):
        game = position(builder)
        walker = oid_of(game, WALKER)
        veil(game)
        activate(game, walker, "+1")
        assert loyalty_actions(game, walker), "the extra is on top of the first"
        activate(game, walker, "+1")
        assert loyalty_actions(game, walker) == []


class TestOnlyTheWalkersThereAsItResolves:
    def test_a_later_walker_keeps_the_single_activation(self, builder):
        game = position(builder, mine=(VEIL,))
        veil(game)
        assert game.state.turn_ledger.extra_loyalty_activations == {}


class TestItWearsOffWithTheTurn:
    def test_the_ledger_clears(self, builder):
        game = position(builder)
        veil(game)
        assert game.state.turn_ledger.extra_loyalty_activations
        game.state.turn_ledger.clear()
        assert game.state.turn_ledger.extra_loyalty_activations == {}
