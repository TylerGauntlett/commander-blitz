"""Exert (702.128): a keyword that needed nothing.

The census routes it as "`attacks` trigger plus a `may`; `skip_untap` already
exists for the cost", which is a complete description of a card that can be
written today — and it sat on the `routed` list anyway, because the row was
never checked against the vocabulary it names.

So this file adds no engine code. It exists because a `free` claim in the
census is only a claim until something cashes it, and the cheapest way for
"exert is free" to become false is for nobody to ever try.

The three parts, all shipped long before:

- `attacks` with `source: "self"` — "as it attacks".
- `may` — "you **may** exert", and declining must cost nothing.
- `skip_untap` — "it won't untap during your next untap step", which is the
  whole price of the keyword.

The one thing worth asserting carefully is the *timing of the assertion*, not
the mechanic. Both halves are transient in opposite directions: the pump is
until end of turn, and `skip_next_untap` is spent by the very next untap step.
A test that drives the game forward before looking reads both as absent and
concludes the keyword does nothing — which is what the first attempt at this
file did.
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until

EXERTER = "t_exerter"  # 2/2; may exert as it attacks for +2/+2


def attack(game, oid: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    game.apply(
        find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),))
    )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def position(builder):
    game = builder(players=2).battlefield(0, [EXERTER]).build()
    return game, only_oid(game, EXERTER, 0)


class TestTheChoiceIsOffered:
    def test_attacking_asks(self, builder):
        game, oid = position(builder)
        attack(game, oid)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.MAY

    def test_not_attacking_does_not_ask(self, builder):
        game, _oid = position(builder)
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        decision = game.pending()
        assert decision is None or decision.kind is not DecisionKind.MAY


class TestExerting:
    def test_it_pumps_and_will_not_untap(self, builder):
        """Read immediately: the pump dies at cleanup and the untap flag is
        spent by the next untap step, so anything that advances first sees
        neither."""
        game, oid = position(builder)
        attack(game, oid)
        game.apply(find_action(game, ActionKind.YES))
        assert chars(game.state, oid).power == 4
        assert game.state.objects[oid].skip_next_untap

    def test_declining_costs_nothing(self, builder):
        game, oid = position(builder)
        attack(game, oid)
        game.apply(find_action(game, ActionKind.NO))
        assert chars(game.state, oid).power == 2
        assert not game.state.objects[oid].skip_next_untap


class TestThePriceIsReal:
    def test_it_stays_tapped_through_the_next_untap_step(self, builder):
        """`skip_untap` is the whole cost of the keyword, and this is the only
        assertion that shows the player actually paid it."""
        game, oid = position(builder)
        attack(game, oid)
        game.apply(find_action(game, ActionKind.YES))
        assert game.state.objects[oid].tapped, "attacking tapped it"
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert game.state.objects[oid].tapped, (
            "its controller's next untap step came and went"
        )

    def test_declining_lets_it_untap(self, builder):
        game, oid = position(builder)
        attack(game, oid)
        game.apply(find_action(game, ActionKind.NO))
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert not game.state.objects[oid].tapped

    def test_the_flag_is_spent_once(self, builder):
        """It skips *one* untap step, not every one after it."""
        game, oid = position(builder)
        attack(game, oid)
        game.apply(find_action(game, ActionKind.YES))
        pass_until(game, lambda g: g.state.turn >= 3 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert game.state.objects[oid].tapped
        assert not game.state.objects[oid].skip_next_untap, "spent"
        pass_until(game, lambda g: g.state.turn >= 5 and g.state.step >= Step.PRECOMBAT_MAIN)
        assert not game.state.objects[oid].tapped, "the untap after that works"


class TestTheCardLoads:
    def test_it_uses_only_shipped_vocabulary(self, registry):
        card = registry.get(EXERTER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None and ability.trigger.event == "attacks"
        (may,) = ability.effects
        assert may["op"] == "may"
        assert [e["op"] for e in may["effects"]] == ["skip_untap", "pump"]
