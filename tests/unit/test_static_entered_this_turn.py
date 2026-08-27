"""An anthem sized by what entered this turn, not by what is standing there.

Kinbinding: "Creatures you control get +X/+X, where X is the number of creatures
that entered the battlefield under your control this turn."

The board is the obvious place to count and it is wrong in **both** directions,
which is the whole reason `TurnLedger.permanents_entered` exists:

- a creature that has sat there since turn three did not enter this turn, and
  `{"count": {"zone": "battlefield", ...}}` counts it anyway;
- a creature that entered this turn and died still entered, and a board count
  has already forgotten it.

Both are ordinary lines of play. The effect side has read the ledger since
Éowyn; a *static* could not, because `STATIC_VALUE_KEYS` is deliberately smaller
than the effect-side language — every leaf in it has to read a pipeline *input*,
or one static could come to depend on another's output and the fixed order of
layers-lite has no way to resolve that.

An `EnteredPermanent` qualifies, one step more safely than a counter does: it is
a snapshot written once, at the moment of entry, and no layer of the
characteristics pipeline can write to it.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.errors import DslError
from automtg.engine.primitives import create_token
from automtg.engine.zones import destroy
from tests.conftest import oids_of

ANTHEM = "t_entered_anthem"

BEAR = "t_bear"


def board(builder):
    """The anthem and one creature that has been there since before this turn.

    `build` auto-passes forward, so the Bear's arrival is in a previous turn's
    ledger and has been cleared — which is exactly the "standing there but did
    not enter this turn" case.
    """
    game = (
        builder(players=2)
        .battlefield(0, [ANTHEM, BEAR])
        .battlefield(1, [BEAR])
        .library(0, ["forest"] * 10)
        .build()
    )
    return game, oids_of(game, BEAR, 0)[0]


class TestTheMagnitude:
    def test_a_creature_already_there_counts_for_nothing(self, builder):
        """The board-count near miss, in the direction it over-counts."""
        game, bear = board(builder)

        assert chars(game.state, bear).power == 2
        assert chars(game.state, bear).toughness == 2

    def test_each_arrival_this_turn_grows_it(self, builder):
        game, bear = board(builder)

        create_token(game.state, "soldier_1_1_w", 0, 1)
        assert chars(game.state, bear).power == 3

        create_token(game.state, "soldier_1_1_w", 0, 1)
        assert chars(game.state, bear).power == 4

    def test_an_arrival_that_died_still_counts(self, builder):
        """The board-count near miss, in the direction it under-counts.

        A creature that entered this turn and died still entered. This is the
        asymmetry that makes the ledger the right source and the board the
        wrong one, and it is also the printed card.
        """
        game, bear = board(builder)
        made = create_token(game.state, "soldier_1_1_w", 0, 1)
        assert chars(game.state, bear).power == 3

        destroy(game.state, made[0])

        assert chars(game.state, bear).power == 3

    def test_an_opponents_arrival_does_not_count(self, builder):
        """"under your control" is part of the printed sentence."""
        game, bear = board(builder)

        create_token(game.state, "soldier_1_1_w", 1, 1)

        assert chars(game.state, bear).power == 2

    def test_a_noncreature_arrival_does_not_count(self, builder):
        game, bear = board(builder)

        create_token(game.state, "clue_token", 0, 1)

        assert chars(game.state, bear).power == 2


class TestTheLoaderStillRefusesWhatItShould:
    def _variant(self, registry, cid, power):
        card = registry.get(ANTHEM)
        base = {
            "id": cid,
            "name": "Test Entered Anthem Bad",
            "oracle_text": card.oracle_text,
            "mana_cost": "{3}{W}{W}",
            "types": ["Enchantment"],
            "colors": ["W"],
            "color_identity": ["W"],
            "abilities": [
                {
                    "kind": "static",
                    "text": card.oracle_text,
                    "effect": "buff",
                    "affects": {"controller": "you", "types": ["Creature"]},
                    "power": power,
                    "toughness": {"const": 0},
                }
            ],
        }
        return CardModel.model_validate(base)

    def test_controller_is_required(self, registry):
        """An omitted `controller` would silently count the opponents' arrivals.

        The effect side has required it since the filter was written, and the
        static side goes through the same validator rather than a looser copy —
        two spellings of one rule is how they drift.
        """
        model = self._variant(
            registry,
            "t_entered_anthem_bad",
            {"permanents_entered_this_turn": {"types": ["Creature"]}},
        )
        with pytest.raises(DslError, match="controller"):
            compile_card(model)

    def test_an_unknown_leaf_is_still_refused(self, registry):
        """Widening the language must not have opened it."""
        model = self._variant(
            registry, "t_entered_anthem_bad2", {"cards_drawn_this_turn": "you"}
        )
        with pytest.raises(DslError, match="static values may only use"):
            compile_card(model)


class TestTheArrivalSeesItsOwnArrival:
    """The token the anthem's own trigger makes must be sized by itself too.

    `_enter_battlefield` bumps the characteristics cache *before* firing the
    enters event, and the ledger entry is written while that event is folded —
    so without a second bump the arriving permanent reads a magnitude computed
    one entry ago. Every other creature on the board comes out right and the new
    one comes out stale, which is the hardest kind of wrong number to notice: it
    corrects itself the moment anything else touches the board.

    Found by an authoring worker writing Kinbinding against this leaf, not by
    the tests above — they only ever asserted on a creature that was already
    there.
    """

    def test_a_token_that_just_entered_is_sized_by_its_own_arrival(self, builder):
        game, bear = board(builder)

        made = create_token(game.state, "soldier_1_1_w", 0, 1)

        assert chars(game.state, bear).power == 3, "the pre-existing creature"
        assert chars(game.state, made[0]).power == 2, (
            "the 1/1 that just entered is +1/+1 from its own arrival"
        )

    def test_several_at_once_all_see_every_arrival(self, builder):
        game, _bear = board(builder)

        made = create_token(game.state, "soldier_1_1_w", 0, 3)

        assert [chars(game.state, oid).power for oid in made] == [4, 4, 4]
