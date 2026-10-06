"""Legions to Ashes — "…and all tokens that player controls with the same name".

    "Exile target nonland permanent an opponent controls and all tokens that
    player controls with the same name as that permanent."

`name` cannot say it, for `shares_a_type_with`'s reason word for word: `name`
takes a literal string fixed when the card is written, and which name matters
here is decided by whatever the spell targeted. So this is the same shape one
column over — a clause naming a **binding** rather than a value — and it is the
third of the family, after type and colour.

Two properties it shares with those two, and one it deliberately does not:

- an unbound name matches nothing rather than everything, because a card that
  bound the wrong thing should exile nothing rather than the board;
- the exclusion half of "…**and** all tokens" is `exclude_binding`'s job, not
  this clause's, exactly as radiance splits it;
- but unlike them it **tolerates a target that has already left the
  battlefield**. Legions to Ashes exiles the target and its copies in one
  breath, and the two `exile` ops have to run in some order. If reading the
  name required the target still to be in play, running the target's exile
  first would leave the token sweep matching nothing — a spell that silently
  did half of what it prints, which is the exact failure the whole pipeline
  exists to prevent. The name is read off the card, and a card does not stop
  having a name when the permanent changes zone.

The name comes from `card.name` rather than the characteristics layer because
nothing in that layer renames an object; types, colours, power and keywords are
what it models.
"""

from __future__ import annotations

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool, validate_selector
from automtg.engine.enums import Zone
from automtg.engine.zones import move_object

FOREST = "forest"
BEAR = "t_bear"
ARTIFACT = "t_artifact_blocker"


def ctx_for(game, bound: int | None = None, controller: int = 0):
    ctx = EffectContext(state=game.state, controller=controller)
    if bound is not None:
        ctx.bindings["it"] = bound
    return ctx


def nonlands(game, pid: int = 0):
    return [o for o in game.state.battlefield_objects(pid) if o.def_id != FOREST]


class TestItMatchesOnName:
    def test_two_copies_of_a_card_share_a_name(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)
        first, second = (o.oid for o in nonlands(game))

        pool = resolve_pool(ctx_for(game, first), {"shares_a_name_with": "it"})

        assert set(pool) == {first, second}

    def test_a_differently_named_permanent_does_not_match(self, builder):
        game = (
            builder(players=2).battlefield(0, [BEAR, ARTIFACT]).build(advance=False)
        )
        bear, _artifact = (o.oid for o in nonlands(game))

        pool = resolve_pool(ctx_for(game, bear), {"shares_a_name_with": "it"})

        assert pool == [bear]

    def test_other_excludes_the_bound_object(self, builder):
        """The "and all *tokens*" half is a separate clause, as with radiance."""
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)
        first, second = (o.oid for o in nonlands(game))

        pool = resolve_pool(
            ctx_for(game, first),
            {"shares_a_name_with": "it", "exclude_binding": "it"},
        )

        assert pool == [second]

    def test_it_reaches_across_controllers(self, builder):
        """"…that **player** controls" is `controller`'s job, not this clause's."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        mine = nonlands(game, 0)[0].oid
        theirs = nonlands(game, 1)[0].oid

        pool = resolve_pool(
            ctx_for(game, mine), {"controller": "any", "shares_a_name_with": "it"}
        )

        assert set(pool) == {mine, theirs}


class TestTheTargetMayAlreadyBeGone:
    """The property that separates this clause from its two siblings."""

    def test_a_target_moved_to_exile_still_names_its_copies(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)
        first, second = (o.oid for o in nonlands(game))

        move_object(game.state, first, Zone.EXILE, cause="test")

        pool = resolve_pool(
            ctx_for(game, first),
            {"shares_a_name_with": "it", "exclude_binding": "it"},
        )

        assert pool == [second], "the sweep must not depend on op ordering"


class TestTheUnboundCase:
    def test_an_unbound_name_matches_nothing(self, builder):
        """Exiling nothing is the safe failure; exiling everything is not."""
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)

        pool = resolve_pool(ctx_for(game), {"shares_a_name_with": "nobody"})

        assert pool == []


class TestTheLoader:
    def test_the_key_is_known(self):
        validate_selector({"shares_a_name_with": "it"}, "test")
