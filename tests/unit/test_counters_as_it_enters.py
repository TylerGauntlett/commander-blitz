"""Counters a permanent enters with are counters "put" on it -- rule 122.6.

    122.6: "Some spells and abilities refer to counters being 'put' on an
    object. This refers to putting counters on that object while it's on the
    battlefield and also to an object that's given counters as it enters the
    battlefield."

    122.6a: "If an object enters the battlefield with counters on it, the
    effect causing the object to be given counters may specify which player
    puts those counters on it. If the effect doesn't specify a player, the
    object's controller puts those counters on it."

The printed ruling on Simic Ascendancy and Sharktocrab says the same thing in
the words a player reads: "An ability that triggers when counters are put on a
permanent will trigger if that permanent somehow enters the battlefield with
those counters."

What was wrong: `zones._enter_battlefield` wrote the counters straight onto
the arriving object and fired nothing, "because the permanent was never on the
battlefield without them". That is why they are written *before* the arrival --
the permanent is never seen at its printed size -- but it is not a reason for
them not to have been put there. So Exemplar of Light ("Whenever you put one or
more +1/+1 counters on this creature, draw a card") entering under Giada, Font
of Hope drew nothing, and neither did a Hydra that "enters with two +1/+1
counters" and watches its own counters.

Now `_enter_battlefield` fires one COUNTER_PLACED per counter kind the
permanent arrived with, after ENTERS_BATTLEFIELD so the permanent's own
"…on this creature" is among the candidates, with ``put_by`` the permanent's
controller (122.6a) and the amount that actually arrived, replacements
included. What must not move:

- a Saga's chapter I triggers once -- its COUNTER_PLACED reaches no chapter
  comparison, `sagas.entered` is still the only route;
- an arrival with no counters reports nothing;
- "you put" is still the putter: a creature entering under an opponent's
  control had its counters put by that opponent.

**One placement.** Every "enters with" -- printed, starting loyalty, Giada's
and Oath of Gideon's extra counters, riot -- is a replacement on the same
event (614.1c, 306.5b), and so are Hardened Scales, Doubling Season and
compleated. They were applied one source at a time, and Giada's and the Oath's
were not replaced at all: Doubling Season with a printed-two Angel under Giada
gave 2*2 + 1 = 5, and Hardened Scales gave an Angel entering with only Giada's
counter nothing. Now the amounts are gathered per kind and put on once, in the
order 616.1e-f lets the controller choose, taken as the one that leaves the
most (`zones._entering_counters`), and COUNTER_PLACED reports that total.
"""

from __future__ import annotations

from automtg.engine import sagas
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.events import EventType
from automtg.engine.zones import move_object
from tests.conftest import action_for_card, only_oid, pass_until

GIADA = "giada_font_of_hope"  # the shipped card: "…an additional +1/+1 counter
# on it for each Angel you already control"
EXEMPLAR = "t_cae_exemplar"  # Exemplar of Light as printed
HYDRA = "t_cae_hydra"  # enters with two +1/+1 counters, draws on its own counters
ALLY_WATCHER = "t_cae_ally_watcher"  # +1/+1 counters on a creature you control: gain 1
PUTTER_WATCHER = "t_cae_putter_watcher"  # you put +1/+1 counters on any creature: draw
ANGEL_HYDRA = "t_cae_angel_hydra"  # an Angel that enters with two +1/+1 counters
SEASON = "t_ceo_season"  # Doubling Season's counter line
SCALES = "t_rc_scales"  # Hardened Scales: +1/+1 counters on a creature you control, plus one
WALKER = "t_walker"  # loyalty 4
OATH = "t_oath"  # each planeswalker you control enters with an additional loyalty
SAGA = "t_saga"  # I draw, II gain 2 life, III a Human Soldier
SAGA_WATCHER = "t_saga_watcher"  # a lore counter put on a permanent you control
BEAR = "t_bear"


#: Every card a test puts onto the battlefield, one in each player's hand.
ARRIVALS = [EXEMPLAR, HYDRA, ANGEL_HYDRA, WALKER, SAGA, BEAR]


def board(builder, mine=()):
    """A frozen main phase: ``mine`` on player 0's battlefield, the arrivals in
    both hands waiting for :func:`arrive`."""
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 6 + list(mine))
        .hand(0, ARRIVALS)
        .hand(1, ARRIVALS)
        .library(0, ["plains"] * 20)
        .library(1, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )


def arrive(game, card_id: str, pid: int = 0) -> int:
    """Put ``pid``'s ``card_id`` from hand onto the battlefield, by `move_object`
    -- an arrival with no spell and no ability behind it."""
    oid = next(
        o for o in game.state.players[pid].hand
        if game.state.objects[o].def_id == card_id
    )
    move_object(game.state, oid, Zone.BATTLEFIELD, to_player=pid)
    return oid


