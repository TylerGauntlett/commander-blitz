""""If this is the **second time this ability has resolved this turn**, double
the number of +1/+1 counters on that creature instead."

Scythecat Cub. Everything else on the card was already sayable — the landfall
trigger is `permanent_enters` filtered to Lands, the doubling is `add_counters`
with an amount of `counters_on` itself, and `if` already carries `then`/`else`
so the printed "instead" needs no replacement machinery. Only the count was
missing, and the two things that nearly stood in for it are both wrong:

- **`set_flag`/`has_flag`** is one-way. There is no `clear_flag` and nothing
  empties `obj.flags` at end of turn, so a flag written on the first landfall
  would still be set next turn, and would make the *third* and every later
  resolution double as well. Faking the reset with an end-step ability
  implements no printed sentence, and the residual gate rejects that.
- **A lands-entered tally** counts the wrong events. The card counts
  *resolutions of the ability*, so a trigger that fizzled, or one removed by its
  intervening-if under 603.4, must not advance it — neither of those resolved.

The count therefore lives where resolution happens. `stack.resolve_top` bumps it
past both of those returns and *before* the effects run, because a card asking
"is this the second time" has to count the one it is in the middle of. That is
also why it is the only tally in `TurnLedger` not folded in `GameState.emit`:
`ABILITY_RESOLVED` is emitted after the effects, one resolution too late to be
of use to the effect that needs it.

Keyed by (object, ability index), because "this ability" is a fact about one
permanent — two Cats count separately — and cleared with the rest of the ledger
at cleanup.

These tests push the trigger and resolve it directly rather than playing lands.
Landfall twice in one turn needs an extra land drop, and driving the turn engine
far enough to get one walks through a cleanup step, which clears the very ledger
under test. Resolving the ability is the claim; how the land got there is not.
"""

from __future__ import annotations

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.values import evaluate_value
from automtg.engine.enums import Zone
from automtg.engine.stack import push_triggered_ability, resolve_top
from automtg.engine.structs import TriggerInstance, TurnLedger
from tests.conftest import only_oid, plus_one_counters

CAT = "t_scythe"  # 1/1; landfall, doubling on the second resolution
EVOLVER = "t_evolver"  # its intervening-if fails against a smaller creature
BEAR = "t_bear"


def fire(game, oid: int, ability_index: int = 0, **bindings) -> None:
    """Put one of ``oid``'s triggered abilities on the stack and resolve it."""
    trig = TriggerInstance(
        source_oid=oid, ability_index=ability_index, controller=0, bindings=bindings
    )
    # A generator since 603.3d: these triggers have no targets, so it asks
    # nothing and runs straight through.
    for _ in push_triggered_ability(game.state, trig):
        raise AssertionError("this trigger chooses nothing")
    gen = resolve_top(game.state)
    answer: list[int] = []
    while True:
        try:
            gen.send(answer) if answer else next(gen)
        except StopIteration:
            return


def cat_board(builder, count: int = 1, **kw):
    return builder(players=2).battlefield(0, [CAT] * count, **kw).build(advance=False)


class TestTheCountThatMakesTheCard:
    def test_the_first_resolution_adds_one(self, builder):
        game = cat_board(builder)
        cat = only_oid(game, CAT, 0)
        fire(game, cat)
        assert plus_one_counters(game, cat) == 1

    def test_the_second_doubles_instead_of_adding(self, builder):
        game = cat_board(builder)
        cat = only_oid(game, CAT, 0)
        fire(game, cat)
        fire(game, cat)
        assert plus_one_counters(game, cat) == 2

    def test_the_third_is_an_ordinary_add_again(self, builder):
        """"The second time" is exactly the second. This is the assertion a
        one-way flag would fail: it would double here too, giving 4."""
        game = cat_board(builder)
        cat = only_oid(game, CAT, 0)
        for _ in range(3):
            fire(game, cat)
        assert plus_one_counters(game, cat) == 3

    def test_the_doubling_reads_the_counters_actually_there(self, builder):
        """A Cat that started with three ends the second landfall on eight,
        not on five. `counters_on` is the amount, so the branch is visible."""
        game = cat_board(builder, counters={"+1/+1": 3})
        cat = only_oid(game, CAT, 0)
        fire(game, cat)  # 3 -> 4
        fire(game, cat)  # 4 -> 8
        assert plus_one_counters(game, cat) == 8


