""""When that mana is spent to cast a creature spell…"

    Path of Ancestry, Opal Palace.

The pool had no provenance at all. `ManaPool` was six integers, so the moment a
land's mana landed in it, it was indistinguishable from every other mana of that
colour and "that mana" could not be identified at spend time.

Nothing existing comes close enough to stand in:

- `mana_restriction` ("spend this only to cast a creature spell") gates what
  *may* be paid and never reports what *was*, and it is deliberately implemented
  by filtering sources before the solver sees them rather than by tagging the
  pool. It cannot carry a rider.
- `delay` is the other shape of after-the-fact effect, but `DelayedTrigger.step`
  is matched against a turn *step*. It can say "at the beginning of the next end
  step" and cannot say "when this mana is spent".
- `spell_cast` alone fires for every spell regardless of what paid for it, so
  hanging the scry there is a strictly better card: it triggers on creature
  spells cast entirely off other lands.

So the pool gained per-pip provenance -- `tags[i]` holds one entry per pip of
`amounts[i]`, naming the permanent whose mana ability made it -- and `spend`
reports both halves of what a payment consumed: the colours (sunburst, converge)
and the permanents (this).

**The event is not new.** `pay_mana` already wrote `colors_spent` onto the spell
at the one instant it was knowable; the sources go onto the same object at the
same instant, and the trigger is an ordinary `spell_cast` with a `paid_by`
filter. A `mana_spent` event of its own would fire *during cost payment*, before
the spell is on the stack and before its own filter has anything to match.

**Which same-coloured pip gets spent** is the player's choice in the printed
rules; `_take` pops newest-first. That is the one bias matching how payment
actually runs -- `pay_mana` taps what it needs immediately before spending, so
the mana it just made is at the end of the list, and a Path of Ancestry tapped
*for* a spell pays for that spell.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, Step
from automtg.engine.mana import ManaCost, ManaPool
from tests.conftest import only_oid, pass_until

ANCESTRY = "t_ancestry"
BEAR = "t_bear"  # a Bear, {1}{G}
BEAR_COMMANDER = "t_bear"
BAT_COMMANDER = "t_bats"


def spend(cost: str, pool: ManaPool):
    return pool.spend(ManaCost.parse(cost).with_x(0))


class TestThePoolRemembers:
    def test_a_tagged_pip_names_its_source(self):
        pool = ManaPool()
        pool.add("G", 1, source=7)
        assert spend("{G}", pool).sources == {7}

    def test_untagged_mana_names_nobody(self):
        """Mana from an effect rather than from a permanent's ability."""
        pool = ManaPool()
        pool.add("G", 1)
        assert spend("{G}", pool).sources == frozenset()

    def test_generic_carries_provenance_too(self):
        """The cost has no coloured pip and the land still paid for it."""
        pool = ManaPool()
        pool.add("G", 1, source=7)
        pool.add("W", 1, source=9)
        assert spend("{2}", pool).sources == {7, 9}

    def test_colorless_is_not_a_colour_but_is_a_source(self):
        pool = ManaPool()
        pool.add("C", 1, source=7)
        result = spend("{1}", pool)
        assert result.colors == frozenset()
        assert result.sources == {7}

    def test_only_the_pips_actually_spent_are_reported(self):
        pool = ManaPool()
        pool.add("G", 1, source=7)
        pool.add("G", 1, source=9)
        assert len(spend("{G}", pool).sources) == 1

    def test_the_newest_pip_goes_first(self):
        """`pay_mana` taps what it needs immediately before spending, so the
        land tapped *for* this spell is the one at the end of the list."""
        pool = ManaPool()
        pool.add("G", 1, source=7)
        pool.add("G", 1, source=9)
        assert spend("{G}", pool).sources == {9}


class TestTheBookkeepingHolds:
    def test_tags_and_amounts_stay_the_same_length(self):
        pool = ManaPool()
        pool.add("G", 3, source=7)
        spend("{2}", pool)
        assert [len(t) for t in pool.tags] == pool.amounts

    def test_clearing_forgets_everything(self):
        pool = ManaPool()
        pool.add("G", 2, source=7)
        pool.clear()
        assert [len(t) for t in pool.tags] == pool.amounts == [0] * len(pool.amounts)

    def test_a_copy_carries_the_tags(self):
        pool = ManaPool()
        pool.add("G", 1, source=7)
        assert spend("{G}", pool.copy()).sources == {7}

    def test_a_copy_does_not_share_them(self):
        pool = ManaPool()
        pool.add("G", 1, source=7)
        spend("{G}", pool.copy())
        assert pool.amounts == pool.copy().amounts, "the original was drained"


def board(builder, commander: str):
    """The land already on the battlefield, untapped, and a Bear to cast."""
    return (
        builder(players=2)
        .battlefield(0, [ANCESTRY, "forest"])
        .hand(0, [BEAR])
        .library(0, ["forest"] * 20)
        .commander(0, [commander])
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def cast_the_bear(game) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == BEAR
        )
    )


class TestOnTheCard:
    def test_the_spell_records_what_paid_for_it(self, builder):
        game = board(builder, BEAR_COMMANDER)
        land = only_oid(game, ANCESTRY)
        cast_the_bear(game)

        # Still on the stack: the record is written as the cost is paid, which
        # is before the spell resolves.
        bear = game.state.stack[-1].oid
        assert land in game.state.objects[bear].mana_sources_spent

    def test_it_scries(self, builder):
        """The whole card: its own mana, a matching creature spell, scry 1."""
        game = board(builder, BEAR_COMMANDER)
        cast_the_bear(game)
        pass_until(
            game, lambda g: not g.state.stack and not g.state.pending_triggers
        )
        fired = [
            e
            for e in game.state.events
            if e.type == "ability_triggered" and e.data.get("card") == ANCESTRY
        ]
        assert fired, "the land's trigger never fired"

    def test_a_mismatching_commander_does_not(self, builder):
        """`shares_a_type_with_commander` still has to hold. The same land, the
        same spell, a different deck."""
        game = board(builder, BAT_COMMANDER)
        cast_the_bear(game)
        pass_until(
            game, lambda g: not g.state.stack and not g.state.pending_triggers
        )
        assert not [
            e
            for e in game.state.events
            if e.type == "ability_triggered" and e.data.get("card") == ANCESTRY
        ]

    def test_a_spell_paid_for_elsewhere_does_not(self, builder):
        """`spell_cast` on its own is a strictly better card: it would trigger
        on creature spells cast entirely off other lands."""
        game = (
            builder(players=2)
            .battlefield(0, [ANCESTRY] + ["forest"] * 3)
            .hand(0, [BEAR])
            .library(0, ["forest"] * 20)
            .commander(0, [BEAR_COMMANDER])
            .step(Step.PRECOMBAT_MAIN)
            .active(0)
            .build()
        )
        game.state.objects[only_oid(game, ANCESTRY)].tapped = True
        game.state.bump_chars()
        cast_the_bear(game)
        pass_until(
            game, lambda g: not g.state.stack and not g.state.pending_triggers
        )
        assert not [
            e
            for e in game.state.events
            if e.type == "ability_triggered" and e.data.get("card") == ANCESTRY
        ]
