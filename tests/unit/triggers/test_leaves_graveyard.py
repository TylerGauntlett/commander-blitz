"""Spirit Mascot — "Whenever one or more cards leave your graveyard…".

Two separate things were missing, and only one of them is the event.

**Nothing watched the graveyard as a source zone.** `trigger_events` carried
`leaves_battlefield`, `dies` and `sacrificed` — all about a permanent leaving
play, and all of which fire when a card *arrives* in a graveyard rather than
when it departs. So every way a card leaves one — reanimation, an exile cost,
graveyard hate, a cast from the yard, a shuffle-back — happened unobserved.
`exile_from_graveyard` is a cost and `return_from_graveyard` is an op: hanging
the counter off either would only ever cover the Mascot controller's *own*
effects, never an opponent's Bojuka Bog.

`ZONE_CHANGE` already records every move and is deliberately **not** on the
trigger bus — routing it through `fire` would run the trigger scan on every
draw, discard, shuffle and land drop in the game. So `LEAVES_GRAVEYARD` is
fired narrowly from `zones.move_object` instead, and nothing else pays for it.

**"One or more" is the second thing, and it is not cosmetic.** Cards move one at
a time, so the event fires once per card. Rise of the Dark Realms emptying a
five-card graveyard would put *five* counters on the Mascot. `batched` says the
ability fires once per simultaneous group, where a group is one effect op or one
cost payment — the two places an effect moves several cards at once.

It is deliberately not `max_per_turn: 1`, which the codebase already documents
as the stand-in for this shape and which is a different card: a printed "one or
more" fires again later the same turn for a second, separate departure, and a
per-turn cap does not. That difference is asserted below.

`t_greedy_mascot` is the counterfactual — the same trigger without `batched` —
so the batching claim is measured against the card that lacks it rather than
against a number in a comment.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, plus_one_counters

MASCOT = "t_mascot"
GREEDY = "t_greedy_mascot"
BEAR = "t_bear"


def board(builder, mascot: str, *, buried: int = 1):
    game = (
        builder(players=2)
        .battlefield(0, [mascot])
        .graveyard(0, [BEAR] * buried)
        .graveyard(1, [BEAR])
        .build(advance=False)
    )
    return game, only_oid(game, mascot)


def settle(game) -> None:
    """Let the queued triggers resolve."""
    game._advance()
    for _ in range(40):
        if not game.state.stack and game.pending() is None:
            return
        actions = game.legal_actions()
        if not actions:
            return
        game.apply(actions[0])


def empty_my_graveyard(game, *, to=Zone.EXILE) -> None:
    """One op's worth of movement: every card at once, one batch."""
    game.state.event_batch += 1
    for oid in list(game.state.players[0].graveyard):
        move_object(game.state, oid, to, cause="test")


class TestTheEventFiresAtAll:
    def test_a_card_leaving_your_graveyard_triggers(self, builder):
        game, oid = board(builder, MASCOT)
        assert plus_one_counters(game, oid) == 0
        empty_my_graveyard(game)
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_a_card_arriving_does_not(self, builder):
        """The direction that every existing trigger already watched."""
        game, oid = board(builder, MASCOT, buried=0)
        game.state.event_batch += 1
        move_object(
            game.state, game.state.players[0].library[0], Zone.GRAVEYARD,
            to_player=0, cause="test",
        )
        settle(game)
        assert plus_one_counters(game, oid) == 0

    def test_an_opponents_graveyard_does_not(self, builder):
        """"**your** graveyard" -- keyed by the yard's owner, per 400.3."""
        game, oid = board(builder, MASCOT, buried=0)
        game.state.event_batch += 1
        for gy_oid in list(game.state.players[1].graveyard):
            move_object(game.state, gy_oid, Zone.EXILE, cause="test")
        settle(game)
        assert plus_one_counters(game, oid) == 0

    def test_it_does_not_care_who_moved_the_card(self, builder):
        """An opponent's graveyard hate still fires your Mascot.

        This is the half that hanging the counter off `return_from_graveyard`
        or an `exile_from_graveyard` cost could never have covered.
        """
        game, oid = board(builder, MASCOT)
        game.state.event_batch += 1
        move_object(
            game.state, game.state.players[0].graveyard[0], Zone.EXILE,
            cause="opponent_hate",
        )
        settle(game)
        assert plus_one_counters(game, oid) == 1


class TestOneOrMore:
    """The batching, measured against the card that lacks it."""

    def test_three_cards_leaving_at_once_is_one_counter(self, builder):
        game, oid = board(builder, MASCOT, buried=3)
        empty_my_graveyard(game)
        settle(game)
        assert plus_one_counters(game, oid) == 1, (
            "'one or more cards' must fire once for a simultaneous departure"
        )

    def test_without_batched_the_same_move_counts_three(self, builder):
        """The counterfactual: identical trigger, no `batched`."""
        game, oid = board(builder, GREEDY, buried=3)
        empty_my_graveyard(game)
        settle(game)
        assert plus_one_counters(game, oid) == 3

    def test_two_separate_departures_fire_twice(self, builder):
        """Not `max_per_turn: 1`, which is a different card.

        A printed "one or more" fires again later the same turn for a second,
        separate departure. A per-turn cap would swallow the second.
        """
        game, oid = board(builder, MASCOT, buried=2)
        game.state.event_batch += 1
        move_object(
            game.state, game.state.players[0].graveyard[0], Zone.EXILE, cause="test"
        )
        settle(game)
        game.state.event_batch += 1
        move_object(
            game.state, game.state.players[0].graveyard[0], Zone.EXILE, cause="test"
        )
        settle(game)
        assert plus_one_counters(game, oid) == 2


class TestTheCounterIsReal:
    def test_the_mascot_grows(self, builder):
        game, oid = board(builder, MASCOT)
        before = chars(game.state, oid).power
        empty_my_graveyard(game)
        settle(game)
        assert chars(game.state, oid).power == before + 1


class TestTheFilterAsksWhatLeft:
    """Cyan, Vengeful Samurai: "one or more **creature cards**".

    A trigger filter is matched against the event's *subject*, and
    `_subject_oid` returns one only for events listed in
    `OBJECT_SUBJECT_TRIGGERS`. `leaves_graveyard` was not, so the filter had
    nothing to match and the trigger silently never fired -- a card that loads,
    prints its line, and does nothing at all. The card has already reached its
    new zone when the event fires and `matches_card_filter` reads the printed
    face, so the subject is still there to be asked about, exactly as it is for
    `discard`.
    """

    PICKY = "t_picky_mascot"

    def test_creature_cards_leaving_trigger_it(self, builder):
        game, oid = board(builder, self.PICKY, buried=3)
        empty_my_graveyard(game)
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_lands_leaving_do_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [self.PICKY])
            .graveyard(0, ["forest", "forest"])
            .build(advance=False)
        )
        oid = only_oid(game, self.PICKY)
        empty_my_graveyard(game)
        settle(game)
        assert plus_one_counters(game, oid) == 0

    def test_a_mixed_departure_fires_once(self, builder):
        """One creature among lands is still "one or more creature cards"."""
        game = (
            builder(players=2)
            .battlefield(0, [self.PICKY])
            .graveyard(0, [BEAR, "forest"])
            .build(advance=False)
        )
        oid = only_oid(game, self.PICKY)
        empty_my_graveyard(game)
        settle(game)
        assert plus_one_counters(game, oid) == 1

