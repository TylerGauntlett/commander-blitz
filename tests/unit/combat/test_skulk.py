"""Skulk (702.72) — "can't be blocked by creatures with greater power."

    Vampire Cutthroat — "Skulk. Lifelink."

Every evasion the engine had asks one fixed question. Flying and menace read a
quality of one creature; landwalk reads the defending player's board; a
`block_restriction` reads a printed characteristic of the would-be blocker.
Skulk is the first that **compares the two creatures**, and that is what made it
the remaining half of the `blocking-restriction` gap after Stromkirk Noble's
half shipped.

It could not be spelled as a `blockers` filter, and not for want of a `power`
key. Static filters are matched against *printed* characteristics on purpose —
that is the constraint that keeps the fixed-order characteristics pipeline
acyclic (`characteristics` module docstring) — while skulk must read **derived**
power on both sides at the moment blockers are declared. An anthem, a pump spell
or a +1/+1 counter on either creature changes who may block, and the printed
card is not consulted at all. So the comparison lives in `combat.can_block`,
beside landwalk, which reads `chars` for the same reason.

A keyword rather than a static, on the landwalk precedent: skulk takes no
parameter, so there is nothing for a static to carry.

The boundary is the card. "Greater power" is strictly greater — an equal-power
creature blocks, and an engine that wrote `>=` would pass every test that only
tried a bigger blocker.
"""

from __future__ import annotations

from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.combat import can_block
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until


def board(builder, mine: list[str], theirs: list[str], *, counters=None):
    """``(game, attacker_oid)`` with the skulker attacking and blockers pending.

    The attacker is always ``mine[-1]``, so a test can put an anthem in front of
    it without moving the creature under test.
    """
    b = builder(players=2).battlefield(0, ["forest"] * 8 + mine)
    if counters:
        b = b.battlefield(1, theirs, counters=counters)
    else:
        b = b.battlefield(1, theirs)
    game = b.build()
    attacker = only_oid(game, mine[-1])
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(
            game, ActionKind.ADD_ATTACKER, source=attacker, targets=(TargetRef.player(1),)
        )
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, attacker


class TestGreaterPowerCannotBlock:
    def test_a_bigger_creature_is_refused(self, builder):
        game, attacker = board(builder, ["t_skulker"], ["t_menacer"])
        bigger = only_oid(game, "t_menacer", 1)
        assert chars(game.state, bigger).power > chars(game.state, attacker).power
        assert not can_block(game.state, bigger, attacker, 1)

    def test_a_smaller_creature_blocks(self, builder):
        game, attacker = board(builder, ["t_skulker"], ["t_dork"])
        assert can_block(game.state, only_oid(game, "t_dork", 1), attacker, 1)

    def test_equal_power_blocks(self, builder):
        """The boundary, and the whole of "greater". A 2/2 blocks a 2/2 skulker;
        an engine written with `>=` passes every other test in this class."""
        game, attacker = board(builder, ["t_skulker"], ["t_bear"])
        bear = only_oid(game, "t_bear", 1)
        assert chars(game.state, bear).power == chars(game.state, attacker).power
        assert can_block(game.state, bear, attacker, 1)

    def test_a_creature_without_skulk_is_blocked_by_anything(self, builder):
        """The pair for the class. Without it, "can't be blocked" and "can't
        block" look the same from the refusals alone."""
        game, attacker = board(builder, ["t_bear"], ["t_menacer"])
        assert can_block(game.state, only_oid(game, "t_menacer", 1), attacker, 1)

    def test_legality_does_not_offer_the_refused_block(self, builder):
        game, _ = board(builder, ["t_skulker"], ["t_menacer"])
        bigger = only_oid(game, "t_menacer", 1)
        offered = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source == bigger
        ]
        assert not offered


class TestItReadsDerivedPower:
    def test_an_anthem_on_the_blocker_takes_the_block_away(self, builder):
        """A 2/2 that could block a 2/2 skulker cannot once it is a 3/3. Printed
        power says it still can, which is exactly the reading this must not do."""
        game, attacker = board(builder, ["t_skulker"], ["t_bear", "t_anthem"])
        bear = only_oid(game, "t_bear", 1)
        assert chars(game.state, bear).power == 3
        assert not can_block(game.state, bear, attacker, 1)

    def test_a_counter_on_the_blocker_takes_it_away_too(self, builder):
        """Counters are board state rather than a static, and they land in a
        different layer of `chars`; both have to reach the comparison."""
        game, attacker = board(
            builder, ["t_skulker"], ["t_bear"], counters={"+1/+1": 1}
        )
        bear = only_oid(game, "t_bear", 1)
        assert chars(game.state, bear).power == 3
        assert not can_block(game.state, bear, attacker, 1)

    def test_pumping_the_attacker_gives_the_block_back(self, builder):
        """The other side of the comparison. A 3/3 blocks a 3/3 skulker, so the
        anthem in front of the skulker undoes what its own size forbade."""
        game, attacker = board(builder, ["t_anthem", "t_skulker"], ["t_menacer"])
        bigger = only_oid(game, "t_menacer", 1)
        assert chars(game.state, attacker).power == 3
        assert chars(game.state, bigger).power == 3
        assert can_block(game.state, bigger, attacker, 1)

    def test_granted_skulk_evades_as_well_as_printed(self, builder):
        """`grant_keyword` reaches skulk because it is a real keyword and not a
        static -- the landwalk argument, and the reason for choosing a keyword."""
        game, attacker = board(builder, ["t_skulk_granter", "t_bear"], ["t_menacer"])
        assert "skulk" in chars(game.state, attacker).keywords
        assert not can_block(game.state, only_oid(game, "t_menacer", 1), attacker, 1)
