""""Whenever you cast a spell, **if mana from a Treasure was spent** to cast it…"

    Smaug, Wicked Worm.

The engine already remembered *which permanent* made the mana a spell was paid
with -- `paid_by` and `GameObject.mana_sources_spent`, Path of Ancestry's "when
**that** mana is spent". That answers a question about one named object, and
this sentence asks about a whole class of them: an arbitrary number of Treasure
tokens Smaug did not make and cannot name. No card can write another object's
oid, and `"self"` would ask about mana Smaug produced, which is none -- a
quietly dead line rather than an approximation.

**The recorded oid could not have been looked up anyway**, and that is the half
of this capability that is not a filter key. A Treasure *sacrifices itself* to
make its mana, and `sba._tokens_and_attachments` pops a token that has left the
battlefield straight out of `state.objects`. By the time the spell is on the
stack the oid in `mana_sources_spent` resolves to nothing at all, so a subtype
test against it would match nothing -- silently, which is the dangerous
direction for a filter.

So the provenance is captured where it is still knowable: `Pip` gained
`source_traits`, a `ManaOrigin` snapshot of what the source *was* -- name,
types, subtypes, supertypes, controller -- taken by `characteristics.
mana_source_traits` before the ability's own cost runs, and carried by `spend`
onto the spell as `GameObject.mana_spent_traits`. Characteristics travelling
with the mana, rather than a pointer back to an object that may be gone.

`Game._activate_mana` takes the snapshot rather than `costs.
activate_mana_ability`, and the difference is exactly this card: that path pays
the ability's cost *first*, so the Treasure is already sacrificed by the time
the mana is added. The solver's path never sacrifices anything and snapshots for
itself.

The negative is half the card: the same creature, the same spell, cast off
lands, must not draw or lose any life. A `spell_cast` trigger without the filter
is a strictly better card -- it would fire on every spell.
"""

from __future__ import annotations

from automtg.engine.characteristics import mana_source_traits
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.mana import ManaCost, ManaOrigin, ManaPool
from tests.conftest import only_oid, pass_until

WORM = "t_hoard_worm"
TREASURE = "treasure_token"
BEAR = "t_bear"  # a Bear, {1}{G}

TREASURE_TRAITS = ManaOrigin(
    oid=1, name="Treasure", types=frozenset({"Artifact"}), subtypes=frozenset({"Treasure"})
)
FOREST_TRAITS = ManaOrigin(oid=2, name="Forest", types=frozenset({"Land"}))


def spend(cost: str, pool: ManaPool):
    return pool.spend(ManaCost.parse(cost).with_x(0))


class TestThePipCarriesWhatMadeIt:
    """The pool half, in isolation: an oid is not enough, so the pip carries
    characteristics beside it."""

    def test_a_tagged_pip_reports_its_source_traits(self):
        pool = ManaPool()
        pool.add("G", 1, source=1, source_traits=TREASURE_TRAITS)
        assert spend("{G}", pool).source_traits == {TREASURE_TRAITS}

    def test_the_oid_is_still_reported_beside_it(self):
        """Path of Ancestry's question has to keep working: the two halves
        answer different sentences and neither replaces the other."""
        pool = ManaPool()
        pool.add("G", 1, source=1, source_traits=TREASURE_TRAITS)
        result = spend("{G}", pool)
        assert result.sources == {1}
        assert result.source_traits == {TREASURE_TRAITS}

    def test_mana_from_an_effect_carries_nothing(self):
        pool = ManaPool()
        pool.add("G", 1)
        assert spend("{G}", pool).source_traits == frozenset()

    def test_generic_carries_provenance_too(self):
        """The Treasure's mana usually pays a generic pip, so a reading that
        only watched coloured pips would miss the whole card."""
        pool = ManaPool()
        pool.add("G", 1, source=1, source_traits=TREASURE_TRAITS)
        pool.add("G", 1, source=2, source_traits=FOREST_TRAITS)
        assert spend("{2}", pool).source_traits == {TREASURE_TRAITS, FOREST_TRAITS}

    def test_only_the_pips_actually_spent_are_reported(self):
        pool = ManaPool()
        pool.add("G", 1, source=2, source_traits=FOREST_TRAITS)
        pool.add("G", 1, source=1, source_traits=TREASURE_TRAITS)
        # `_take` is newest-first, so the Treasure's pip is the one spent.
        assert spend("{G}", pool).source_traits == {TREASURE_TRAITS}

    def test_two_identical_treasures_do_not_collapse(self):
        """The oid rides along inside the snapshot, so a set of them still
        counts two Treasures as two."""
        other = TREASURE_TRAITS._replace(oid=9)
        pool = ManaPool()
        pool.add("G", 1, source=1, source_traits=TREASURE_TRAITS)
        pool.add("G", 1, source=9, source_traits=other)
        assert spend("{2}", pool).source_traits == {TREASURE_TRAITS, other}

    def test_a_copy_carries_the_traits(self):
        pool = ManaPool()
        pool.add("G", 1, source=1, source_traits=TREASURE_TRAITS)
        assert spend("{G}", pool.copy()).source_traits == {TREASURE_TRAITS}

    def test_tags_and_amounts_stay_the_same_length(self):
        pool = ManaPool()
        pool.add("G", 3, source=1, source_traits=TREASURE_TRAITS)
        spend("{2}", pool)
        assert [len(t) for t in pool.tags] == pool.amounts


