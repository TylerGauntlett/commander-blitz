"""Crew — a cost measured in power rather than in permanents.

    "Crew 3 (Tap any number of creatures you control with total power 3 or more:
    This Vehicle becomes an artifact creature until end of turn.)"

The census filed this as "vehicles are not a supported type; `tap_permanents`
ships but counts permanents, and crew sums their **derived** power". Half of
that turned out to be free — `subtypes` is unvalidated free text, so *Vehicle*
needed nothing — and the other half is the whole capability: `tap_permanents`
gained a `total_power`.

A sum is not a count with a different number, and the board that separates them
is the ordinary one: **one 4/4 crews a Vehicle that four 0/1s cannot.** Written
as a count, crew is either unpayable on a wide small board or free on a tall
one, and both look plausible.

**Derived** power, for the reason skulk reads derived power: an anthem, a pump
spell or a +1/+1 counter all change who can crew, and reading the printed face
would refuse a crew the board plainly supports.

The question is asked **one creature at a time**, and that is forced rather than
stylistic: `ask_objects` takes counts, not sums, so a single subset question
could be answered with a set that does not reach the number — and a cost cannot
fail halfway through being paid. Asking until the total is met is also how a
player crews at a table, and it stops the moment the Vehicle is crewed rather
than taking every creature that could have helped.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind
from tests.conftest import only_oid

VEHICLE = "t_vehicle"      # crew 3
BEAR = "t_bear"            # 2/2
GIANT = "t_big"            # 6/6
DORK = "t_dork"            # a 1/1 mana creature
ANTHEM = "t_anthem"        # creatures you control get +1/+1
ISLAND = "island"


def position(builder, *crewers: str):
    game = (
        builder(players=2)
        .battlefield(0, [VEHICLE])
        .battlefield(0, list(crewers))
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
        .build()
    )
    return game, only_oid(game, VEHICLE)


def crew_action(game, vehicle: int):
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == vehicle
        ),
        None,
    )


def crew(game, vehicle: int, *, taps: int = 1):
    game.apply(crew_action(game, vehicle))
    for _ in range(taps):
        choose = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
        )
        if choose is None:
            break
        game.apply(choose)


class TestWhenItIsOffered:
    def test_one_big_creature_can_crew_it(self, builder):
        game, vehicle = position(builder, GIANT)
        assert crew_action(game, vehicle) is not None

    def test_two_small_creatures_can_crew_it_together(self, builder):
        game, vehicle = position(builder, BEAR, BEAR)
        assert crew_action(game, vehicle) is not None

    def test_a_board_that_cannot_reach_the_number_is_not_offered(self, builder):
        """Two 1/1s are two permanents and two power. A count would have crewed."""
        game, vehicle = position(builder, DORK, DORK)
        assert crew_action(game, vehicle) is None

    def test_one_creature_short_is_not_offered(self, builder):
        game, vehicle = position(builder, BEAR)
        assert crew_action(game, vehicle) is None

    def test_an_empty_board_is_not_offered(self, builder):
        game, vehicle = position(builder)
        assert crew_action(game, vehicle) is None


class TestItReadsDerivedPower:
    def test_an_anthem_makes_a_short_board_sufficient(self, builder):
        """Two 1/1s cannot crew 3; two 2/2s can, and the anthem is the difference."""
        game, vehicle = position(builder, DORK, DORK, ANTHEM)
        assert crew_action(game, vehicle) is not None

    def test_without_it_the_same_creatures_cannot(self, builder):
        game, vehicle = position(builder, DORK, DORK)
        assert crew_action(game, vehicle) is None


class TestPayingIt:
    def test_it_taps_the_creatures_that_crewed(self, builder):
        game, vehicle = position(builder, GIANT)
        giant = only_oid(game, GIANT)

        crew(game, vehicle, taps=1)

        assert game.state.objects[giant].tapped

    def test_the_vehicle_becomes_a_creature(self, builder):
        game, vehicle = position(builder, GIANT)

        crew(game, vehicle, taps=1)

        assert "Creature" in chars(game.state, vehicle).types
        assert chars(game.state, vehicle).power == 4

    def test_it_stops_asking_once_the_total_is_met(self, builder):
        """A 6/6 crews 3 on its own; the second Bear must not be taken too."""
        game, vehicle = position(builder, GIANT, BEAR)
        bear = only_oid(game, BEAR)

        game.apply(crew_action(game, vehicle))
        # The pool has two creatures, so the first pick is a real question; the
        # Giant alone satisfies crew 3, so no second one is asked for.
        giant = only_oid(game, GIANT)
        choose = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and giant in [t.id for t in a.targets]
        )
        game.apply(choose)

        assert game.state.objects[giant].tapped
        assert not game.state.objects[bear].tapped, "the Vehicle was already crewed"

    def test_two_creatures_are_taken_when_one_is_not_enough(self, builder):
        game, vehicle = position(builder, BEAR, BEAR)

        crew(game, vehicle, taps=2)

        tapped = [o for o in game.state.battlefield_objects(0) if o.tapped]
        assert len(tapped) == 2
        assert "Creature" in chars(game.state, vehicle).types

    def test_a_tapped_creature_cannot_crew(self, builder):
        """`tapped: false` is forced on the pool, as it is for every tap cost."""
        game = (
            builder(players=2)
            .battlefield(0, [VEHICLE])
            .battlefield(0, [GIANT], tapped=True)
            .library(0, [ISLAND] * 20)
            .library(1, [ISLAND] * 20)
            .build()
        )
        vehicle = only_oid(game, VEHICLE)
        assert crew_action(game, vehicle) is None
