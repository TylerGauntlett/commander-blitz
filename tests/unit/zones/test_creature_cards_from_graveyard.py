"""Syrix, Carrier of the Flame — "if a **creature card** left your graveyard this turn".

    At the beginning of each end step, if a creature card left your graveyard
    this turn, target Phoenix you control deals damage equal to its power to
    any target.

`cards_from_graveyard_this_turn` already answered Gau's "if **a card** left
your graveyard this turn", and for Syrix it is true in the wrong games: a
fetched-back land, a flashed-back instant or a Bojuka Bog on your yard each
make one card leave and no creature card, and the Phoenix would fire anyway --
a strictly better Syrix, and a silent one.

The type cannot be recovered after the fact. By the end step the card that
left may be a creature animated into something else, a card face down in
exile, or a shuffled library card; nothing about it now says what it was as it
left. So the ledger records the departed card's printed id (the face a card
has in a graveyard, 712.8a) at the moment it leaves, and the typed form
`{"player": …, "filter": …}` matches that face -- the same shape and matcher as
`spells_cast_this_turn`'s typed form, which answers "noncreature spells" off
the recorded ids for the same reason.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

BEAR = "t_bear"
INSTANT = "t_plain_instant"
LAND = "t_dual_land"

CREATURE = {"types": ["Creature"]}


def creatures_left(game, who="you", controller: int = 0, filt=CREATURE) -> int:
    ctx = EffectContext(state=game.state, controller=controller)
    return evaluate_value(
        ctx, {"cards_from_graveyard_this_turn": {"player": who, "filter": filt}}
    )


def position(builder, mine=(BEAR, INSTANT, LAND), theirs=(), *, advance=False):
    """A two-seat game with ``mine`` in seat 0's graveyard; returns (game, oids by card)."""
    game = (
        builder(players=2)
        .graveyard(0, list(mine))
        .graveyard(1, list(theirs))
        .build(advance=advance)
    )
    oids = {game.state.objects[o].def_id: o for o in game.state.players[0].graveyard}
    return game, oids


def leave(game, oid, to=Zone.EXILE):
    move_object(game.state, oid, to, to_player=game.state.objects[oid].owner, cause="test")


class TestOnlyACreatureCardCounts:
    def test_nothing_has_left(self, builder):
        game, _ = position(builder)
        assert creatures_left(game) == 0

    @pytest.mark.parametrize("card", [INSTANT, LAND])
    def test_a_noncreature_card_leaving_does_not_count(self, builder, card):
        game, oids = position(builder)
        leave(game, oids[card])
        assert creatures_left(game) == 0
        # ...though it is a card that left, which is the whole near miss.
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"cards_from_graveyard_this_turn": "you"}) == 1

    @pytest.mark.parametrize("to", [Zone.EXILE, Zone.HAND, Zone.BATTLEFIELD, Zone.LIBRARY])
    def test_a_creature_card_leaving_counts_wherever_it_goes(self, builder, to):
        game, oids = position(builder)
        leave(game, oids[BEAR], to)
        assert creatures_left(game) == 1

    def test_only_the_creatures_among_several(self, builder):
        game, _ = position(builder, mine=(BEAR, BEAR, INSTANT, LAND))
        for oid in list(game.state.players[0].graveyard):
            leave(game, oid)
        assert creatures_left(game) == 2

    def test_a_negated_filter_reads_the_complement(self, builder):
        game, oids = position(builder)
        leave(game, oids[BEAR])
        leave(game, oids[INSTANT])
        assert creatures_left(game, filt={"not_types": ["Creature"]}) == 1


class TestItIsTheFaceAsItLeft:
    def test_a_reanimated_creature_still_counts_after_it_changes_zone_again(self, builder):
        """The record outlives the object: 400.7 makes the bear a new object twice."""
        game, oids = position(builder)
        leave(game, oids[BEAR], Zone.BATTLEFIELD)
        leave(game, oids[BEAR], Zone.EXILE)
        assert creatures_left(game) == 1


class TestItIsYourGraveyard:
    def test_an_opponents_creature_card_is_not_yours(self, builder):
        game, _ = position(builder, mine=(), theirs=(BEAR,))
        leave(game, game.state.players[1].graveyard[0])
        assert creatures_left(game, "you") == 0
        assert creatures_left(game, "opponent") == 1


class TestTheTurnBoundary:
    def test_the_count_resets_next_turn(self, builder):
        game, oids = position(builder, advance=True)
        leave(game, oids[BEAR])
        assert creatures_left(game) == 1

        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert game.state.turn > turn
        assert creatures_left(game) == 0, (
            "a turn-scoped fact that survived the turn would fire Syrix every end step"
        )


class TestTheLoaderGuard:
    @pytest.mark.parametrize(
        "spec",
        [
            {"player": "you", "filter": CREATURE},
            {"filter": CREATURE},
            {"player": "opponent", "filter": {"subtypes": ["Phoenix"]}},
            "you",
        ],
    )
    def test_the_printed_forms_load(self, spec):
        validate_value({"cards_from_graveyard_this_turn": spec}, "test")

    @pytest.mark.parametrize(
        "spec",
        [
            {"player": "you", "filter": {}},
            {"player": "you", "filter": CREATURE, "zone": "exile"},
            {"player": "everyone", "filter": CREATURE},
            # Board state the remembered card no longer has.
            {"player": "you", "filter": {"types": ["Creature"], "tapped": True}},
            {"player": "you", "filter": {"paid_by": {"types": ["Land"]}}},
        ],
    )
    def test_anything_else_is_refused(self, spec):
        with pytest.raises(DslError, match="cards_from_graveyard_this_turn"):
            validate_value({"cards_from_graveyard_this_turn": spec}, "test")