def placed(game, oid: int, counter: str | None = None) -> list:
    return [
        e for e in game.state.events
        if e.type == EventType.COUNTER_PLACED
        and e.data.get("oid") == oid
        and (counter is None or e.data.get("counter") == counter)
    ]


def queued(game, card_id: str) -> int:
    return sum(
        1 for t in game.state.pending_triggers
        if game.state.objects[t.source_oid].def_id == card_id
    )


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestTheWitness:
    """Exemplar of Light entering under Giada, Font of Hope."""

    def test_cast_under_giada_it_draws(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 6 + [GIADA])
            .hand(0, [EXEMPLAR])
            .library(0, ["plains"] * 20)
            .library(1, ["plains"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, EXEMPLAR))
        settle(game)
        exemplar = only_oid(game, EXEMPLAR, 0)
        assert game.state.objects[exemplar].counter("+1/+1") == 1, "Giada's one Angel"
        assert len(game.state.players[0].hand) == 1, "and Exemplar drew for it"

    def test_the_event_is_the_arrival_put_by_its_controller(self, builder):
        """122.6a: no player is named, so the permanent's controller puts them.
        One event for the arrival, with the count Giada gave: two Angels already
        there, two counters, one "one or more"."""
        game = board(builder, mine=[GIADA, EXEMPLAR])
        second = arrive(game, EXEMPLAR)
        events = placed(game, second, "+1/+1")
        assert [(e.data["amount"], e.data["put_by"]) for e in events] == [(2, 0)]
        assert queued(game, EXEMPLAR) == 1

    def test_after_the_enters_event(self, builder):
        """So the permanent is on the battlefield and its own trigger can see it."""
        game = board(builder, mine=[GIADA])
        oid = arrive(game, EXEMPLAR)
        kinds = [
            e.type for e in game.state.events
            if e.data.get("oid") == oid
            and e.type in (EventType.ENTERS_BATTLEFIELD, EventType.COUNTER_PLACED)
        ]
        assert kinds == [EventType.ENTERS_BATTLEFIELD, EventType.COUNTER_PLACED]

    def test_once_each_turn_still_holds(self, builder):
        """The arrival spends Exemplar's once-each-turn: a second placement the
        same turn draws nothing more."""
        from automtg.engine.primitives import add_counters

        game = board(builder, mine=[GIADA])
        oid = arrive(game, EXEMPLAR)
        add_counters(game.state, oid, "+1/+1", 1, by=0)
        assert queued(game, EXEMPLAR) == 1


class TestEveryEntersWithPath:
    def test_printed_enters_with_counters(self, builder):
        """"This creature enters with two +1/+1 counters on it" -- no static on
        the board at all."""
        game = board(builder)
        oid = arrive(game, HYDRA)
        assert [e.data["amount"] for e in placed(game, oid, "+1/+1")] == [2]
        assert queued(game, HYDRA) == 1

    def test_a_watcher_of_creatures_you_control_sees_it(self, builder):
        game = board(builder, mine=[ALLY_WATCHER])
        arrive(game, HYDRA)
        assert queued(game, ALLY_WATCHER) == 1

    def test_the_amount_is_the_replaced_amount(self, builder):
        """Doubling Season doubles the counters it enters with (122.6), and the
        event reports the four that arrived, not the two that were printed."""
        game = board(builder, mine=[SEASON])
        oid = arrive(game, HYDRA)
        assert game.state.objects[oid].counter("+1/+1") == 4
        assert [e.data["amount"] for e in placed(game, oid, "+1/+1")] == [4]

    def test_starting_loyalty_is_put_on(self, builder):
        """A planeswalker's loyalty is counters it enters with (306.5b), so it is
        reported too -- with an Oath of Gideon's extra one folded in, one event."""
        game = board(builder, mine=[OATH])
        oid = arrive(game, WALKER)
        events = placed(game, oid, "loyalty")
        assert [(e.data["amount"], e.data["put_by"]) for e in events] == [(5, 0)]