def board(builder, *, treasures: int = 1, forests: int = 2):
    """The Worm already on the battlefield, plus a Bear to cast off Treasures.

    `GameBuilder.battlefield` places *cards*, and a Treasure is a token. The
    difference is the whole point of this file -- `sba._tokens_and_attachments`
    pops a token out of `state.objects` the moment it leaves the battlefield and
    leaves an ordinary card sitting in the graveyard -- so the flag is set here
    rather than relying on the placed permanent to behave like one.
    """
    game = (
        builder(players=2)
        .battlefield(0, [WORM] + [TREASURE] * treasures + ["forest"] * forests)
        .hand(0, [BEAR])
        .library(0, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    for obj in game.state.objects.values():
        if obj.def_id == TREASURE:
            obj.is_token = True
    return game


def tap_the_treasure(game, oid: int) -> None:
    """Activate the Treasure by hand -- it sacrifices itself for the mana, so
    the payment solver never offers it."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and a.source == oid
            and a.mana_option is not None
        )
    )


def cast_the_bear(game) -> int:
    """Cast it, and return the spell's oid.

    Read off the action rather than off `state.stack`, because an oid survives
    the zone change (400.7 is a documented simplification here) and the Bear has
    already resolved onto the battlefield by the time `apply` returns -- both
    players pass on an empty decision queue. `mana_spent_traits` is not cleared
    by `reset_permanent_state`, exactly as `mana_sources_spent` is not.
    """
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == BEAR
    )
    game.apply(action)
    return action.source


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def worm_triggers(game) -> list:
    return [
        e
        for e in game.state.events
        if e.type == "ability_triggered" and e.data.get("card") == WORM
    ]


class TestTheSnapshotOutlivesTheTreasure:
    def test_the_spell_remembers_a_treasure_paid(self, builder):
        game = board(builder)
        treasure = only_oid(game, TREASURE)
        tap_the_treasure(game, treasure)
        spell = game.state.objects[cast_the_bear(game)]
        assert treasure not in game.state.objects, (
            "the sacrificed token is still in state.objects -- this test is no "
            "longer exercising the case the capability exists for"
        )
        assert any(
            "Treasure" in origin.subtypes for origin in spell.mana_spent_traits
        )

    def test_the_oid_it_recorded_is_unresolvable(self, builder):
        """Precisely why a selector-valued `paid_by` alone would not have
        worked: the oid is there and points at nothing."""
        game = board(builder)
        treasure = only_oid(game, TREASURE)
        tap_the_treasure(game, treasure)
        spell = game.state.objects[cast_the_bear(game)]
        assert treasure in spell.mana_sources_spent
        assert game.state.objects.get(treasure) is None

    def test_the_trigger_fires(self, builder):
        game = board(builder)
        tap_the_treasure(game, only_oid(game, TREASURE))
        cast_the_bear(game)
        settle(game)
        assert worm_triggers(game), "the Worm's trigger never fired"

    def test_it_draws_a_card_and_loses_one_life(self, builder):
        game = board(builder)
        before_life = game.state.players[0].life
        before_hand = len(game.state.players[0].hand)
        tap_the_treasure(game, only_oid(game, TREASURE))
        cast_the_bear(game)
        settle(game)
        # The Bear left the hand and one card was drawn.
        assert len(game.state.players[0].hand) == before_hand
        assert game.state.players[0].life == before_life - 1


class TestTheFilterStillNarrows:
    def test_a_spell_paid_for_off_lands_does_not_fire_it(self, builder):
        """A bare `spell_cast` with no filter is a strictly better card. The
        same Worm, the same Bear, no Treasure tapped."""
        game = board(builder, treasures=1, forests=3)
        cast_the_bear(game)
        settle(game)
        assert not worm_triggers(game)

    def test_the_life_is_not_lost_either(self, builder):
        game = board(builder, treasures=1, forests=3)
        before_life = game.state.players[0].life
        cast_the_bear(game)
        settle(game)
        assert game.state.players[0].life == before_life

    def test_a_land_that_paid_is_not_a_treasure(self, builder):
        """The snapshot is a real characteristic read, not a flag set on
        anything that makes mana."""
        game = board(builder, treasures=1, forests=3)
        forest = next(
            oid
            for oid, obj in game.state.objects.items()
            if obj.def_id == "forest" and obj.zone is Zone.BATTLEFIELD
        )
        traits = mana_source_traits(game.state, forest)
        assert traits is not None
        assert "Treasure" not in traits.subtypes
        assert "Land" in traits.types


class TestTheSnapshotItself:
    def test_it_reads_the_board(self, builder):
        game = board(builder)
        treasure = only_oid(game, TREASURE)
        traits = mana_source_traits(game.state, treasure)
        assert traits is not None
        assert traits.name == "Treasure"
        assert traits.subtypes == frozenset({"Treasure"})
        assert traits.types == frozenset({"Artifact"})
        assert traits.controller == 0

    def test_an_object_that_is_gone_snapshots_to_nothing(self, builder):
        """Unknown provenance does not establish "mana from a Treasure": the
        claim has to be positively made, so `None` matches no filter."""
        game = board(builder)
        assert mana_source_traits(game.state, 9999) is None
        assert mana_source_traits(game.state, None) is None
