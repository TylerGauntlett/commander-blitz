"""Finality counters -- 122.1g, a replacement of the graveyard that lives on a counter.

    Shuri's Fabricator -- "{6}, {T}: Return target artifact card from your
    graveyard to the battlefield with a finality counter on it. Activate only as
    a sorcery. (If a permanent with a finality counter on it would be put into a
    graveyard, exile it instead.)"

Counter kinds are free strings and `return_from_graveyard` already took a
``counters`` map, so the Fabricator's line always loaded. Without the
replacement the counter is an inert tally and the returned artifact goes back to
the graveyard to be returned again every turn -- a strictly better card that
passes every authoring gate, which is why this is a unit test.

The rule is "put into a graveyard **from the battlefield**", so every route is
covered by `zones.move_object` rather than by `destroy`: destroyed, sacrificed,
0 toughness. It is a replacement (614.6), so the permanent never dies and its
own dies trigger does not fire. The counter is read, not spent. And it is the
affected player's own replacement, so Kalitas, which would also exile the
creature, has nothing left to replace and makes no Zombie (616.1).
"""

from __future__ import annotations

import pytest

from commanderblitz.engine import sba
from commanderblitz.engine.effects.values import validate_counter_kind
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import FINALITY
from commanderblitz.engine.primitives import add_counters
from commanderblitz.engine.zones import destroy, move_object, sacrifice
from tests.conftest import activations, oids_of, only_oid, settle

FABRICATOR = "t_fabricator_like"
CONSTRUCT = "t_artifact_this_dies"  # an artifact creature: "When this dies, gain 1 life."
BEAR = "t_bear"
KALITAS = "t_kalitas_like"
ZOMBIE = "zombie_2_2_b"


def final(builder, card: str = CONSTRUCT, *, pid: int = 0, mine=(), theirs=()):
    """``card`` on ``pid``'s battlefield with a finality counter, in a main phase."""
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .battlefield(pid, [card])
        .library(0, ["plains"] * 5)
        .library(1, ["plains"] * 5)
        .build()
    )
    oid = oids_of(game, card, pid)[-1]
    add_counters(game.state, oid, FINALITY, 1)
    return game, oid


def zone_of(game, oid: int) -> Zone:
    return game.state.objects[oid].zone


class TestEveryRouteToTheGraveyard:
    def test_destroyed_it_is_exiled(self, builder):
        game, oid = final(builder)

        destroy(game.state, oid)

        assert zone_of(game, oid) is Zone.EXILE
        assert game.state.players[0].graveyard == []

    def test_sacrificed_it_is_exiled(self, builder):
        game, oid = final(builder)

        assert sacrifice(game.state, oid) is True

        assert zone_of(game, oid) is Zone.EXILE

    def test_zero_toughness_it_is_exiled(self, builder):
        game, oid = final(builder)
        add_counters(game.state, oid, "-1/-1", 1)

        sba.check(game.state)

        assert zone_of(game, oid) is Zone.EXILE

    def test_a_token_is_exiled_too(self, builder):
        """A token in exile ceases to exist all the same, but it is never put
        into a graveyard, so nothing watching the graveyard sees it."""
        game, oid = final(builder, BEAR)
        game.state.objects[oid].is_token = True

        destroy(game.state, oid)

        assert game.state.players[0].graveyard == []


class TestItIsNotADeath:
    def test_its_own_dies_trigger_does_not_fire(self, builder):
        game, oid = final(builder)
        life = game.state.players[0].life

        destroy(game.state, oid)
        settle(game)

        assert game.state.players[0].life == life


class TestOnlyTheGraveyard:
    def test_a_bounce_is_not_replaced(self, builder):
        game, oid = final(builder)

        move_object(game.state, oid, Zone.HAND)

        assert zone_of(game, oid) is Zone.HAND

    def test_without_a_counter_it_dies(self, builder):
        game, oid = final(builder)
        game.state.objects[oid].counters.pop(FINALITY)

        destroy(game.state, oid)

        assert zone_of(game, oid) is Zone.GRAVEYARD

    def test_the_card_comes_back_without_one(self, builder):
        """400.7: the exiled card is a new object, counters and all."""
        game, oid = final(builder)

        destroy(game.state, oid)

        assert game.state.objects[oid].counter(FINALITY) == 0


class TestTheAffectedPlayersReplacementComesFirst:
    def test_kalitas_makes_no_zombie(self, builder):
        """616.1: the owner of the dying creature applies its own replacement
        first, and there is no death left for Kalitas to replace."""
        game, oid = final(builder, BEAR, pid=1, mine=(KALITAS,))

        destroy(game.state, oid)

        assert zone_of(game, oid) is Zone.EXILE
        assert oids_of(game, ZOMBIE, 0) == []

    def test_a_commander_still_goes_home(self, builder):
        game = (
            builder(players=2)
            .commander(0, ["t_commander"])
            .library(0, ["plains"] * 5)
            .library(1, ["plains"] * 5)
            .build()
        )
        (oid,) = game.state.players[0].commanders
        move_object(game.state, oid, Zone.BATTLEFIELD)
        add_counters(game.state, oid, FINALITY, 1)

        destroy(game.state, oid)

        assert zone_of(game, oid) is Zone.COMMAND


class TestShurisFabricator:
    def board(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FABRICATOR] + ["wastes"] * 6)
            .graveyard(0, [CONSTRUCT])
            .library(0, ["plains"] * 5)
            .library(1, ["plains"] * 5)
            .build()
        )
        (construct,) = game.state.players[0].graveyard
        return game, only_oid(game, FABRICATOR), construct

    def test_it_returns_with_a_finality_counter(self, builder):
        game, fabricator, construct = self.board(builder)
        (activation,) = [
            a
            for a in activations(game, fabricator)
            if not a.targets or any(t.id == construct for t in a.targets)
        ]

        game.apply(activation)
        settle(game)

        assert zone_of(game, construct) is Zone.BATTLEFIELD
        assert game.state.objects[construct].counter(FINALITY) == 1

    def test_and_it_cannot_be_returned_twice(self, builder):
        game, fabricator, construct = self.board(builder)
        game.apply(activations(game, fabricator)[0])
        settle(game)

        destroy(game.state, construct)

        assert zone_of(game, construct) is Zone.EXILE


class TestTheSpellingIsExact:
    def test_a_near_miss_is_refused(self):
        validate_counter_kind("finality", "probe")
        for near in ("Finality", "finality counter", "finality counters"):
            with pytest.raises(DslError, match="finality counter"):
                validate_counter_kind(near, "probe")
