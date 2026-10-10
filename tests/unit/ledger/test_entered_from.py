"""Celes, Rune Knight — "if one or more of them **entered from a graveyard**".

    Whenever one or more other creatures you control enter, if one or more of
    them entered from a graveyard or was cast from a graveyard, put a +1/+1
    counter on each creature you control.

Two things, and the card needs both.

**The origin zone.** `ENTERS_BATTLEFIELD` carried `cause` and not the zone, and
`cause` names the *mechanism* -- `put_onto_battlefield`, `manifest`, `meld` --
which reaches the battlefield from anywhere. The origin was on the separate
`ZONE_CHANGE` event all along and no trigger maps to that one, so nothing could
reach it. Now the enters event carries `from_zone`, `event_bindings` hands it to
the trigger, and the `entered_from` condition reads it.

Read off the **binding** rather than the object, because by the time the
condition is asked the permanent is on the battlefield and nothing on it
remembers where it came from.

**"One or more … enter" is one firing.** `permanent_enters` fires once per
permanent, so reanimating three creatures put three counters where the card
prints one. `batched` groups them, using the same `state.event_batch` the
leave-the-graveyard trigger already used -- the enters event simply had no batch
stamped on it to group by.

`max_per_turn: 1` is the documented stand-in for this shape and is a different
card: Celes prints no per-turn cap, so a second, separate reanimation later the
same turn should trigger her again.

`t_greedy_celes` is the counterfactual -- the same trigger without `batched` --
and it counts three where the printed card counts one.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Zone
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, plus_one_counters

CELES = "t_celes"
GREEDY = "t_greedy_celes"
BEAR = "t_bear"


def board(builder, card: str, *, count: int, origin: str):
    b = builder(players=2).battlefield(0, [card])
    b = (
        b.graveyard(0, [BEAR] * count)
        if origin == "graveyard"
        else b.hand(0, [BEAR] * count)
    )
    game = b.build(advance=False)
    return game, only_oid(game, card)


def arrive(game, origin: str) -> None:
    """Move them all onto the battlefield as one simultaneous group."""
    state = game.state
    state.event_batch += 1
    source = state.players[0].graveyard if origin == "graveyard" else state.players[0].hand
    for oid in list(source):
        move_object(state, oid, Zone.BATTLEFIELD, to_player=0, cause="test")


def settle(game) -> None:
    game._advance()
    for _ in range(30):
        if not game.state.stack and game.pending() is None:
            return
        actions = game.legal_actions()
        if not actions:
            return
        game.apply(actions[0])


class TestTheOriginZone:
    def test_arriving_from_a_graveyard_triggers(self, builder):
        game, oid = board(builder, CELES, count=1, origin="graveyard")
        arrive(game, "graveyard")
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_arriving_from_hand_does_not(self, builder):
        """The half `cause` could never tell apart: the same mechanism puts a
        permanent onto the battlefield from either zone."""
        game, oid = board(builder, CELES, count=1, origin="hand")
        arrive(game, "hand")
        settle(game)
        assert plus_one_counters(game, oid) == 0


class TestOneOrMore:
    def test_three_reanimated_at_once_is_one_counter(self, builder):
        game, oid = board(builder, CELES, count=3, origin="graveyard")
        arrive(game, "graveyard")
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_without_batched_the_same_arrival_counts_three(self, builder):
        """The counterfactual, and the number the printed card does not say."""
        game, oid = board(builder, GREEDY, count=3, origin="graveyard")
        arrive(game, "graveyard")
        settle(game)
        assert plus_one_counters(game, oid) == 3

    def test_two_separate_arrivals_trigger_twice(self, builder):
        """Not `max_per_turn: 1` -- Celes prints no cap.

        A second, separate reanimation later the same turn is a second "one or
        more … enter", and a per-turn cap would swallow it.
        """
        game, oid = board(builder, CELES, count=2, origin="graveyard")
        state = game.state
        first, second = list(state.players[0].graveyard)

        state.event_batch += 1
        move_object(state, first, Zone.BATTLEFIELD, to_player=0, cause="test")
        settle(game)

        state.event_batch += 1
        move_object(state, second, Zone.BATTLEFIELD, to_player=0, cause="test")
        settle(game)

        assert plus_one_counters(game, oid) == 2
