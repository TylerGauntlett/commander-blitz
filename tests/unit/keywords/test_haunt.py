"""Haunt — an exile link pointing the other way.

    "When this creature dies, exile it haunting target creature.
     When the creature this card haunts dies, you gain 3 life."

The engine already had an exile link: `exiled_by`, written on the exiled card
and naming the permanent that exiled it. That direction is the O-Ring family's,
and it is right for O-Ring because the *exiler* is the thing that goes away and
its own leaves-trigger reads the link back.

Haunt is the mirror and needs the opposite. The card in exile is what survives,
and it is what has to notice a creature dying somewhere else — so the link
points from the haunting card **at its victim**, and the trigger filter is
answered off the ability's source rather than off the subject.

That last part is the whole reason `haunted_by` is a filter key rather than a
condition: by the time the second trigger fires, the haunted creature has died
and carries no record of who was haunting it. The haunting card is sitting in
exile with the link on it, which is why `active_zones: ["exile"]` is on that
ability — the same widening the cycling trigger needed for the graveyard.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Zone
from automtg.engine.zones import destroy
from tests.conftest import _default_answer, only_oid, pass_until

PLAINS = "plains"
SPIRIT = "t_haunter"
BEAR = "t_bear"


def position(builder):
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * 3)
        .battlefield(0, [SPIRIT])
        .battlefield(1, [BEAR])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )
    return game, only_oid(game, SPIRIT), only_oid(game, BEAR, 1)


def kill_and_haunt(game, spirit: int, victim: int) -> None:
    """Kill the Spirit and let its dies-trigger haunt ``victim``.

    A triggered ability's targets are enumerated as it goes on the stack, so
    with one legal creature there is nothing to ask; the choice only appears
    when the board offers more than one.
    """
    destroy(game.state, spirit)
    for _ in range(200):
        if not game.state.stack and game.state.objects[spirit].haunting is not None:
            return
        decision = game.pending()
        if decision is None:
            return
        wanted = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and victim in [t.id for t in a.targets]
        ]
        game.apply(wanted[0] if wanted else _default_answer(game, decision))


class TestTheLink:
    def test_dying_exiles_it_haunting_the_target(self, builder):
        game, spirit, bear = position(builder)

        kill_and_haunt(game, spirit, bear)

        assert game.state.objects[spirit].zone is Zone.EXILE
        assert game.state.objects[spirit].haunting == bear

    def test_it_points_at_the_victim_not_the_exiler(self, builder):
        """The direction that separates it from `exiled_by`."""
        game, spirit, bear = position(builder)

        kill_and_haunt(game, spirit, bear)

        assert game.state.objects[spirit].exiled_by is None
        assert game.state.objects[spirit].haunting == bear


class TestTheSecondTrigger:
    def test_the_haunted_creature_dying_fires_it(self, builder):
        game, spirit, bear = position(builder)
        kill_and_haunt(game, spirit, bear)
        life = game.state.players[0].life

        destroy(game.state, bear)
        pass_until(game, lambda g: g.state.players[0].life != life)

        assert game.state.players[0].life == life + 3

    def test_another_creature_dying_does_not(self, builder):
        """`haunted_by` names one object, and only that one."""
        game = (
            builder(players=2)
            .battlefield(0, [PLAINS] * 3)
            .battlefield(0, [SPIRIT])
            .battlefield(1, [BEAR, BEAR])
            .library(0, [PLAINS] * 20)
            .library(1, [PLAINS] * 20)
            .build()
        )
        spirit = only_oid(game, SPIRIT)
        bears = [o.oid for o in game.state.battlefield_objects(1)]
        kill_and_haunt(game, spirit, bears[0])
        life = game.state.players[0].life

        destroy(game.state, bears[1])
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert game.state.players[0].life == life, "the other Bear was not haunted"

    def test_it_fires_from_exile(self, builder):
        """The haunting card is in exile, so the ability has to be live there."""
        game, spirit, bear = position(builder)
        kill_and_haunt(game, spirit, bear)
        assert game.state.objects[spirit].zone is Zone.EXILE

        life = game.state.players[0].life
        destroy(game.state, bear)
        pass_until(game, lambda g: g.state.players[0].life != life)

        assert game.state.players[0].life == life + 3
