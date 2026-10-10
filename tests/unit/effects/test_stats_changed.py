"""Buffs stopped happening off screen.

``pump``, ``animate`` and ``grant_keyword`` all mutate ``until_eot`` and call
``bump_chars()``, and all three used to do it in complete silence.  Nothing
downstream could see them.  That is a real hole rather than a cosmetic one:
"target creature gets +3/+3 until end of turn" is the single most common combat
trick in the game, and from the log's point of view it simply did not happen --
a 2/2 blocked a 3/3, took lethal damage, and lived, with no line anywhere saying
why.

``STATS_CHANGED`` is emitted through ``state.emit`` and deliberately not through
``triggers.fire``.  ``zones.py`` warns that keys added to a *fired* event's
``data`` become bindings a card's triggered ability reads, so firing this would
quietly change what abilities match against.  Nothing is meant to trigger off
it; it exists to be watched.
"""

from __future__ import annotations

from commanderblitz.engine.enums import Keyword
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import animate, grant_keyword, pump


def a_creature(builder):
    game = builder(players=2).battlefield(0, ["t_bear"]).build()
    oid = next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == "t_bear"
    )
    return game, oid


def stats_events(game):
    return [e for e in game.state.events if e.type == EventType.STATS_CHANGED]


class TestPump:
    def test_a_pump_is_announced(self, builder):
        game, oid = a_creature(builder)
        pump(game.state, oid, 3, 3)

        [event] = stats_events(game)
        assert event.source == oid
        assert event.data["power"] == 3
        assert event.data["toughness"] == 3

    def test_the_event_names_the_card_so_a_log_line_can_be_written(self, builder):
        game, oid = a_creature(builder)
        pump(game.state, oid, 1, 1)

        [event] = stats_events(game)
        assert event.data["card"] == "t_bear"
        assert event.player == game.state.objects[oid].controller

    def test_a_negative_pump_is_announced_too(self, builder):
        """-3/-0 is how a creature is stopped from killing something, and it was
        exactly as invisible as the positive case."""
        game, oid = a_creature(builder)
        pump(game.state, oid, -3, 0)

        [event] = stats_events(game)
        assert event.data["power"] == -3

    def test_nothing_is_said_about_a_permanent_that_is_not_there(self, builder):
        game, oid = a_creature(builder)
        pump(game.state, oid + 999, 3, 3)
        assert stats_events(game) == []


class TestTheOtherTwo:
    def test_animating_a_land_is_announced(self, builder):
        game, oid = a_creature(builder)
        animate(game.state, oid, 4, 4)

        [event] = stats_events(game)
        assert (event.data["power"], event.data["toughness"]) == (4, 4)

    def test_granting_a_keyword_names_the_keyword_and_no_numbers(self, builder):
        game, oid = a_creature(builder)
        grant_keyword(game.state, oid, Keyword.FLYING)

        [event] = stats_events(game)
        assert event.data["keyword"] == Keyword.FLYING
        assert "power" not in event.data


class TestItDoesNotTrigger:
    def test_the_event_queues_no_triggered_abilities(self, builder):
        """The reason it goes through `state.emit` rather than `triggers.fire`.

        A pump that woke the trigger system would give every "whenever this
        creature..." ability a new event to match against, and the bindings it
        carries would land in the same `data` dict those abilities read from.
        """
        game, oid = a_creature(builder)
        before = len(game.state.pending_triggers)
        pump(game.state, oid, 2, 2)
        assert len(game.state.pending_triggers) == before
