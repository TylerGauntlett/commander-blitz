"""Counting what else is attached to the permanent this Equipment is on.

    "Equipped creature has double strike as long as two or more Equipment are
    attached to it."                                          -- Brass Knuckles
    "Enchanted creature gets +2/+2 for each Aura and Equipment attached to it."
                                                              -- Strong Back

`attached` and `attached_to_host` are the two ends of one relationship. The
first names the host -- the creature the Equipment is on, which is what every
"equipped creature gets…" static already reads. The second names that host's
*other* attachments, which nothing could say: `_matches` implements `attached`
as ``obj.oid == source.attached_to``, so a filter written
``{"subtypes": ["Equipment"], "attached": true}`` asks whether the equipped
*creature* is an Equipment and counts nought, every time, on every board.

Two design points, both load-bearing and both asserted below.

**It does not short-circuit.** `attached` returns the moment it matches, which is
right for a key that names exactly one permanent. This one is always paired with
a narrowing -- "two or more *Equipment*", "each *Aura and Equipment*" -- so
returning early would count every attachment and make Brass Knuckles turn on
from a single Aura. `t_broad_knuckles` is that mistake written deliberately, kept
live so the difference is measured rather than asserted in a comment.

**It suppresses the default `controller: "you"`**, as `attached` does. The
equipped creature may be an opponent's, and "attached to it" asks what is on it
rather than who controls what.

The source counts itself when it qualifies, which is the printed reading: Brass
Knuckles is one of the Equipment attached to the creature, so "two or more" is
itself plus one more.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Keyword
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import attach
from tests.conftest import oids_of, two_seat_board

KNUCKLES = "t_knuckles"  # double strike while 2+ Equipment are attached
BROAD = "t_broad_knuckles"  # the same, counting every attachment
SCALER = "t_scaler"  # +1/+1 for each attachment
GEAR = "t_plain_gear"  # an ordinary Equipment, there to be counted
CLOAK = "t_ah_cloak"  # an Aura, likewise
BEAR = "t_ah_bear"  # 2/2


def double_strike(game, oid: int) -> bool:
    return Keyword.DOUBLE_STRIKE.value in chars(game.state, oid).keywords


class TestTheCountIsOfSiblings:
    def test_one_equipment_alone_is_not_two(self, builder):
        game = two_seat_board(builder, [KNUCKLES, BEAR], advance=False)
        knuckles, bear = oids_of(game, KNUCKLES, 0)[0], oids_of(game, BEAR, 0)[0]
        attach(game.state, knuckles, bear)
        assert not double_strike(game, bear)

    def test_a_second_equipment_turns_it_on(self, builder):
        """And the Knuckles counts itself -- "two or more" is itself plus one."""
        game = two_seat_board(builder, [KNUCKLES, GEAR, BEAR], advance=False)
        knuckles = oids_of(game, KNUCKLES, 0)[0]
        gear = oids_of(game, GEAR, 0)[0]
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, knuckles, bear)
        attach(game.state, gear, bear)
        assert double_strike(game, bear)

    def test_an_equipment_on_a_different_creature_does_not_count(self, builder):
        """The sharpest form: the board has two Equipment, but not on one host.

        Written with a plain board count this would pass, which is the whole
        reason the key names a relationship instead.
        """
        game = two_seat_board(builder, [KNUCKLES, GEAR, BEAR, BEAR], advance=False)
        knuckles = oids_of(game, KNUCKLES, 0)[0]
        gear = oids_of(game, GEAR, 0)[0]
        first, second = oids_of(game, BEAR, 0)
        attach(game.state, knuckles, first)
        attach(game.state, gear, second)
        assert not double_strike(game, first)

    def test_an_unattached_equipment_counts_nothing(self, builder):
        """`source.attached_to` is None, so the filter matches nobody rather
        than matching every unattached permanent on the table."""
        game = two_seat_board(builder, [KNUCKLES, GEAR, BEAR], advance=False)
        bear = oids_of(game, BEAR, 0)[0]
        assert not double_strike(game, bear)


class TestTheRestOfTheFilterStillApplies:
    """The key must not short-circuit, or every card that prints it is wrong."""

    def test_an_aura_does_not_count_as_an_equipment(self, builder):
        game = two_seat_board(builder, [KNUCKLES, CLOAK, BEAR], advance=False)
        knuckles = oids_of(game, KNUCKLES, 0)[0]
        cloak = oids_of(game, CLOAK, 0)[0]
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, knuckles, bear)
        attach(game.state, cloak, bear)
        assert not double_strike(game, bear), "an Aura is not an Equipment"

    def test_without_the_subtype_narrowing_the_aura_does_count(self, builder):
        """`t_broad_knuckles` is the short-circuiting mistake, written out.

        Kept live so the assertion above is measuring the conjunction and not a
        board that happened to be empty.
        """
        game = two_seat_board(builder, [BROAD, CLOAK, BEAR], advance=False)
        broad = oids_of(game, BROAD, 0)[0]
        cloak = oids_of(game, CLOAK, 0)[0]
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, broad, bear)
        attach(game.state, cloak, bear)
        assert double_strike(game, bear)


class TestItReachesAnOpponentsCreature:
    def test_equipment_on_an_opponents_creature_still_counts(self, builder):
        """`attached_to_host` suppresses the default `controller: "you"`.

        Left defaulted, an Equipment moved onto an opponent's creature would
        stop counting the moment it got there -- and the printed line asks what
        is attached to the creature, not who controls it.
        """
        game = two_seat_board(builder, [KNUCKLES, GEAR], [BEAR], advance=False)
        knuckles = oids_of(game, KNUCKLES, 0)[0]
        gear = oids_of(game, GEAR, 0)[0]
        theirs = oids_of(game, BEAR, 1)[0]
        attach(game.state, knuckles, theirs)
        attach(game.state, gear, theirs)
        assert double_strike(game, theirs)


class TestItScalesAMagnitude:
    def test_the_buff_counts_every_attachment(self, builder):
        """Strong Back's half: a number rather than a threshold."""
        game = two_seat_board(builder, [SCALER, GEAR, CLOAK, BEAR], advance=False)
        scaler = oids_of(game, SCALER, 0)[0]
        gear = oids_of(game, GEAR, 0)[0]
        cloak = oids_of(game, CLOAK, 0)[0]
        bear = oids_of(game, BEAR, 0)[0]
        attach(game.state, scaler, bear)
        assert chars(game.state, bear).power == 3, "2/2 plus the Scaler itself"
        attach(game.state, gear, bear)
        assert chars(game.state, bear).power == 4
        attach(game.state, cloak, bear)
        assert chars(game.state, bear).power == 5

    def test_it_falls_back_when_an_attachment_leaves(self, builder):
        """The wearing-off. A count read once and cached would not move."""
        game = two_seat_board(builder, [SCALER, GEAR, BEAR, BEAR], advance=False)
        scaler = oids_of(game, SCALER, 0)[0]
        gear = oids_of(game, GEAR, 0)[0]
        first, second = oids_of(game, BEAR, 0)
        attach(game.state, scaler, first)
        attach(game.state, gear, first)
        assert chars(game.state, first).power == 4
        attach(game.state, gear, second)
        assert chars(game.state, first).power == 3


class TestTheLoaderPlacesTheKey:
    def _reduction(self) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "This spell costs {1} less to cast for each Equipment attached to it.",
                "mana_cost": "{4}",
                "types": ["Artifact"],
                "subtypes": ["Equipment"],
                "cost_reduction": {"count": {"attached_to_host": True}},
            }
        )

    def test_a_cost_reduction_refuses_it(self):
        """`costs._reduction_matches` does not read the key, so one written
        there would load and be silently ignored -- priced off a filter nobody
        honoured. Refused at load instead."""
        with pytest.raises(DslError, match="attached_to_host"):
            compile_card(self._reduction())
