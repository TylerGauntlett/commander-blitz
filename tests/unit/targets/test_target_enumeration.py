"""What ``enumerate_target_tuples`` offers, and in what order.

The list it returns is the action list: `legality` emits one action per tuple,
so anything missing here is a line of play the player cannot reach, and
anything ordered wrongly here is what a trigger picks when nobody is asked.
"""

from __future__ import annotations

from commanderblitz.engine.carddef import TargetSpec
from commanderblitz.engine.targeting import enumerate_target_tuples

CREATURE = {"types": ["Creature"], "zone": "battlefield"}


def spec(**kwargs) -> TargetSpec:
    return TargetSpec(id="t1", kind="permanent", selector=CREATURE, **kwargs)


def board(builder, creatures: int = 3):
    return builder(players=2).battlefield(0, ["grizzly_bears"] * creatures).build()


def tuples(game, target: TargetSpec, **kwargs):
    return enumerate_target_tuples(game.state, 0, [target], None, **kwargs)


class TestOptionalTargets:
    def test_declining_is_offered_even_when_targets_exist(self, builder):
        """The reported symptom: a mode you can never choose.

        Simic Charm's third mode gives *your permanents* hexproof and takes no
        target, so its single target spec is optional.  `optional` used to be
        honoured only when there were no candidates at all, which made that
        mode unreachable in any game with a creature on the battlefield -- the
        only games it is ever wanted in.
        """
        game = board(builder)
        out = tuples(game, spec(optional=True))
        assert () in out, "the spell can never decline its optional target"
        assert len(out) == 4, "three creatures plus declining"

    def test_a_trigger_asked_for_one_option_gets_a_real_target(self, builder):
        """Load-bearing ordering: whatever is not asked takes the first tuple.

        `stack.push_trigger` and `suspend.cast_suspended` both call this with
        ``limit=1`` and take ``options[0]``.  Put declining first and every
        triggered ability with an optional target silently does nothing.
        """
        game = board(builder)
        out = tuples(game, spec(optional=True), limit=1)
        assert out[0] != (), "a trigger taking options[0] would fizzle"

    def test_a_required_target_never_offers_the_empty_tuple(self, builder):
        game = board(builder)
        out = tuples(game, spec())
        assert () not in out
        assert len(out) == 3

    def test_no_candidates_still_collapses_to_declining(self, builder):
        game = board(builder, creatures=0)
        assert tuples(game, spec(optional=True)) == [()]
        assert tuples(game, spec()) == []

    def test_up_to_n_offers_the_full_set_before_declining(self, builder):
        """"Tap up to four target creatures" with two on board: both, or neither."""
        game = board(builder, creatures=2)
        out = tuples(game, spec(count=4, optional=True))
        assert out[-1] == (), "declining is the tail, not the default"
        assert len(out[0]) == 2, "the first choice takes every creature it can"

    def test_the_cap_eats_candidates_not_the_choice_to_decline(self, builder):
        game = board(builder, creatures=6)
        out = tuples(game, spec(optional=True), limit=4)
        assert len(out) == 4
        assert out[-1] == ()
