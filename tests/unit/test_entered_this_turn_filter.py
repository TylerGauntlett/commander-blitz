"""Asking **one** permanent whether it entered the battlefield this turn.

    "Zurgo and Ojutai has hexproof as long as it entered this turn."
                                                      -- Zurgo and Ojutai
    "If a creature you control that entered this turn would deal damage, it
     deals twice that much damage instead."   -- Neriv, Heart of the Storm

Two cards, two static positions -- a `grant_keyword` gated on its own source,
and a `replace_damage` filtering the permanent that is about to deal damage --
and one missing word between them. `STATIC_FILTER_KEYS` had no temporal clause
at all, so `damage_source` and `affects` could name what a permanent *is* and
never when it arrived.

**Why this is legal in a static filter, when power is not.** A static filter is
documented to read printed characteristics, and "entered this turn" is not one.
The rule it is really keeping is narrower than the slogan: `check_static_
constraints` forbids a filter from reading another static's *output*, because
layers-lite applies continuous effects in a fixed order and has no way to
resolve a cycle. Printed characteristics are the large safe family, and they
have never been the only one -- `tapped`, `attacking`, `is_token`, `owner` and
`controller` are board state and are all in that list already, on the footing
that no layer of the pipeline writes them. An arrival snapshot is one step
safer still: `TurnLedger.permanents_entered` is written once, by `GameState.
emit` folding ENTERS_BATTLEFIELD, and is not rewritten at all. Power is the
contrast, and it is refused because it is an *output* -- four layers rewrite it.

**Why it is not the value leaf that already existed.** `permanents_entered_this_
turn` sums arrivals across a filter, and an `EnteredPermanent` snapshot carries
*characteristics* only. So the narrowest condition writable without this key is
"an Orc Dragon you control entered this turn", which is satisfied by any second
Orc Dragon -- and Zurgo is an Orc Dragon in a deck full of Dragons. `t_ett_
zurgo_ledger` is that near miss written out and kept live, so the difference
between "this permanent entered" and "some matching permanent did" is measured
on one board rather than argued for in a comment.

**Why it is not `GameObject.entered_turn`.** That field is what `summoning_sick`
reads, and `change_control` stamps it -- rule 302.6 makes a stolen permanent
sick without its having entered anything. A filter reading it would double an
Act of Treason'd attacker under Neriv and hand a stolen commander hexproof.
`TestItIsArrivalAndNotControl` pins the divergence the other way round.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import Keyword, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import change_control, damage_permanent, damage_player
from automtg.engine.state import new_object
from automtg.engine.zones import destroy, move_object
from tests.conftest import oids_of, pass_until

ZURGO = "t_ett_zurgo"  # hexproof as long as *it* entered this turn
LEDGER_ZURGO = "t_ett_zurgo_ledger"  # ...as long as an Orc Dragon you control did
NERIV = "t_ett_neriv"  # doubles damage from creatures that entered this turn
GRATUITOUS = "t_ett_gratuitous"  # the same static with the temporal clause dropped
DRAGON = "t_ett_dragon"  # a plain Orc Dragon, to be the *other* one
BEAR = "t_ett_bear"  # 2/2, something to deal damage with


def board(builder, mine=(), theirs=()):
    """A position whose permanents have all been there since before this turn.

    `build()` auto-passes forward, so the ledger has been cleared at a cleanup
    step and nothing on this board entered this turn -- which is the "standing
    there, but did not arrive" half of every assertion below.
    """
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .build()
    )


def arrive(game, card_id: str, pid: int = 0) -> int:
    """Make a card *enter* the battlefield, firing the real event.

    The route does not matter and the event does: a creature that is cast, one
    that is reanimated and one that is put onto the battlefield by another card
    all enter, and `zones._enter_battlefield` is the funnel all three share --
    which is where the ledger entry is written.

    Not `builder.battlefield(..., sick=True)`, which sets `entered_turn` and
    emits nothing. That is the point of the whole file: the two are different
    facts, and only one of them is an arrival.
    """
    obj = new_object(game.state, card_id, owner=pid, zone=Zone.HAND)
    game.state.players[pid].hand.append(obj.oid)
    move_object(game.state, obj.oid, Zone.BATTLEFIELD)
    return obj.oid


def hexproof(game, oid: int) -> bool:
    return Keyword.HEXPROOF.value in chars(game.state, oid).keywords


class TestTheStaticReadsItsOwnArrival:
    """Zurgo's half: a condition on the permanent that carries the ability."""

    def test_a_permanent_already_there_has_no_hexproof(self, builder):
        game = board(builder, [ZURGO])
        assert not hexproof(game, oids_of(game, ZURGO, 0)[0])

    def test_a_permanent_that_entered_this_turn_has_it(self, builder):
        game = board(builder)
        assert hexproof(game, arrive(game, ZURGO))

    def test_it_wears_off_at_the_turn_boundary(self, builder):
        """The ledger is cleared at cleanup, so the grant expires with it.

        Played out through a real turn rather than by clearing the ledger by
        hand: the claim is that the cleanup step which already clears morbid and
        storm ends this grant too, and nothing else has to be taught about it.

        Without this the card would be plain hexproof written the long way.
        """
        game = board(builder)
        zurgo = arrive(game, ZURGO)
        assert hexproof(game, zurgo)

        started = game.state.turn
        pass_until(game, lambda g: g.state.turn > started)
        assert not hexproof(game, zurgo)

    def test_an_arrival_and_return_this_turn_still_counts(self, builder):
        """Nothing is removed from the ledger while the turn lasts, so a
        permanent that entered, left and came back has an entry for the trip it
        is on -- which is the one the printed line asks about."""
        game = board(builder)
        zurgo = arrive(game, ZURGO)
        destroy(game.state, zurgo)
        move_object(game.state, zurgo, Zone.BATTLEFIELD)
        assert hexproof(game, zurgo)


