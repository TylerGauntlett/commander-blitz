"""Exalted (702.83) -- a keyword whose whole content is a rules-supplied trigger.

    "Exalted (Whenever a creature you control attacks alone, that creature
    gets +1/+1 until end of turn.)"

Printed exalted was always expressible as a `you_attack` trigger with one
creature in its ``attackers`` binding (Noble Hierarch is written that way).
What was not is Merchant of Truth's "Clues you control **have exalted**": a
grant needs a `Keyword` to grant, and the granted keyword has to *trigger*.
So the trigger is `carddef.EXALTED_TRIGGER`, yielded by
`triggers._candidate_abilities` for every permanent whose derived keywords
include exalted, with that permanent as its source.

The rules points, each with a test:

- 506.5 -- "attacks alone" is the only creature declared as an attacker; a
  second attacker means no trigger at all.
- 702.83b -- each exalted permanent triggers separately, so two give +2/+2,
  and the attacker's own exalted counts.
- Exalted is "a creature **you** control": an opponent's exalted is silent.
- A granted exalted triggers, and stops once the grant is gone.
- +1/+1 until end of turn: it wears off at cleanup.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import attack_with, find_action, only_oid, pass_until, pt, settle

SQUIRE = "t_ex_squire"
MERCHANT = "t_ex_merchant"
CLUE = "t_ex_clue"
BEAR = "t_bear"  # 2/2, no abilities


def position(builder, mine=(), theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    return game


def declare(game, *card_ids: str) -> None:
    for card_id in card_ids:
        attack_with(game, only_oid(game, card_id, 0))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    settle(game)


class TestAttackingAlone:
    def test_one_exalted_permanent_pumps_the_lone_attacker(self, builder):
        game = position(builder, mine=[SQUIRE, BEAR])
        declare(game, BEAR)
        assert pt(game, only_oid(game, BEAR, 0)) == (3, 3)

    def test_a_second_attacker_means_no_trigger(self, builder):
        game = position(builder, mine=[SQUIRE, BEAR, "t_flyer"])
        declare(game, BEAR, "t_flyer")
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2)
        assert not game.state.stack

    def test_the_attackers_own_exalted_counts(self, builder):
        game = position(builder, mine=[SQUIRE])
        declare(game, SQUIRE)
        assert pt(game, only_oid(game, SQUIRE, 0)) == (2, 2)


class TestEachInstanceTriggersSeparately:
    def test_two_exalted_permanents_give_plus_two(self, builder):
        game = position(builder, mine=[SQUIRE, SQUIRE, BEAR])
        declare(game, BEAR)
        assert pt(game, only_oid(game, BEAR, 0)) == (4, 4)

    def test_an_opponents_exalted_is_silent(self, builder):
        game = position(builder, mine=[BEAR], theirs=[SQUIRE])
        declare(game, BEAR)
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2)


class TestGrantedExalted:
    def test_a_clue_granted_exalted_triggers(self, builder):
        game = position(builder, mine=[MERCHANT, CLUE, BEAR])
        declare(game, BEAR)
        assert pt(game, only_oid(game, BEAR, 0)) == (3, 3)

    def test_without_the_grant_the_clue_is_silent(self, builder):
        game = position(builder, mine=[CLUE, BEAR])
        declare(game, BEAR)
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2)


class TestItWearsOff:
    def test_the_pump_ends_with_the_turn(self, builder):
        game = position(builder, mine=[SQUIRE, BEAR])
        declare(game, BEAR)
        bear = only_oid(game, BEAR, 0)
        assert pt(game, bear) == (3, 3)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert pt(game, bear) == (2, 2)