class TestOnePlacement:
    """Every "enters with" is one event, and the counter replacements apply to
    its total once (122.6, 614.5, 616.1)."""

    def _arrive(self, game, card_id: str, kind: str) -> tuple[int, list[int]]:
        oid = arrive(game, card_id)
        return game.state.objects[oid].counter(kind), [
            e.data["amount"] for e in placed(game, oid, kind)
        ]

    def test_doubling_season_doubles_printed_plus_giada(self, builder):
        """A printed-two Angel under Giada (one Angel already there) under
        Doubling Season: (2 + 1) * 2 = 6. It was 2*2 + 1 = 5 -- the Season
        doubled the printed two and never saw Giada's."""
        game = board(builder, mine=[GIADA, SEASON])
        assert self._arrive(game, ANGEL_HYDRA, "+1/+1") == (6, [6])

    def test_hardened_scales_adds_to_giadas_counter(self, builder):
        """An Angel whose only counter is Giada's still enters with one or more,
        so Hardened Scales applies: 1 + 1 = 2. It was 1."""
        game = board(builder, mine=[GIADA, SCALES])
        assert self._arrive(game, EXEMPLAR, "+1/+1") == (2, [2])

    def test_hardened_scales_applies_once_to_the_total(self, builder):
        """Printed two plus Giada's one is one placement of three, plus one:
        four, not five."""
        game = board(builder, mine=[GIADA, SCALES])
        assert self._arrive(game, ANGEL_HYDRA, "+1/+1") == (4, [4])

    def test_scales_then_season_is_the_controllers_order(self, builder):
        """Hardened Scales before Doubling Season (616.1): (2 + 1) * 2 = 6
        rather than 2 * 2 + 1 = 5, whichever arrived first."""
        game = board(builder, mine=[SEASON, SCALES])
        assert self._arrive(game, HYDRA, "+1/+1") == (6, [6])

    def test_scales_alone_gives_nothing_to_an_arrival_with_none(self, builder):
        """The near miss: "if one or more +1/+1 counters would be put" -- an
        Angel under Hardened Scales with no Giada enters with none at all."""
        game = board(builder, mine=[SCALES])
        assert self._arrive(game, EXEMPLAR, "+1/+1") == (0, [])

    def test_oath_and_season_on_a_walker(self, builder):
        """Loyalty 4 plus the Oath's one, doubled: 10. It was 4*2 + 1 = 9."""
        game = board(builder, mine=[OATH, SEASON])
        assert self._arrive(game, WALKER, "loyalty") == (10, [10])

    def test_oath_and_hardened_scales_on_a_walker(self, builder):
        """Hardened Scales is about +1/+1 counters on a creature, so a
        planeswalker's loyalty is the Oath's 4 + 1 and nothing more."""
        game = board(builder, mine=[OATH, SCALES])
        assert self._arrive(game, WALKER, "loyalty") == (5, [5])


class TestTheSagaDoesNotDoubleTrigger:
    def test_chapter_one_fires_once(self, builder):
        game = board(builder, mine=[SAGA_WATCHER])
        oid = arrive(game, SAGA)
        chapters = [
            e.data["chapter"] for e in game.state.events
            if e.type == EventType.CHAPTER_REACHED and e.data.get("oid") == oid
        ]
        assert chapters == [1]
        assert queued(game, SAGA) == 1

    def test_the_lore_counter_is_reported_once(self, builder):
        """And a "lore counter put on a permanent you control" watcher sees the
        Saga's first counter, which by 122.6 it was."""
        game = board(builder, mine=[SAGA_WATCHER])
        oid = arrive(game, SAGA)
        assert [e.data["amount"] for e in placed(game, oid, sagas.LORE)] == [1]
        assert queued(game, SAGA_WATCHER) == 1


class TestTheNearMisses:
    def test_no_counters_no_event(self, builder):
        """Exemplar without Giada enters with nothing, and draws nothing."""
        game = board(builder)
        oid = arrive(game, EXEMPLAR)
        assert placed(game, oid) == []
        assert queued(game, EXEMPLAR) == 0

    def test_a_non_angel_under_giada_gets_and_reports_nothing(self, builder):
        game = board(builder, mine=[GIADA, ALLY_WATCHER])
        oid = arrive(game, BEAR)
        assert placed(game, oid) == []
        assert queued(game, ALLY_WATCHER) == 0

    def test_an_opponents_arrival_was_put_by_them(self, builder):
        """122.6a: the permanent's controller puts them. My "whenever **you**
        put" watcher does not fire for an opponent's Hydra, though their
        Hydra's own "you put" does."""
        game = board(builder, mine=[PUTTER_WATCHER])
        oid = arrive(game, HYDRA, pid=1)
        assert [e.data["put_by"] for e in placed(game, oid, "+1/+1")] == [1]
        assert queued(game, PUTTER_WATCHER) == 0
        assert queued(game, HYDRA) == 1

    def test_my_arrival_fires_my_putter_watcher(self, builder):
        """The control for the one above."""
        game = board(builder, mine=[PUTTER_WATCHER])
        arrive(game, HYDRA)
        assert queued(game, PUTTER_WATCHER) == 1
