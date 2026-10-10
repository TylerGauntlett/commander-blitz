"""``entered_this_turn`` — the effect-side selector key that *gathers* the
turn's arrivals rather than counting them or asking about one of them.

    Ocelot Pride — "…then if you have the city's blessing, **for each token you
    control that entered this turn**, create a token that's a copy of it."

The reading already existed in every other filter language in the engine and in
none of the one this card needs. `characteristics._matches` answers it for
statics (Zurgo and Ojutai's "as long as it entered this turn"),
`cost_reduction._object_matches` answers it on the cost side, and
`triggers.matches_card_filter` answers it for trigger filters. Only
`effects.selectors` could not say it, and `validate_selector` turns any key
outside `SELECTOR_KEYS` into a load error — so the clause was a refused card
rather than a silently wrong one, which is the good failure.

Counting is not a substitute, and that is what this file pins. The value
`permanents_entered_this_turn` reads the same ledger and yields **a number**;
`for_each` needs the object *pool*, so it can bind `each` and hand it to
`copy_permanent`. A number cannot be copied.

Three near misses, each of which would be a different card:

1. `created_with: "self"` is restricted to the literal string "self" and gathers
   only the tokens this source itself made — on Ocelot Pride that misses every
   token another card made this turn, which is most of what it copies.
2. A bare `is_token: true` gathers the whole token board, so a deck that has
   been making Cats for six turns would copy all of them at once instead of the
   turn's arrivals. `entered_this_turn` is the clause that narrows it, and the
   two compose.
3. Reading `entered_turn` off the object instead of the ledger is the subtle
   one: that field is what `summoning_sick` reads, and it is not the arrival
   record 400.7 makes meaningful.

Witness: Ocelot Pride (`ocelot_pride` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool, validate_selector
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.state import new_object
from commanderblitz.engine.zones import move_object

BEAR = "t_bear"  # {1}{G} vanilla creature
PLAINS = "plains"

#: Ocelot Pride's own shape, minus the `is_token` clause it composes with.
ARRIVED = {
    "zone": "battlefield",
    "controller": "you",
    "entered_this_turn": True,
    "count": "all",
}

#: The same pool without the new key -- everything you control, which is what
#: the card would have had to say before.
EVERYTHING = {"zone": "battlefield", "controller": "you", "count": "all"}


def board(builder, standing=(BEAR,)):
    """Six Plains and whatever was already there when the turn began.

    A permanent the builder places is never *moved* onto the battlefield, so it
    has no ledger entry -- which is precisely a permanent from an earlier turn.
    """
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 6 + list(standing))
        .battlefield(1, ["forest"])
        .hand(0, [PLAINS])
        .build()
    )


def ctx(game, controller: int = 0, source: int | None = None) -> EffectContext:
    return EffectContext(state=game.state, controller=controller, source_oid=source)


def arrive(game, card_id: str, pid: int = 0) -> int:
    """Make a card *enter* the battlefield, firing the real event.

    `move_object` is the funnel a cast, a reanimation and a put-onto-battlefield
    all share, and it is what writes the ledger entry.
    """
    obj = new_object(game.state, card_id, owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD)
    return obj.oid


def pool(game, selector, controller: int = 0) -> set[int]:
    return set(resolve_pool(ctx(game, controller), selector))


def standing_oid(game, card_id: str, pid: int = 0) -> int:
    return next(o.oid for o in game.state.battlefield_objects(pid) if o.def_id == card_id)


class TestItGathersTheTurnsArrivals:
    def test_a_permanent_that_entered_this_turn_is_in_the_pool(self, builder):
        game = board(builder)
        assert arrive(game, BEAR) in pool(game, ARRIVED)

    def test_one_that_was_already_there_is_not(self, builder):
        """The whole of what the key adds."""
        game = board(builder)
        arrive(game, BEAR)
        assert standing_oid(game, BEAR) not in pool(game, ARRIVED)

    def test_without_the_key_both_are_gathered(self, builder):
        """Pins that the exclusion above is this key's doing and not the
        position's: unfiltered, the standing permanent is right there."""
        game = board(builder)
        arrived = arrive(game, BEAR)
        standing = standing_oid(game, BEAR)
        wide = pool(game, EVERYTHING)
        assert arrived in wide and standing in wide

    def test_it_composes_with_the_rest_of_the_selector(self, builder):
        """Ocelot Pride writes it beside `controller` and `is_token`, so it has
        to narrow an ordinary pool rather than replace it. An opponent's
        arrival is the half `controller` is carrying."""
        game = board(builder)
        mine = arrive(game, BEAR, pid=0)
        theirs = arrive(game, BEAR, pid=1)
        assert mine in pool(game, ARRIVED)
        assert theirs not in pool(game, ARRIVED)


class TestFalseIsTheComplement:
    def test_false_gathers_what_did_not_enter(self, builder):
        game = board(builder)
        arrived = arrive(game, BEAR)
        did_not = pool(game, {**ARRIVED, "entered_this_turn": False})
        assert standing_oid(game, BEAR) in did_not
        assert arrived not in did_not


class TestTheRecordIsTheArrivalAndNotTheObjectsAge:
    def test_a_permanent_that_left_and_came_back_counts_again(self, builder):
        """400.7 -- what returns is a new object, and the printed reading
        follows the arrival rather than the card.

        This is also the reason the key reads the ledger rather than
        `entered_turn`: that field is `summoning_sick`'s, and the two answer
        different questions.
        """
        game = board(builder)
        oid = standing_oid(game, BEAR)
        assert oid not in pool(game, ARRIVED)
        move_object(game.state, oid, Zone.EXILE)
        move_object(game.state, oid, Zone.BATTLEFIELD)
        assert oid in pool(game, ARRIVED)


class TestTheLoaderKnowsTheKey:
    def test_the_selector_validates(self):
        validate_selector(ARRIVED, "t_probe.effects[0].objects")

    def test_a_word_it_cannot_answer_is_still_refused(self):
        """The guard that made this a refused card rather than a silent
        mis-read, and it has to keep refusing everything else."""
        with pytest.raises(DslError):
            validate_selector(
                {"zone": "battlefield", "entered_last_turn": True},
                "t_probe.effects[0].objects",
            )
