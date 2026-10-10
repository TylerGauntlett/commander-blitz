"""Banding — the last refused keyword, and it was one concept the engine had.

    "Banding (Any creatures with banding, and up to one without, can attack in a
    band. Bands are blocked as a group. If any creatures with banding you
    control are blocking or being blocked by a creature, you divide that
    creature's combat damage.)" (702.21)

Banding was the last `refused` row, and the recorded reason was that its second
half needs **player-chosen combat damage assignment**, which the engine
automates for every creature: blockers ordered by effective toughness, lethal
paid in order, nobody asked.

That reason was half right, and the half it got wrong is the interesting one.
The engine does not *lack* damage assignment order — it has had the concept all
along, in `CombatState.block_order`, and has simply been **sorting it instead of
asking**. So banding is not a new subsystem. It is two sentences:

- the automatic sort is a choice made silently on the attacking player's behalf;
- banding says *ask*, and ask **the other player**.

`ask_objects` records the order options were taken in, which is exactly what a
damage assignment order is, so the question needed no new `DecisionKind` either.

The other half, 702.21b, is the band declaration, and it is asked as **two**
questions because the printed sentence is two constraints: "one or more
attacking creatures with banding" and "up to one attacking creature without".
A single question could not say the second at all, and validating the answer
afterwards would mean offering a choice the engine then refuses.

Every combat with no banding in it asks nothing and behaves exactly as before —
`_ask_order` returns immediately when there is nothing to order, and
`band_of` returns a band of one, so the ordinary case falls straight through.
"""

from __future__ import annotations

from commanderblitz.engine.combat import (
    _divide,
    _order_chooser,
    add_attacker,
    add_blocker,
    start_combat,
)
from commanderblitz.engine.enums import Keyword
from tests.conftest import oids_of, only_oid

PLAINS = "plains"
BANDER = "t_bander"   # {2}{W} 2/2 with banding
SQUIRE = "t_small"    # {W} 1/1, no banding
BEAR = "t_bear"       # 2/2
GIANT = "t_big"       # a big body to block with


def board(builder, mine: list[str], theirs: list[str]):
    game = (
        builder(players=2)
        .battlefield(0, [PLAINS] * 4)
        .battlefield(0, mine)
        .battlefield(1, theirs)
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build(advance=False)
    )
    start_combat(game.state)
    return game


class TestTheBandIsRecorded:
    def test_a_band_makes_its_members_one_unit(self, builder):
        game = board(builder, [BANDER, SQUIRE], [])
        combat = game.state.combat
        bander, squire = only_oid(game, BANDER), only_oid(game, SQUIRE)
        combat.bands.append([bander, squire])

        assert combat.band_of(bander) == [bander, squire]
        assert combat.band_of(squire) == [bander, squire]

    def test_everything_else_is_a_band_of_one(self, builder):
        """Which is what lets the damage code treat both cases with one line."""
        game = board(builder, [BEAR], [])
        bear = only_oid(game, BEAR)

        assert game.state.combat.band_of(bear) == [bear]

    def test_a_dead_member_drops_out_of_it(self, builder):
        game = board(builder, [BANDER, SQUIRE], [])
        combat = game.state.combat
        bander, squire = only_oid(game, BANDER), only_oid(game, SQUIRE)
        combat.bands.append([bander, squire])
        combat.remove(squire)

        assert combat.band_of(bander) == [bander]


class TestWhoChoosesTheOrder:
    def _blocked_by(self, builder, blockers: list[str]):
        game = board(builder, [GIANT], blockers)
        attacker = only_oid(game, GIANT, 0)
        add_attacker(game.state, attacker, 1)
        game.state.combat.attackers_declared = True
        for blocker in oids_of(game, blockers[0], 1):
            add_blocker(game.state, blocker, attacker, 1)
        return game, attacker

    def test_nobody_is_asked_without_banding(self, builder):
        """The automatic sort stands, which is every combat in every other deck."""
        game, attacker = self._blocked_by(builder, [BEAR])

        assert _order_chooser(game.state, attacker) is None

    def test_a_blocker_with_banding_takes_the_choice(self, builder):
        """702.21, and the chooser is the *blocking* creature's controller."""
        game, attacker = self._blocked_by(builder, [BANDER])

        assert _order_chooser(game.state, attacker) == 1

    def test_an_unblocked_attacker_asks_nobody(self, builder):
        game = board(builder, [GIANT], [])
        attacker = only_oid(game, GIANT, 0)
        add_attacker(game.state, attacker, 1)

        assert _order_chooser(game.state, attacker) is None


