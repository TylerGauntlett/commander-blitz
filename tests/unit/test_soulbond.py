"""Soulbond — a relationship between two permanents that is not attachment.

    "Soulbond (You may pair this creature with another unpaired creature when
    either enters. They remain paired for as long as you control both.)
     As long as this creature is paired with another creature, both creatures
     get +1/+1."

The census filed this as "a paired-permanent relationship with no
representation". `attached_to` is the nearest thing in the engine and is wrong
in two independent ways, either of which is enough:

- **It is one-way.** "Both creatures get +1/+1" is asked of the partner as well
  as of the source, and a one-sided link buffs exactly one of the two.
- **An Aura attached to nothing dies.** A state-based action puts it in its
  owner's graveyard; a creature whose partner died is simply unpaired. Two
  lifetimes, so two fields — the argument `frozen_by` and `skip_next_untap`
  already made.

So `paired_with` is symmetric, and breaking it is two writes: the leaving
object's own is cleared by `reset_permanent_state`, and the **partner's** has to
be cleared in `_detach_all`, because nothing else walks back along the link and
a creature left pointing at a card in a graveyard would keep the bonus for ever.

The static is written once and applies to two creatures, which is why there are
two filter keys: `paired` is "this creature, while it has a partner", and
`paired_with_source` is "the partner".
"""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind
from automtg.engine.zones import destroy
from tests.conftest import _default_answer, action_for_card, only_oid, pass_until

PLAINS = "plains"
ELDER = "t_soulbond"      # {2}{W} 2/2, soulbond, +1/+1 to both
BEAR = "t_bear"           # 2/2


def position(builder, others: list[str]):
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 3)
        .battlefield(0, others)
        .hand(0, [ELDER])
        .library(0, [PLAINS] * 20)
        .library(1, [PLAINS] * 20)
        .build()
    )


def play_the_elder(game):
    game.apply(action_for_card(game, ActionKind.CAST, ELDER))
    for _ in range(60):
        if game.state.stack:
            decision = game.pending()
            if decision is None:
                break
            game.apply(_default_answer(game, decision))
            continue
        pool = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
        if pool:
            game.apply(pool[0])
            continue
        break
    pass_until(game, lambda g: g.pending() is None or not g.state.stack)


class TestThePairing:
    def test_the_link_is_symmetric(self, builder):
        game = position(builder, [BEAR])
        play_the_elder(game)
        elder, bear = only_oid(game, ELDER), only_oid(game, BEAR)

        assert game.state.objects[elder].paired_with == bear
        assert game.state.objects[bear].paired_with == elder

    def test_nothing_to_pair_with_is_fine(self, builder):
        game = position(builder, [])
        play_the_elder(game)
        elder = only_oid(game, ELDER)

        assert game.state.objects[elder].paired_with is None

    def test_an_already_paired_creature_is_not_offered(self, builder):
        """702.94a, and it is also what stops one creature holding two partners."""
        game = position(builder, [BEAR, ELDER])
        first = only_oid(game, ELDER)
        game.state.objects[first].paired_with = only_oid(game, BEAR)
        game.state.objects[only_oid(game, BEAR)].paired_with = first

        play_the_elder(game)

        newcomer = next(
            o.oid
            for o in game.state.battlefield_objects(0)
            if o.def_id == ELDER and o.oid != first
        )
        assert game.state.objects[newcomer].paired_with is None


class TestTheStatic:
    def test_both_creatures_get_the_bonus(self, builder):
        """The whole reason the link is symmetric."""
        game = position(builder, [BEAR])
        play_the_elder(game)
        elder, bear = only_oid(game, ELDER), only_oid(game, BEAR)

        assert chars(game.state, elder).power == 3
        assert chars(game.state, bear).power == 3

    def test_an_unpaired_soulbond_creature_gets_nothing(self, builder):
        game = position(builder, [])
        play_the_elder(game)
        elder = only_oid(game, ELDER)

        assert chars(game.state, elder).power == 2

    def test_a_third_creature_gets_nothing(self, builder):
        game = position(builder, [BEAR, BEAR])
        play_the_elder(game)
        elder = only_oid(game, ELDER)
        partner = game.state.objects[elder].paired_with
        others = [
            o.oid
            for o in game.state.battlefield_objects(0)
            if o.def_id == BEAR and o.oid != partner
        ]

        assert chars(game.state, others[0]).power == 2


class TestBreakingThePair:
    def test_the_survivor_is_unpaired(self, builder):
        """The write nothing else would do -- and the bonus would be permanent."""
        game = position(builder, [BEAR])
        play_the_elder(game)
        elder, bear = only_oid(game, ELDER), only_oid(game, BEAR)

        destroy(game.state, bear)
        pass_until(game, lambda g: g.pending() is None or not g.state.stack)

        assert game.state.objects[elder].paired_with is None
        assert chars(game.state, elder).power == 2
