"""Radiance — "…and each other creature that shares a color with it".

    Skyknight Legionnaire's cycle: "Radiance — Target creature and each other
    creature that shares a color with it get +2/+2 until end of turn."

`colors` cannot say it, and the reason is `shares_a_type_with`'s reason word for
word: `colors` takes a literal list fixed when the card is written, and which
colour matters here is decided by whatever the spell targeted. So it is the same
shape one column over — a clause naming a **binding** rather than a value.

Two things it inherits from that clause and one it does not:

- both sides are read off **derived** colours, so a creature made black by
  another spell is caught;
- an unbound name matches nothing rather than everything, because a card that
  bound the wrong thing should do nothing rather than pump the board;
- and the boundary is intimidate's, not landwalk's: a **colorless** creature
  shares a colour with nothing, so radiance off an artifact creature hits only
  the target. Reading the clause as "is not a different colour" would invert
  exactly that case, and on a board of coloured creatures the two look identical.
"""

from __future__ import annotations

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool, validate_selector

FOREST = "forest"
BEAR = "t_bear"              # green
BOLT = "t_bolt"              # a red instant, for a red permanent stand-in
ARTIFACT = "t_artifact_blocker"


def ctx_for(game, bound: int | None = None, controller: int = 0):
    ctx = EffectContext(state=game.state, controller=controller)
    if bound is not None:
        ctx.bindings["it"] = bound
    return ctx


def creatures(game, pid: int = 0):
    return [o for o in game.state.battlefield_objects(pid) if o.def_id != FOREST]


class TestItMatchesOnColour:
    def test_a_creature_of_the_same_colour_matches(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)
        first, second = (o.oid for o in creatures(game))

        pool = resolve_pool(ctx_for(game, first), {"shares_a_color_with": "it"})

        assert set(pool) == {first, second}, "both green"

    def test_other_excludes_the_bound_object(self, builder):
        """"…and each **other** creature" — `exclude_binding` does that half."""
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)
        first, second = (o.oid for o in creatures(game))

        pool = resolve_pool(
            ctx_for(game, first),
            {"shares_a_color_with": "it", "exclude_binding": "it"},
        )

        assert pool == [second]

    def test_a_creature_of_another_colour_does_not_match(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .battlefield(1, [ARTIFACT])
            .build(advance=False)
        )
        bear = creatures(game)[0].oid

        pool = resolve_pool(
            ctx_for(game, bear), {"controller": "any", "shares_a_color_with": "it"}
        )

        assert pool == [bear], "the artifact is colorless"


class TestTheColorlessBoundary:
    def test_a_colorless_object_shares_with_nothing(self, builder):
        """Not even itself — which is the case "not a different colour" inverts."""
        game = (
            builder(players=2)
            .battlefield(0, [ARTIFACT])
            .battlefield(1, [ARTIFACT])
            .build(advance=False)
        )
        mine = creatures(game)[0].oid

        pool = resolve_pool(
            ctx_for(game, mine), {"controller": "any", "shares_a_color_with": "it"}
        )

        assert pool == [], "colorless shares a colour with nothing at all"


class TestTheUnboundCase:
    def test_an_unbound_name_matches_nothing(self, builder):
        """A card that bound the wrong thing must do nothing, not everything."""
        game = builder(players=2).battlefield(0, [BEAR, BEAR]).build(advance=False)

        pool = resolve_pool(ctx_for(game), {"shares_a_color_with": "nobody"})

        assert pool == []


class TestTheLoader:
    def test_the_key_is_known(self):
        validate_selector({"shares_a_color_with": "it"}, "test")


class TestSelfIsTheAbilitysSource:
    """Kasmina, Enigma Sage: "…an instant or sorcery card that shares a color
    with **this planeswalker**." `"self"` names the ability's source rather than
    a binding, so a granted copy reads the walker that has it."""

    def _game(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [FOREST, BEAR, BEAR, ARTIFACT])
            .build(advance=False)
        )

    def test_a_green_source_finds_the_green_creature(self, builder):
        game = self._game(builder)
        source, other = [o.oid for o in creatures(game) if o.def_id == BEAR]
        ctx = EffectContext(state=game.state, controller=0, source_oid=source)
        pool = resolve_pool(ctx, {"zone": "battlefield", "shares_a_color_with": "self"})
        assert other in pool

    def test_a_colorless_permanent_is_not_found(self, builder):
        game = self._game(builder)
        source = next(o.oid for o in creatures(game) if o.def_id == BEAR)
        artifact = next(o.oid for o in creatures(game) if o.def_id == ARTIFACT)
        ctx = EffectContext(state=game.state, controller=0, source_oid=source)
        pool = resolve_pool(ctx, {"zone": "battlefield", "shares_a_color_with": "self"})
        assert artifact not in pool

    def test_with_no_source_nothing_matches(self, builder):
        game = self._game(builder)
        ctx = EffectContext(state=game.state, controller=0)
        assert resolve_pool(ctx, {"zone": "battlefield", "shares_a_color_with": "self"}) == []