class TestThisPermanentAndNotAMatchingOne:
    """The sharpest claim in the file, and the reason the key exists.

    Both Zurgos on these boards are Orc Dragons and neither entered this turn.
    A *second* Orc Dragon then lands. The value leaf counts arrivals by
    characteristic and cannot tell the two apart; the filter asks by oid.
    """

    def test_another_orc_dragon_arriving_grants_nothing(self, builder):
        game = board(builder, [ZURGO])
        zurgo = oids_of(game, ZURGO, 0)[0]
        arrive(game, DRAGON)
        assert not hexproof(game, zurgo)

    def test_the_value_leaf_is_fooled_by_exactly_that_board(self, builder):
        """`t_ett_zurgo_ledger` is the near miss, kept live and measured.

        It reads "as long as an Orc Dragon you control entered this turn" --
        the narrowest sentence the snapshots can express -- and turns on for a
        Zurgo that has been standing there since last turn.
        """
        game = board(builder, [LEDGER_ZURGO])
        zurgo = oids_of(game, LEDGER_ZURGO, 0)[0]
        assert not hexproof(game, zurgo)

        arrive(game, DRAGON)
        assert hexproof(game, zurgo), "the near miss, firing on somebody else's arrival"

    def test_two_copies_disagree_about_which_of_them_arrived(self, builder):
        """One board, one card, two objects: only the new one is hexproof."""
        game = board(builder, [ZURGO])
        old = oids_of(game, ZURGO, 0)[0]
        new = arrive(game, ZURGO)
        assert hexproof(game, new)
        assert not hexproof(game, old)


class TestItIsArrivalAndNotControl:
    """`entered_turn` is the near miss, and it is wrong on a control change.

    Rule 302.6 stamps `entered_turn` when control changes, so `summoning_sick`
    can say a stolen creature has not been under its new controller since their
    turn began. It did not enter the battlefield, and 400.7 is clear that a
    control change is not a zone change -- so the printed clause is false for it.
    """

    def test_a_stolen_permanent_did_not_enter_this_turn(self, builder):
        game = board(builder, theirs=[ZURGO])
        zurgo = oids_of(game, ZURGO, 1)[0]
        change_control(game.state, zurgo, 0)

        assert game.state.objects[zurgo].summoning_sick(game.state.turn), (
            "the control change stamped `entered_turn`, which is what this "
            "filter must not read"
        )
        assert not hexproof(game, zurgo)

    def test_a_permanent_stolen_after_arriving_still_entered(self, builder):
        """The other direction: the ledger entry is keyed by oid, so it
        survives the creature changing hands."""
        game = board(builder)
        zurgo = arrive(game, ZURGO, pid=1)
        change_control(game.state, zurgo, 0)
        assert hexproof(game, zurgo)


class TestTheReplacementFilter:
    """Neriv's half: the same key on `damage_source` rather than `affects`."""

    def test_a_creature_already_there_deals_its_printed_damage(self, builder):
        game = board(builder, [NERIV, BEAR])
        bear = oids_of(game, BEAR, 0)[0]
        assert damage_player(game.state, 1, 2, bear) == 2

    def test_a_creature_that_entered_this_turn_deals_double(self, builder):
        game = board(builder, [NERIV])
        bear = arrive(game, BEAR)
        assert damage_player(game.state, 1, 2, bear) == 4

    def test_it_doubles_damage_to_a_permanent_too(self, builder):
        """No `combat_only`, and `affects` is absent: Neriv doubles any damage
        from a qualifying creature, to anything."""
        game = board(builder, [NERIV], theirs=[DRAGON])
        bear = arrive(game, BEAR)
        target = oids_of(game, DRAGON, 1)[0]
        assert damage_permanent(game.state, target, 2, bear) == 4

    def test_an_opponents_new_creature_is_not_doubled(self, builder):
        """`controller: "you"` is still read: the key does not short-circuit."""
        game = board(builder, [NERIV])
        theirs = arrive(game, BEAR, pid=1)
        assert damage_player(game.state, 0, 2, theirs) == 2

    def test_without_the_clause_every_creature_is_doubled(self, builder):
        """`t_ett_gratuitous` is the approximation the gap record refused.

        Kept live so the assertions above are measuring the temporal clause and
        not a board on which the replacement never applied at all.
        """
        game = board(builder, [GRATUITOUS, BEAR])
        bear = oids_of(game, BEAR, 0)[0]
        assert damage_player(game.state, 1, 2, bear) == 4


class TestTheLoaderPlacesTheKey:
    def _card(self, ability: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "",
                "mana_cost": "{2}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [ability],
            }
        )

    def test_a_counting_filter_refuses_it_outside_the_battlefield(self):
        """A card in a graveyard did not enter the battlefield, this turn or
        ever, so the key is refused there with the rest of the board state
        rather than loading and matching nothing."""
        with pytest.raises(DslError, match="entered_this_turn"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "effect": "grant_keyword",
                        "keywords": ["flying"],
                        "affects": {"self_only": True},
                        "condition": {
                            "exists": {
                                "zone": "graveyard",
                                "entered_this_turn": True,
                            }
                        },
                    }
                )
            )

    def test_a_battlefield_counting_filter_accepts_it(self):
        """"…for each creature you control that entered this turn" is a
        magnitude, and the same key answers it through the same `_matches`."""
        compile_card(
            self._card(
                {
                    "kind": "static",
                    "effect": "buff",
                    "affects": {"self_only": True},
                    "power": {
                        "count": {
                            "controller": "you",
                            "types": ["Creature"],
                            "entered_this_turn": True,
                        }
                    },
                    "toughness": {"const": 0},
                }
            )
        )
