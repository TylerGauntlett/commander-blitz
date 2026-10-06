"""Locke, Treasure Hunter — milling, then casting one of what you milled.

    Mug — Whenever Locke attacks, each player mills a card. If a land card was
    milled this way, create a Treasure token. Until end of turn, you may cast a
    spell from among those cards.

Three separate things, and the card needs all of them.

**`mill` records what it moved.** It took only `amount` and `player` and threw
away the oid list `mill_cards` returns, so nothing downstream could name the
cards. `exists` over a graveyard selector is a *different card*: it matches a
land that was already lying in somebody's yard, so Locke would make a Treasure
on every attack whatever the mill turned up. The binding accumulates across the
players one op touched, because "each player mills a card" is one op.

**`grant_playable` leaves a standing permission where the cards already are.**
Every neighbouring op is wrong: `play_exiled` casts one card there and then, for
free, out of exile; `exile`'s `playable_this_turn` grants the same permission
but only to cards it has just exiled. Locke's cards stay in their owners'
graveyards -- including an opponent's, which is why legality now walks every
graveyard for the flag -- and are paid for at their printed price.

**"a spell", singular.** Out of however many were milled, and with no cap the
permission would let you cast all of them. Counted per granting permanent in the
turn ledger, the same slot a `cast_from_graveyard` permission bills.
"""

from __future__ import annotations

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind

LOCKE = "t_locke"


def mug(builder, *, my_top: str, their_top: str):
    """Put Locke on the board and run its ability directly.

    Directly, because the printed trigger is on *attacking* and the sandbox
    declines combat -- this is about what the ability does, not about when.
    """
    game = (
        builder(players=2)
        .battlefield(0, [LOCKE])
        .battlefield(0, ["mountain"] * 4)
        .hand(0, ["plains"])
        .library(0, [my_top] + ["forest"] * 8)
        .library(1, [their_top] + ["island"] * 8)
        .build()
    )
    state = game.state
    source = next(
        o.oid for o in state.battlefield_objects(0) if state.card_of(o).id == LOCKE
    )
    ctx = EffectContext(state=state, controller=0, source_oid=source)
    gen = execute(ctx, state.card_of(state.objects[source]).abilities[0].effects)
    try:
        while True:
            next(gen)
    except StopIteration:
        pass
    return game


def tokens(game):
    state = game.state
    return [
        state.card_of(o).id
        for o in state.battlefield_objects(0)
        if state.card_of(o).is_token
    ]


def castable(game):
    """Distinct *cards* on offer, not target permutations of them."""
    return {a.source for a in game.legal_actions() if a.kind is ActionKind.CAST}


def resolve_one(game):
    action = next(a for a in game.legal_actions() if a.kind is ActionKind.CAST)
    game.apply(action)
    state = game.state
    for _ in range(15):
        if not state.stack:
            break
        actions = game.legal_actions()
        if not actions:
            break
        game.apply(actions[0])
    return game


class TestTheMillBinding:
    def test_a_milled_land_makes_a_treasure(self, builder):
        game = mug(builder, my_top="forest", their_top="t_bolt")
        assert tokens(game) == ["treasure_token"]

    def test_no_milled_land_makes_none(self, builder):
        game = mug(builder, my_top="t_bolt", their_top="t_bolt")
        assert tokens(game) == []

    def test_a_land_milled_from_an_opponent_counts(self, builder):
        """"each player mills a card" -- the binding accumulates across seats."""
        game = mug(builder, my_top="t_bolt", their_top="island")
        assert tokens(game) == ["treasure_token"]

    def test_a_land_already_in_a_graveyard_does_not(self, builder):
        """The near miss: `exists` over a graveyard is a different card.

        A Forest sitting in the yard from an earlier turn is not a land milled
        *this way*, and Locke would otherwise make a Treasure every attack.
        """
        game = (
            builder(players=2)
            .battlefield(0, [LOCKE])
            .battlefield(0, ["mountain"] * 4)
            .graveyard(0, ["forest"])
            .hand(0, ["plains"])
            .library(0, ["t_bolt"] + ["forest"] * 8)
            .library(1, ["t_bolt"] + ["island"] * 8)
            .build()
        )
        state = game.state
        source = next(
            o.oid for o in state.battlefield_objects(0) if state.card_of(o).id == LOCKE
        )
        ctx = EffectContext(state=state, controller=0, source_oid=source)
        gen = execute(ctx, state.card_of(state.objects[source]).abilities[0].effects)
        try:
            while True:
                next(gen)
        except StopIteration:
            pass
        assert tokens(game) == []


class TestThePermission:
    def test_both_milled_cards_are_castable(self, builder):
        """Including the one out of the **opponent's** graveyard."""
        game = mug(builder, my_top="t_bolt", their_top="t_bolt")
        assert len(castable(game)) == 2

    def test_they_stay_in_their_graveyards(self, builder):
        """A standing permission, not a move: nothing was exiled."""
        game = mug(builder, my_top="t_bolt", their_top="t_bolt")
        state = game.state
        assert len(state.players[0].graveyard) == 1
        assert len(state.players[1].graveyard) == 1


class TestOnlyOneSpell:
    def test_the_permission_is_spent_by_the_first_cast(self, builder):
        """"you may cast **a spell** from among those cards", singular."""
        game = mug(builder, my_top="t_bolt", their_top="t_bolt")
        assert len(castable(game)) == 2
        resolve_one(game)
        assert castable(game) == set()