class TestItIsPerAbilityAndPerTurn:
    def test_two_copies_count_separately(self, builder):
        """"This ability" is a fact about one permanent, so one land entering
        is the first resolution for each Cat and neither doubles."""
        game = cat_board(builder, count=2)
        both = [o for o in game.state.battlefield if game.state.objects[o].def_id == CAT]
        assert len(both) == 2
        for oid in both:
            fire(game, oid)
        for oid in both:
            fire(game, oid)
        assert [plus_one_counters(game, o) for o in both] == [2, 2]

    def test_the_tally_clears_with_the_rest_of_the_ledger(self, builder):
        """Without the clear, every later turn's first landfall would double."""
        game = cat_board(builder)
        cat = only_oid(game, CAT, 0)
        fire(game, cat)
        assert game.state.turn_ledger.ability_resolutions == {(cat, 0): 1}
        game.state.turn_ledger.clear()
        assert game.state.turn_ledger.ability_resolutions == {}
        fire(game, cat)
        assert plus_one_counters(game, cat) == 2, "a fresh turn adds one, it does not double"


class TestOnlyRealResolutionsCount:
    def test_an_intervening_if_that_fails_does_not_count(self, builder):
        """603.4: the ability is removed and does nothing. It did not resolve,
        so it must not advance the tally — otherwise a Cat that had a landfall
        trigger *fail* would double on its next real one."""
        game = builder(players=2).battlefield(0, [EVOLVER]).build(advance=False)
        evolver = only_oid(game, EVOLVER, 0)
        from automtg.engine.primitives import create_token

        create_token(game.state, BEAR, 0)  # a 2/2 joining a 1/1: condition holds
        big = next(
            o for o in game.state.battlefield if game.state.objects[o].def_id == BEAR
        )
        game.state.pending_triggers.clear()
        fire(game, evolver, subject=big)
        assert game.state.turn_ledger.ability_resolutions == {(evolver, 0): 1}

        # Now a condition that cannot hold: the evolver is bigger than itself.
        game.state.turn_ledger.clear()
        fire(game, evolver, subject=evolver)
        assert game.state.turn_ledger.ability_resolutions == {}, (
            "an ability removed by 603.4 never resolved"
        )

    def test_a_source_that_has_left_still_counts(self, builder):
        """The other side of the same line. An ability resolves even when its
        source is gone (`_resolve_ability` deletes `source` deliberately), and
        that *is* a resolution, so it must advance the tally. The bump sits
        after the two early returns and before the effects, which is the only
        placement that gets both this and the 603.4 case right."""
        game = builder(players=2).battlefield(0, [CAT]).build(advance=False)
        cat = only_oid(game, CAT, 0)
        game.state.objects[cat].zone = Zone.GRAVEYARD
        game.state.battlefield.remove(cat)
        fire(game, cat)
        assert game.state.turn_ledger.ability_resolutions == {(cat, 0): 1}


class TestTheValueLeaf:
    def test_it_reads_the_context_not_the_ledger(self, builder):
        """The count has to include the resolution in progress, and only
        `resolve_top` knows which ability that is."""
        game = cat_board(builder)
        ctx = EffectContext(state=game.state, controller=0, resolutions=2)
        assert evaluate_value(ctx, {"resolutions_this_turn": "self"}) == 2

    def test_it_is_zero_for_a_spell(self, builder):
        """A spell has no ability index and cannot ask."""
        game = cat_board(builder)
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"resolutions_this_turn": "self"}) == 0


class TestTheLedgerItself:
    def test_resolving_counts_from_one(self):
        ledger = TurnLedger()
        assert ledger.resolving(7, 0) == 1, "the first resolution is the first"
        assert ledger.resolving(7, 0) == 2

    def test_different_abilities_on_one_object_are_separate(self):
        ledger = TurnLedger()
        assert ledger.resolving(7, 0) == 1
        assert ledger.resolving(7, 1) == 1, "a different ability of the same card"

    def test_clear_empties_it(self):
        ledger = TurnLedger()
        ledger.resolving(7, 0)
        ledger.clear()
        assert ledger.resolving(7, 0) == 1
