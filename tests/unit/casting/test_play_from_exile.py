""""Exile one of those cards … You may play the exiled card this turn."

    Florian, Voldaren Scion — the impulse-draw pattern.

`play_exiled` already existed and is a different thing: it is hideaway's
permission, it casts the card **for free**, and it does it there and then as the
ability resolves. Florian grants permission to play the card *later*, at the
printed price, and only until the turn ends.

So the permission is recorded on the exiled object -- who may play it and on
which turn. Both halves, because it expires: a bare boolean would leave the card
castable out of exile for the rest of the game, which is a strictly better card
and a silent one.

Modelled on the Adventure block in `_cast_actions`, which already widens "where
a card may be cast from" to exile for a flagged object. The turn is the only
thing this adds.

**Both halves of "play".** A land is played rather than cast, so the permission
reaches `_land_actions` too -- without that, Florian exiling a land would grant
a permission that silently did nothing.
"""

from __future__ import annotations

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, Zone
from tests.conftest import action_for_card

BEAR = "t_bear"
LAND = "forest"  # the test bear is {1}{G}


def exile_it(game, card_id: str, *, playable: bool = True) -> int:
    """Exile a card from hand, optionally with the play permission."""
    oid = next(
        o.oid
        for o in game.state.objects.values()
        if o.zone is Zone.HAND and o.def_id == card_id
    )
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    spec = {"op": "exile", "objects": {"zone": "hand", "controller": "you", "count": "all"}}
    if playable:
        spec["playable_this_turn"] = True
    for _ in execute(ctx, [spec]):
        raise AssertionError("this exile asks nothing")
    return oid


def board(builder, hand):
    return (
        builder(players=2)
        .battlefield(0, [LAND] * 5)
        .hand(0, list(hand))
        .library(0, [LAND] * 20)
        .active(0)
        .max_turns(4)
        .build()
    )


def playable_from_exile(game, oid: int) -> bool:
    return any(
        a.source == oid
        and a.kind in (ActionKind.CAST, ActionKind.PLAY_LAND)
        for a in game.legal_actions()
    )


class TestTheSpellHalf:
    def test_it_is_castable_from_exile(self, builder):
        game = board(builder, [BEAR])
        oid = exile_it(game, BEAR)
        assert game.state.objects[oid].zone is Zone.EXILE
        assert playable_from_exile(game, oid)

    def test_without_the_permission_it_is_not(self, builder):
        game = board(builder, [BEAR])
        oid = exile_it(game, BEAR, playable=False)
        assert not playable_from_exile(game, oid)

    def test_the_cost_is_still_owed(self, builder):
        """The whole difference from `play_exiled`, which casts for free."""
        game = (
            builder(players=2)
            .battlefield(0, [LAND])  # a Bear costs {1}{G}; one land cannot pay
            .hand(0, [BEAR])
            .library(0, [LAND] * 20)
            .active(0)
            .build()
        )
        oid = exile_it(game, BEAR)
        assert not playable_from_exile(game, oid)

    def test_it_expires_with_the_turn(self, builder):
        game = board(builder, [BEAR])
        oid = exile_it(game, BEAR)
        assert playable_from_exile(game, oid)

        game.state.turn += 1  # what the next untap step brings

        assert not playable_from_exile(game, oid)

    def test_an_opponent_may_not_play_it(self, builder):
        game = board(builder, [BEAR])
        oid = exile_it(game, BEAR)
        game.state.objects[oid].playable_by = 1
        assert not playable_from_exile(game, oid)


class TestTheLandHalf:
    def test_a_land_is_offered_as_a_land_drop(self, builder):
        """"Play" covers a land, which is played rather than cast."""
        game = board(builder, ["forest"])
        oid = exile_it(game, "forest")
        assert any(
            a.kind is ActionKind.PLAY_LAND and a.source == oid
            for a in game.legal_actions()
        )

    def test_it_still_costs_the_land_drop(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [LAND] * 5)
            .hand(0, ["forest"])
            .library(0, [LAND] * 20)
            .active(0)
            .lands_played(0, 1)
            .build()
        )
        oid = exile_it(game, "forest")
        assert not playable_from_exile(game, oid)


class TestItActuallyResolves:
    def test_the_bear_arrives_on_the_battlefield(self, builder):
        """Being offered is not the same as working. Cast it and look."""
        game = board(builder, [BEAR])
        oid = exile_it(game, BEAR)

        game.apply(action_for_card(game, ActionKind.CAST, BEAR))
        while game.state.stack:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.PASS
                )
            )

        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert game.state.objects[oid].controller == 0

    def test_the_permission_does_not_follow_it_back(self, builder):
        """It resolved from exile; if it is exiled again later, that is a new
        permission and not this one. `reset_permanent_state` clears both fields
        on every zone change, so the flag cannot ride a card around the game."""
        game = board(builder, [BEAR])
        oid = exile_it(game, BEAR)
        game.apply(action_for_card(game, ActionKind.CAST, BEAR))

        assert game.state.objects[oid].playable_by is None


class TestLookAtTopGrantsItToo:
    """Florian exiles from inside `look_at_top`, never from a bare `exile`."""

    def test_the_card_it_exiles_is_playable(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [LAND] * 5)
            .hand(0, [LAND])
            .library(0, [BEAR] + [LAND] * 20)
            .active(0)
            .max_turns(4)
            .build()
        )
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        spec = {
            "op": "look_at_top",
            "player": "you",
            "amount": {"const": 1},
            "objects": {"count": 1},
            "destination": "exile",
            "rest_to_bottom": True,
            "playable_this_turn": True,
        }
        gen, send = execute(ctx, [spec]), None
        while True:
            try:
                decision = gen.send(send)
            except StopIteration:
                break
            send = list(range(decision.max_count or 1))  # take the first card

        oid = next(
            o.oid
            for o in game.state.objects.values()
            if o.zone is Zone.EXILE and o.def_id == BEAR
        )
        assert playable_from_exile(game, oid)
