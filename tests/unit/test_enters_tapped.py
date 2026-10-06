"""``enters_tapped`` — "Creatures your opponents control enter tapped."

    Authority of the Consuls — "Creatures your opponents control enter tapped.
    Whenever a creature an opponent controls enters, you gain 1 life."

This is the one thing a card's own ``replacements`` can never say. That list is a
closed ``self_*`` Literal (`self_enters`, `self_enters_tapped`,
`self_enters_with_counters`, `self_enters_prepared`, `self_enters_as_copy`,
`self_enters_replaced`) and every branch of it is read off the **arriving**
card's printed face, so each one speaks about itself. `self_enters_tapped` on
Authority taps the enchantment and leaves the opponents entirely alone.

That is not hypothetical. Ten cards in the shipped pool print a line about
somebody *else's* arrivals and carry `self_enters_tapped`, because it was the
only spelling available — Imposing Sovereign, Kismet, Frozen Aether, Loxodon
Gatekeeper, Root Maze, Orb of Dreams, Kinjalli's Sunwing, Thalia Heretic Cathar,
Uphill Battle and Spider-Woman. Every one of them taps itself on arrival and
does nothing to its opponents. This static is the shape they all needed.

Three claims:

**It reaches every arrival, not just a cast.** The static is read in
`zones._enter_battlefield`, where `obj.tapped` is decided, and that is the one
funnel a cast, a `put_onto_battlefield`, a token and a return from a graveyard
all go through. A version hung off the cast path would pass the obvious test and
let a reanimated creature arrive untapped.

**It is one-sided when the card says so, and symmetric only when it says that.**
`affects` is required, because the filter language defaults to
`controller: "you"` — an absent filter would tap the card's own side, which is
the same defect `self_enters_tapped` already produces, reached from the other
direction. Orb of Dreams' "Permanents enter tapped" is written with an explicit
`controller: "any"`, so the symmetric case is a statement rather than an
omission.

**It does not tap itself.** Orb of Dreams does not enter tapped: a permanent's
own static is not applying to its own entrance. By the point this runs the
arriving object is already in `state.battlefield` — which is what makes the
ordinary `_matches` filter language usable here at all — so the arriving object
has to be excluded as a *source* explicitly. `TestItDoesNotTapItself` is that
claim, and without it every symmetric card in the family would acquire the exact
bug this static exists to fix.

Witness: Authority of the Consuls
(`authority_of_the_consuls` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import create_token
from automtg.engine.state import new_object
from automtg.engine.zones import move_object

AUTHORITY = "t_authority"  # creatures your opponents control enter tapped
KISMET = "t_kismet_like"  # artifacts, creatures and lands too
ORB = "t_orb"  # permanents enter tapped -- symmetric, controller "any"
BEAR = "t_bear"  # 2/2 vanilla creature
PLAINS = "plains"


def board(builder, mine=(AUTHORITY,), theirs=()):
    """Player 0 holds the static; player 1 is the opponent it names."""
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 4 + list(mine))
        .battlefield(1, [PLAINS] * 4 + list(theirs))
        .hand(0, [PLAINS])
        .hand(1, [PLAINS])
        .build()
    )


def arrive(game, card_id: str, pid: int, from_zone: Zone = Zone.HAND) -> int:
    """Put a card into ``from_zone`` and move it onto the battlefield.

    `move_object` is the funnel every arrival shares -- a resolved cast, a
    `put_onto_battlefield`, a reanimation -- so this exercises the same seam the
    static is read at.
    """
    obj = new_object(game.state, card_id, owner=pid, zone=from_zone)
    if from_zone is Zone.HAND:
        game.state.players[pid].hand.append(obj.oid)
    elif from_zone is Zone.GRAVEYARD:
        game.state.players[pid].graveyard.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD)
    return obj.oid


def tapped(game, oid: int) -> bool:
    return game.state.objects[oid].tapped


class TestItTapsTheOpponentsArrival:
    def test_an_opponents_creature_arrives_tapped(self, builder):
        game = board(builder)
        assert tapped(game, arrive(game, BEAR, 1))

    def test_without_the_static_it_arrives_untapped(self, builder):
        """Pins that the tapping is the static's and not the arrival path's."""
        game = board(builder, mine=())
        assert not tapped(game, arrive(game, BEAR, 1))

    def test_its_controllers_own_creature_is_untouched(self, builder):
        """"Creatures **your opponents** control" -- the filter is the printed
        clause, and the whole card is a one-sided tax."""
        game = board(builder)
        assert not tapped(game, arrive(game, BEAR, 0))


class TestItReachesEveryArrival:
    """`obj.tapped` is decided in one place, so every route through it is
    covered. A version hung off the cast path would pass the test above and let
    a reanimated creature walk in untapped."""

    def test_a_creature_returned_from_a_graveyard_arrives_tapped(self, builder):
        game = board(builder)
        assert tapped(game, arrive(game, BEAR, 1, from_zone=Zone.GRAVEYARD))

    def test_a_token_arrives_tapped(self, builder):
        """A token is created straight onto the battlefield and never had a
        printed replacement of its own to read."""
        game = board(builder)
        oid = create_token(game.state, "cat_1_1_w", controller=1)
        oids = oid if isinstance(oid, list) else [oid]
        assert oids, "create_token returned nothing"
        assert all(tapped(game, o) for o in oids)


class TestTheFilterIsThePrintedClause:
    def test_the_narrow_version_leaves_a_land_alone(self, builder):
        """Authority names creatures only, so an opponent's land is untouched --
        which is the difference between it and Kismet."""
        game = board(builder)
        assert not tapped(game, arrive(game, PLAINS, 1))

    def test_the_wide_version_catches_the_land(self, builder):
        game = board(builder, mine=(KISMET,))
        assert tapped(game, arrive(game, PLAINS, 1))

    def test_the_symmetric_version_catches_both_sides(self, builder):
        """Orb of Dreams, written with `controller: "any"` out loud."""
        game = board(builder, mine=(ORB,))
        assert tapped(game, arrive(game, BEAR, 0))
        assert tapped(game, arrive(game, BEAR, 1))


class TestItDoesNotTapItself:
    """Orb of Dreams does not enter tapped: a permanent's own static is not
    applying to its own entrance.

    The arriving object is already in `state.battlefield` by the time this runs
    -- that is what makes the ordinary filter language work here -- so it has to
    be excluded as a source explicitly. Without this, every symmetric card in
    the family would acquire the same self-tapping bug that
    `self_enters_tapped` gave the ten cards in the pool.
    """

    def test_the_symmetric_permanent_arrives_untapped(self, builder):
        game = board(builder, mine=())
        assert not tapped(game, arrive(game, ORB, 0))

    def test_but_a_second_copy_taps_the_first(self, builder):
        """The exclusion is about the *arriving* object, not about the effect
        being self-blind: another Orb already out does tap the newcomer."""
        game = board(builder, mine=(ORB,))
        assert tapped(game, arrive(game, ORB, 0))


class TestTheLoaderRefusesTheSilentFailures:
    def _card(self, **extra) -> CardModel:
        static = {
            "kind": "static",
            "text": "Creatures your opponents control enter tapped.",
            "effect": "enters_tapped",
            "affects": {"controller": "opponent", "types": ["Creature"]},
        }
        static.update(extra)
        return CardModel.model_validate(
            {
                "id": "t_enters_tapped_probe",
                "name": "Enters Tapped Probe",
                "mana_cost": "{W}",
                "oracle_text": "Creatures your opponents control enter tapped.",
                "types": ["Enchantment"],
                "abilities": [static],
            }
        )

    def test_the_printed_shape_loads(self):
        assert compile_card(self._card()) is not None

    def test_a_missing_filter_is_refused(self):
        """The filter defaults to your own side, so an absent one is the very
        bug this static exists to fix, written the other way round."""
        with pytest.raises(DslError, match="needs 'affects'"):
            compile_card(self._card(affects=None))

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="not a quantity"):
            compile_card(self._card(amount={"const": 1}))
