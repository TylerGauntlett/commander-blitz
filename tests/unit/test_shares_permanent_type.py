"""Sharing a *permanent type*, as opposed to a creature type.

    Cloudstone Curio — "Whenever a nonartifact permanent you control enters, you
    may return another permanent you control that shares a permanent type with
    it to its owner's hand."

The selector language already had two dynamic "shares a … with" clauses —
`shares_a_type_with`, which intersects **subtypes**, and `shares_a_color_with`,
which intersects colours. This is the third member of that family and reads
`types`.

It is a separate key rather than a mode of the subtype one because the wrong
reading is *quietly narrower*, which is the failure this pipeline exists to
prevent. Written with `shares_a_type_with`, Cloudstone Curio would find another
Goblin when a Goblin entered, and **nothing at all** when a land, a typeless
artifact, or any permanent without shared creature types entered — a card that
loads clean, prints the right sentence and does a fraction of what it says.

A literal `types` list cannot stand in either: which permanent type matters is
decided at resolution by whatever just entered, not when the card is written.

Two things worth pinning beyond the happy path:

- **An artifact creature matches both pools** (205.2a — an object can have
  several card types, and "a permanent type" is satisfied by any one of them).
- **"Another"** is `exclude_binding`, not this clause. A permanent trivially
  shares a type with itself, so without the exclusion the card would bounce the
  permanent that just entered every time, which is a different and much worse
  card.
"""

from __future__ import annotations

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from tests.conftest import only_oid

BEAR = "t_bear"
DORK = "t_dork"
ARTIFACT_CREATURE = "t_artifact_blocker"
PLAIN_ARTIFACT = "t_toll_gate"


def _pool(game, subject_oid: int, **extra):
    """Everything `shares_permanent_type_with: "subject"` would offer."""
    ctx = EffectContext(state=game.state, controller=0, source_name="probe")
    ctx.bindings["subject"] = subject_oid
    selector = {
        "zone": "battlefield",
        "controller": "you",
        "shares_permanent_type_with": "subject",
        "count": "all",
        **extra,
    }
    return set(resolve_pool(ctx, selector))


class TestItReadsCardTypesNotSubtypes:
    def test_a_creature_finds_the_other_creatures(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "island"])
            .battlefield(0, [BEAR, DORK])
            .build()
        )
        bear = only_oid(game, BEAR)
        dork = only_oid(game, DORK)
        pool = _pool(game, bear)
        assert dork in pool, "a creature did not find the other creature"

    def test_a_creature_does_not_find_a_land(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "island"])
            .battlefield(0, [BEAR])
            .build()
        )
        forest = only_oid(game, "forest")
        assert forest not in _pool(game, only_oid(game, BEAR))

    def test_a_land_finds_the_other_lands(self, builder):
        """The case the subtype reading gets wrong and silently.

        Forest and Island share no subtype, so `shares_a_type_with` would return
        nothing here — the card would look implemented and do nothing whenever a
        land entered.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest", "island"])
            .battlefield(0, [BEAR])
            .build()
        )
        island = only_oid(game, "island")
        pool = _pool(game, island)
        assert only_oid(game, "forest") in pool, (
            "an Island did not find a Forest -- this is the subtype reading, "
            "not the card-type one"
        )
        assert only_oid(game, BEAR) not in pool

    def test_two_creatures_of_different_subtypes_still_match(self, builder):
        """The positive half of the same point: no shared subtype needed."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [BEAR, DORK])
            .build()
        )
        from automtg.engine.characteristics import chars

        bear, dork = only_oid(game, BEAR), only_oid(game, DORK)
        assert not (set(chars(game.state, bear).subtypes) & set(chars(game.state, dork).subtypes)), (
            "the fixture creatures share a subtype, so this test proves nothing"
        )
        assert dork in _pool(game, bear)


class TestSeveralCardTypes:
    """205.2a: an object can have more than one card type, and the printed "a
    permanent type" is satisfied by any one of them."""

    def test_an_artifact_creature_finds_both_pools(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [ARTIFACT_CREATURE, BEAR, PLAIN_ARTIFACT])
            .build()
        )
        pool = _pool(game, only_oid(game, ARTIFACT_CREATURE))
        assert only_oid(game, BEAR) in pool, "did not reach the creatures"
        assert only_oid(game, PLAIN_ARTIFACT) in pool, "did not reach the artifacts"

    def test_a_plain_creature_does_not_reach_the_artifacts(self, builder):
        """The other direction, and the one an over-wide intersection breaks."""
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [BEAR, PLAIN_ARTIFACT])
            .build()
        )
        assert only_oid(game, PLAIN_ARTIFACT) not in _pool(game, only_oid(game, BEAR))


class TestTheBoundaries:
    def test_another_is_the_exclusion_not_this_clause(self, builder):
        """A permanent shares a type with itself, so `exclude_binding` carries
        the printed "another" -- without it the card bounces what just entered.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["forest"])
            .battlefield(0, [BEAR, DORK])
            .build()
        )
        bear = only_oid(game, BEAR)
        assert bear in _pool(game, bear), "self-match is the clause working"
        assert bear not in _pool(game, bear, exclude_binding="subject")

    def test_an_unbound_name_matches_nothing(self, builder):
        """Fails closed, as every other `_bound_oid` clause does."""
        game = builder(players=2).battlefield(0, ["forest", BEAR]).build()
        ctx = EffectContext(state=game.state, controller=0, source_name="probe")
        pool = resolve_pool(
            ctx,
            {
                "zone": "battlefield",
                "controller": "you",
                "shares_permanent_type_with": "nothing_bound_here",
                "count": "all",
            },
        )
        assert list(pool) == []