class TestDividingDamage:
    def test_lethal_to_each_in_the_order_given(self, builder):
        """510.1c is one rule whoever is assigning, so there is one walk."""
        game = board(builder, [BEAR, SQUIRE], [GIANT])
        source = only_oid(game, GIANT, 1)
        bear, squire = only_oid(game, BEAR), only_oid(game, SQUIRE)

        out = _divide(game.state, source, 3, [bear, squire])

        assert [(a.to_object, a.amount) for a in out] == [(bear, 2), (squire, 1)]

    def test_the_order_is_what_changes_the_outcome(self, builder):
        """The same power, the other way round, kills a different creature."""
        game = board(builder, [BEAR, SQUIRE], [GIANT])
        source = only_oid(game, GIANT, 1)
        bear, squire = only_oid(game, BEAR), only_oid(game, SQUIRE)

        out = _divide(game.state, source, 2, [squire, bear])

        assert [(a.to_object, a.amount) for a in out] == [(squire, 1), (bear, 1)]

    def test_leftover_damage_piles_onto_the_last(self, builder):
        game = board(builder, [SQUIRE], [GIANT])
        source = only_oid(game, GIANT, 1)
        squire = only_oid(game, SQUIRE)

        out = _divide(game.state, source, 5, [squire])

        assert [(a.to_object, a.amount) for a in out] == [(squire, 5)]

    def test_deathtouch_makes_one_lethal(self, builder):
        game = board(builder, [BEAR, SQUIRE], [GIANT])
        source = only_oid(game, GIANT, 1)
        bear, squire = only_oid(game, BEAR), only_oid(game, SQUIRE)
        game.state.objects[source].granted_keywords.add(Keyword.DEATHTOUCH.value)
        game.state.bump_chars()

        out = _divide(game.state, source, 2, [bear, squire])

        assert [(a.to_object, a.amount) for a in out] == [(bear, 1), (squire, 1)]


class TestTheBandIsBlockedAsAUnit:
    def test_an_unblocked_member_of_a_blocked_band_hits_nobody(self, builder):
        """702.21e -- the whole defensive value of blocking a band."""
        from commanderblitz.engine.combat import _attacker_assignments

        game = board(builder, [BANDER, SQUIRE], [BEAR])
        bander, squire = only_oid(game, BANDER), only_oid(game, SQUIRE)
        blocker = only_oid(game, BEAR, 1)
        add_attacker(game.state, bander, 1)
        add_attacker(game.state, squire, 1)
        game.state.combat.attackers_declared = True
        game.state.combat.bands.append([bander, squire])
        add_blocker(game.state, blocker, bander, 1)

        out = _attacker_assignments(game.state, squire)

        assert all(a.to_player is None for a in out), "it is blocked with its band"

    def test_without_the_band_it_gets_through(self, builder):
        from commanderblitz.engine.combat import _attacker_assignments

        game = board(builder, [BANDER, SQUIRE], [BEAR])
        bander, squire = only_oid(game, BANDER), only_oid(game, SQUIRE)
        blocker = only_oid(game, BEAR, 1)
        add_attacker(game.state, bander, 1)
        add_attacker(game.state, squire, 1)
        game.state.combat.attackers_declared = True
        add_blocker(game.state, blocker, bander, 1)

        out = _attacker_assignments(game.state, squire)

        assert [a.to_player for a in out] == [1]


class TestTheKeywordIsReal:
    def test_it_is_on_the_card(self, builder):
        game = board(builder, [BANDER], [])
        assert Keyword.BANDING.value in game.state.card(only_oid(game, BANDER)).keywords
