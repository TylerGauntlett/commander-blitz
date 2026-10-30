"""Melee (702.121) -- a keyword whose whole content is a rules-supplied trigger.

    "Melee (Whenever this creature attacks, it gets +1/+1 until end of turn for
    each opponent you attacked this combat.)"
                                        -- Titania, Proud Pummeler

    "Other creatures you control have melee."   -- the same card

The count is of *opponents*, not creatures, and of *this combat*, not this
turn, and it is made as the ability resolves (702.121b) -- with a creature that
attacked a planeswalker or battle counting that permanent's controller. None of
the existing values says that: `attacked_this_turn` counts who attacked rather
than whom; a `player_count` over `attacked_by` counts only the seats this one
creature attacked, misses walker attacks, and lasts the turn. So the count is
`TurnLedger.opponents_attacked_this_combat`, frozen at the declaration and
reset by `combat.start_combat`, read by the `opponents_attacked_this_combat`
value.

And it is a `Keyword` -- exalted's shape -- because Titania *grants* melee: the
trigger is `carddef.MELEE_TRIGGER`, yielded for every permanent whose derived
keywords include it.

The rules points, each with a test:

- one opponent attacked is +1/+1, two are +2/+2, however many creatures;
- the count is every creature you attacked with, not just this one;
- a granted melee triggers, each creature for itself, and "other" means other;
- a second combat counts only its own attacks;
- attacking only a planeswalker counts its controller (702.121b);
- an attacker removed before resolution still counts its opponent;
- the loader refuses a value without a player spec.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import untap_permanent
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.turn import grant_extra_phases
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, keywords, oids_of, only_oid, pass_until, pt, settle

BRAWLER = "t_ml_brawler"  # 2/2, printed melee
TITANIA = "t_ml_titania"  # 4/4 first strike, melee, "other creatures you control have melee"
BEAR = "t_bear"  # 2/2, no abilities
WALKER = "t_walker"  # loyalty 4
BOLT = "t_bolt"  # {R} instant, so priority stops while a trigger is on the stack

VALUE = {"opponents_attacked_this_combat": "you"}


def position(builder, *, mine=(BRAWLER,), players=3, theirs=None):
    b = (
        builder(players=players)
        .battlefield(0, ["mountain", *mine])
        .hand(0, [BOLT])
        .step(Step.PRECOMBAT_MAIN)
    )
    for pid, cards in (theirs or {}).items():
        b.battlefield(pid, cards)
    game = b.build()
    to_declare_attackers(game)
    return game


def to_declare_attackers(game) -> None:
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)


def declare(game, attacks: dict[int, TargetRef]) -> None:
    for oid, ref in attacks.items():
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def at(pid: int) -> TargetRef:
    return TargetRef.player(pid)


def opponents_attacked(game, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), VALUE)


class TestOpponentsAttacked:
    def test_one_opponent_is_plus_one(self, builder):
        game = position(builder)
        brawler = only_oid(game, BRAWLER, 0)
        declare(game, {brawler: at(1)})
        settle(game)
        assert pt(game, brawler) == (3, 3)

    def test_two_opponents_are_plus_two(self, builder):
        """The other creature's opponent counts: "you attacked", not "it attacked"."""
        game = position(builder, mine=(BRAWLER, BEAR))
        brawler, bear = only_oid(game, BRAWLER, 0), only_oid(game, BEAR, 0)
        declare(game, {brawler: at(1), bear: at(2)})
        settle(game)
        assert pt(game, brawler) == (4, 4)
        assert pt(game, bear) == (2, 2), "the bear has no melee"

    def test_opponents_not_creatures(self, builder):
        """Two creatures at one opponent are one opponent."""
        game = position(builder, mine=(BRAWLER, BEAR, BEAR))
        brawler = only_oid(game, BRAWLER, 0)
        bears = oids_of(game, BEAR, 0)
        declare(game, {brawler: at(1), bears[0]: at(1), bears[1]: at(1)})
        settle(game)
        assert pt(game, brawler) == (3, 3)

    def test_a_creature_that_does_not_attack_does_not_trigger(self, builder):
        game = position(builder, mine=(BRAWLER, BEAR))
        brawler, bear = only_oid(game, BRAWLER, 0), only_oid(game, BEAR, 0)
        declare(game, {bear: at(1)})
        assert not game.state.stack
        settle(game)
        assert pt(game, brawler) == (2, 2)

    def test_the_bonus_lasts_until_end_of_turn(self, builder):
        game = position(builder, players=2)
        brawler = only_oid(game, BRAWLER, 0)
        declare(game, {brawler: at(1)})
        settle(game)
        assert pt(game, brawler) == (3, 3)
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        assert pt(game, brawler) == (3, 3)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert pt(game, brawler) == (2, 2)


