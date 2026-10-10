"""Excluding a whole set a binding holds, not merely its first member.

Martial Coup: "Create X 1/1 white Soldier creature tokens. If X is 5 or more,
destroy all other creatures."

"Other" here means *other than the ones this spell just made* — and no selector
can name them. `is_token: false` spares every unrelated token as well, and
reordering the wrath before the tokens changes the card: the creatures being
destroyed would no longer see the Soldiers arrive, so a `permanent_enters`
trigger on the opponent's board fires or does not fire depending on which half
ran first.

`create_token`'s `as` already recorded the set. What did not work was reading it
back: `exclude_binding` went through `_bound_oid`, the *singular* reader, which
returns `None` for a list — so the exclusion matched nothing and Martial Coup
wrathed the tokens it had made a moment earlier. Reading one oid out of the list
would have been worse than nothing, because it spares exactly one Soldier and
looks almost right on the board.

The set form is not new; `_bound_oids` has read it since amplify and devour.
Only this one call site was still asking the singular question.
"""

from __future__ import annotations

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.primitives import create_token
from tests.conftest import oids_of

BEAR = "t_bear"


def board(builder):
    """Two creatures already out, and a context to resolve selectors in."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains", BEAR])
        .battlefield(1, [BEAR])
        .build()
    )
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    return game, ctx


def all_creatures(ctx, **extra):
    return resolve_pool(
        ctx, {"zone": "battlefield", "types": ["Creature"], "count": "all", **extra}
    )


class TestExcludingASet:
    def test_every_member_of_the_binding_is_spared(self, builder):
        game, ctx = board(builder)
        made = create_token(game.state, "soldier_1_1_w", 0, 3)
        ctx.bindings["made"] = list(made)

        pool = all_creatures(ctx, exclude_binding="made")

        assert not set(pool) & set(made), "every token the spell made must be spared"
        assert len(pool) == 2, "the two pre-existing creatures are still destroyed"

    def test_it_spares_all_of_them_and_not_just_the_first(self, builder):
        """The failure this replaces looked almost right.

        A singular reader that happened to take `made[0]` would leave two
        Soldiers in the pool — a board a player would have to count to notice.
        """
        game, ctx = board(builder)
        made = create_token(game.state, "soldier_1_1_w", 0, 3)
        ctx.bindings["made"] = list(made)

        pool = all_creatures(ctx, exclude_binding="made")

        assert len(set(made) - set(pool)) == 3


class TestTheSingularFormStillWorks:
    def test_one_bound_oid_is_still_excluded(self, builder):
        """Shared Animosity's "each other attacking creature" is a bare oid."""
        game, ctx = board(builder)
        mine = oids_of(game, BEAR, 0)[0]
        ctx.bindings["subject"] = mine

        pool = all_creatures(ctx, exclude_binding="subject")

        assert mine not in pool
        assert len(pool) == 1

    def test_a_snapshot_binding_is_still_excluded(self, builder):
        """`snapshot` binds a dict; `_bound_oid` reads its `oid` key."""
        game, ctx = board(builder)
        mine = oids_of(game, BEAR, 0)[0]
        ctx.bindings["subject"] = {"oid": mine, "power": 2}

        assert mine not in all_creatures(ctx, exclude_binding="subject")

    def test_an_unbound_name_excludes_nothing(self, builder):
        _game, ctx = board(builder)

        assert len(all_creatures(ctx, exclude_binding="nobody")) == 2