class TestGrantedMelee:
    def test_a_granted_melee_triggers_for_each_creature(self, builder):
        game = position(builder, mine=(TITANIA, BEAR, BEAR))
        bears = oids_of(game, BEAR, 0)
        titania = only_oid(game, TITANIA, 0)
        assert all("melee" in keywords(game, b) for b in bears)
        declare(game, {bears[0]: at(1), bears[1]: at(2), titania: at(1)})
        settle(game)
        assert [pt(game, b) for b in bears] == [(4, 4), (4, 4)]
        assert pt(game, titania) == (6, 6), "her printed melee, once: 'other creatures'"

    def test_without_the_grant_a_bear_is_silent(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        declare(game, {bear: at(1)})
        assert not game.state.stack


class TestThisCombat:
    def test_a_second_combat_counts_only_its_own_attacks(self, builder):
        game = position(builder, mine=(BRAWLER, BEAR))
        brawler, bear = only_oid(game, BRAWLER, 0), only_oid(game, BEAR, 0)
        declare(game, {brawler: at(1), bear: at(2)})
        settle(game)
        assert pt(game, brawler) == (4, 4)
        assert grant_extra_phases(game.state, ["combat"]) == ["combat"]
        untap_permanent(game.state, brawler)
        pass_until(
            game,
            lambda g: g.state.extra_phases_taken >= 1
            and g.pending() is not None
            and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        assert opponents_attacked(game) == 0, "a new combat starts from nought"
        declare(game, {brawler: at(1)})
        settle(game)
        assert pt(game, brawler) == (5, 5), "+2 from the first combat, +1 from the second"


class TestPlaneswalkersAndRemovedAttackers:
    def test_attacking_only_a_planeswalker_counts_its_controller(self, builder):
        """702.121b: the controller of an attacked planeswalker is counted."""
        game = position(builder, theirs={1: [WALKER]})
        brawler = only_oid(game, BRAWLER, 0)
        declare(game, {brawler: TargetRef.obj(only_oid(game, WALKER, 1))})
        settle(game)
        assert pt(game, brawler) == (3, 3)

    def test_a_walker_and_its_controller_are_one_opponent(self, builder):
        game = position(builder, mine=(BRAWLER, BEAR), theirs={1: [WALKER]})
        brawler, bear = only_oid(game, BRAWLER, 0), only_oid(game, BEAR, 0)
        declare(game, {brawler: TargetRef.obj(only_oid(game, WALKER, 1)), bear: at(1)})
        settle(game)
        assert pt(game, brawler) == (3, 3)

    def test_an_attacker_removed_before_resolution_still_counts(self, builder):
        """Counted on resolution, of the opponents you attacked -- not those still attacked."""
        game = position(builder, mine=(BRAWLER, BEAR))
        brawler, bear = only_oid(game, BRAWLER, 0), only_oid(game, BEAR, 0)
        declare(game, {brawler: at(1), bear: at(2)})
        assert game.state.stack, "the trigger is waiting to resolve"
        move_object(game.state, bear, Zone.GRAVEYARD)
        settle(game)
        assert pt(game, brawler) == (4, 4)


class TestTheValue:
    def test_only_the_attacking_player_has_attacked_anyone(self, builder):
        game = position(builder, mine=(BEAR,))
        declare(game, {only_oid(game, BEAR, 0): at(1)})
        assert opponents_attacked(game, 0) == 1
        assert opponents_attacked(game, 1) == 0

    def test_cleanup_clears_it(self, builder):
        game = position(builder, mine=(BEAR,))
        declare(game, {only_oid(game, BEAR, 0): at(1)})
        game.state.turn_ledger.clear()
        assert opponents_attacked(game) == 0

    def test_a_player_spec_loads(self):
        validate_value(VALUE, "test")

    @pytest.mark.parametrize("bad", [True, None, 3, {"you": True}, "everyone"])
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(DslError, match="opponents_attacked_this_combat"):
            validate_value({"opponents_attacked_this_combat": bad}, "test")
