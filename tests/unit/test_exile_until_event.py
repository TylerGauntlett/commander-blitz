"""An exile whose duration ends on an *event*, and outlives both its source and the turn.

    Palace Jailer — "When this creature enters, you become the monarch. When this
    creature enters, exile target creature an opponent controls **until an
    opponent becomes the monarch**."

Rule 603.7 and rule 610.3. The exile is a one-shot effect with a duration, not an
effect a permanent maintains, and the difference is the whole card. Two things
follow, and they point in opposite directions:

- **Killing the Jailer does not give the creature back.** The delayed ability was
  created by a resolving trigger, not by the permanent, and does not care what
  happens to the permanent afterwards.
- **Something that is not the Jailer gives the creature back.** The crown moving
  to an opponent — which in an ordinary game means somebody connecting with a
  creature — is the only thing that ends it.

`exile` has one duration, `until_leaves`, and it is the Oblivion Ring link: the
op records `exiled_by` and the return is a separate `leaves_battlefield` trigger
on the same card reading `exiled_with: self`. That is wrong here twice over and
in both directions at once — it returns the creature on an event that must *not*
return it, and cannot return it on the event that must. Written that way Palace
Jailer hands the creature back for the price of killing a 2/2, a materially
weaker card that reads identically on the board.

`delayed_trigger` already had the shape: a subscription with no permanent,
created by a resolving effect, bindings and controller captured then and there.
What it did not have is Palace Jailer's **duration**. Forth Eorlingas! prints
"whenever … **this turn**" — a subscription with a stated lifetime that fires
every time — and the op was built to that, repeating and dropped at
`turn._cleanup_step`. Palace Jailer prints "**until** …", which is the opposite
on both counts: it fires **once**, and it must outlive the turn, because the
crown may not move for six of them.

So `DelayedTrigger.duration` is that one field, read at exactly two places —
`triggers._arm_delayed` (strike the subscription off as it arms) and
`turn._cleanup_step` (leave it alone). The two axes it conflates, repeating-or-
once and turn-scoped-or-not, are correlated in both printed cards and are not the
same question; `structs.DELAYED_DURATIONS` says where a card that separated them
would go.

The boundary that would otherwise be silent is the turn one. The cleanup clear as
first written dropped every event-watching subscription, which turns "until an
opponent becomes the monarch" into "until end of turn" with nothing on the board
to say so — `test_the_exile_outlives_the_turn_it_was_made_in` is the witness, and
it fails against that clear.

The rest of the boundaries are each a quietly different card: the exile has no
step it also ends at; a re-designation of the player who already holds the crown
is not the crown *moving*, so it ends nothing; the Jailer's own controller
reclaiming it ends nothing; and a card that left exile in between stays where it
went, because by 400.7 it is a new object.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader.effects import _validate_effect
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.primitives import become_monarch
from automtg.engine.structs import TargetRef
from automtg.engine.turn import DELAY_STEPS, _delay_due
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, action_for_card, oids_of, only_oid

JAILER = "palace_jailer"  # 2/2; the shipped witness for this capability
BEAR = "t_bear"
ELF = "t_elf"
PLAINS = "plains"

#: "Until an opponent becomes the monarch", as a card writes it.
UNTIL_AN_OPPONENT_IS_MONARCH = {"event": "becomes_monarch", "controller": "opponent"}


# ----------------------------------------------------------------------
# positions
# ----------------------------------------------------------------------


def board(builder, *, opponent=(BEAR,)):
    """A frozen position: mana, and creatures for the Jailer to point at."""
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 8)
        .battlefield(1, list(opponent))
        .turn(3)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def jailer_resolved(builder, *, opponent=(BEAR,)):
    """Palace Jailer cast and fully resolved, and the creature it took.

    Cast rather than placed, because both halves of this card are enters
    triggers: a Jailer put straight onto the battlefield has never entered, so
    nothing has become the monarch and nothing has been exiled.
    """
    game = (
        builder(players=2)
        .hand(0, [JAILER])
        .battlefield(0, [PLAINS] * 8)
        .battlefield(1, list(opponent))
        .turn(3)
        .build()
    )
    victim = oids_of(game, opponent[0], 1)[0]
    game.apply(action_for_card(game, ActionKind.CAST, JAILER))
    settle(game)
    return game, victim


def settle(game, limit: int = 80) -> None:
    """Run the engine forward until nothing is owed and nothing is waiting.

    ``armed_delays`` is in the loop condition on purpose: an armed subscription
    is work the game still owes, and a helper that stopped at "the stack is
    empty" would report the board one pass *before* the exile ends.
    """
    for _ in range(limit):
        state = game.state
        if not (state.pending_triggers or state.stack or state.armed_delays):
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the position never settled")


def walk_turns(game, count: int, limit: int = 600) -> None:
    """Play passively until ``count`` turn boundaries have gone by."""
    target = game.state.turn + count
    for _ in range(limit):
        if game.state.turn >= target or game.over:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never reached turn {target}")


def run(game, effects, *, controller: int = 0, source: int | None = None, target=None):
    """Resolve a list of effects with no card in the way."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    if target is not None:
        ctx.targets["t1"] = (TargetRef.obj(target),)
    gen = execute(ctx, effects)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)
    return ctx


def jail(game, oid: int, *, controller: int = 0, trigger=None, duration="until_it_fires"):
    """One resolution of "exile it until <event>", written as a card writes it."""
    return run(
        game,
        [
            {"op": "exile", "as": "jailed", "objects": {"target": "t1"}},
            {
                "op": "delayed_trigger",
                "trigger": dict(trigger or UNTIL_AN_OPPONENT_IS_MONARCH),
                "duration": duration,
                "text": "Return the exiled card to the battlefield.",
                "effects": [
                    {
                        "op": "put_onto_battlefield",
                        "objects": {"binding": "jailed", "zone": "exile"},
                    }
                ],
            },
        ],
        controller=controller,
        target=oid,
    )


def zone_of(game, oid: int) -> Zone:
    return game.state.objects[oid].zone


# ----------------------------------------------------------------------
# the duration this capability added
# ----------------------------------------------------------------------


class TestTheExileOutlivesTheTurn:
    """`until_it_fires` against `this_turn`, which is the whole of the new field."""

    def test_the_exile_outlives_the_turn_it_was_made_in(self, builder):
        """The silent failure: a blanket cleanup clear retimes this to end of turn.

        `turn._cleanup_step` drops event-watching subscriptions, because the
        shape it was written for prints "this turn". Palace Jailer names no turn
        at all — the crown may not move for six of them — and a clear keyed on
        *being* event-watching rather than on the subscription's own duration
        makes this an "until end of turn" exile with nothing on the board saying
        so.
        """
        game, bear = jailer_resolved(builder)
        assert zone_of(game, bear) is Zone.EXILE

        walk_turns(game, 3)

        assert zone_of(game, bear) is Zone.EXILE, "cleanup ate the subscription"
        assert len(game.state.delayed_triggers) == 1

    def test_and_still_ends_when_the_crown_moves_turns_later(self, builder):
        """Surviving cleanup is only half of it; it has to still work afterwards."""
        game, bear = jailer_resolved(builder)
        walk_turns(game, 3)

        become_monarch(game.state, 1)
        settle(game)

        assert zone_of(game, bear) is Zone.BATTLEFIELD

    def test_the_repeating_shape_still_expires_at_cleanup(self, builder):
        """Forth Eorlingas' duration is untouched, and is still the default.

        The contrast is the point of having a field at all: "whenever … **this
        turn**" must not become a subscription that lives for ever.
        """
        game = board(builder)
        jail(game, only_oid(game, BEAR, 1), duration="this_turn")
        assert len(game.state.delayed_triggers) == 1

        walk_turns(game, 1)

        assert game.state.delayed_triggers == []

    def test_this_turn_is_the_default(self, builder):
        """An op that says nothing gets the shape every printed one has today."""
        game = board(builder)
        run(
            game,
            [
                {
                    "op": "delayed_trigger",
                    "trigger": {"event": "becomes_monarch", "controller": "any"},
                    "effects": [{"op": "noop"}],
                }
            ],
        )

        assert game.state.delayed_triggers[0].duration == "this_turn"


class TestItFiresOnceAndIsSpent:
    """`until_it_fires` is discharged as it arms; `this_turn` is not."""

    def test_the_subscription_is_struck_off_when_it_arms(self, builder):
        game = board(builder)
        jail(game, only_oid(game, BEAR, 1))

        become_monarch(game.state, 1)

        assert game.state.delayed_triggers == []
        assert len(game.state.armed_delays) == 1, "the copy still has to resolve"

    def test_a_repeating_subscription_survives_firing(self, builder):
        """The behaviour `_arm_delayed` was written for, and must keep."""
        game = board(builder)
        jail(game, only_oid(game, BEAR, 1), duration="this_turn")

        become_monarch(game.state, 1)

        assert len(game.state.delayed_triggers) == 1

    def test_a_second_monarch_change_does_not_free_the_creature_again(self, builder):
        """The exile ended once; the crown moving again is not that exile's business.

        Put back in exile by something else and the crown handed round again, a
        subscription that had survived firing would reach in and hand the
        creature back a second time -- off an exile it was never about.
        """
        game, bear = jailer_resolved(builder)
        become_monarch(game.state, 1)
        settle(game)
        assert zone_of(game, bear) is Zone.BATTLEFIELD
        move_object(game.state, bear, Zone.EXILE)

        become_monarch(game.state, 0)
        become_monarch(game.state, 1)
        settle(game)

        assert zone_of(game, bear) is Zone.EXILE

    def test_two_exiles_each_get_their_own_creature_back(self, builder):
        """Two subscriptions, two records, one event: both, and each its own card.

        Also the reason `_arm_delayed` strikes off by identity: these differ only
        in their captured bindings.
        """
        game = board(builder, opponent=(BEAR, ELF))
        bear = only_oid(game, BEAR, 1)
        elf = only_oid(game, ELF, 1)
        jail(game, bear)
        jail(game, elf)

        become_monarch(game.state, 1)
        settle(game)

        assert zone_of(game, bear) is Zone.BATTLEFIELD
        assert zone_of(game, elf) is Zone.BATTLEFIELD
        assert game.state.delayed_triggers == []


# ----------------------------------------------------------------------
# the duration is an event, and only an event
# ----------------------------------------------------------------------


class TestTheDurationIsAnEventAndNotAStep:
    def test_it_is_due_at_no_step_at_all(self, builder):
        """The quiet failure this guards: a second, earlier way for the exile to end."""
        game = board(builder)
        jail(game, only_oid(game, BEAR, 1))
        delayed = game.state.delayed_triggers[0]

        for name, step in DELAY_STEPS.items():
            game.state.step = step
            assert not _delay_due(game.state, delayed), f"came due at {name}"

    def test_it_carries_no_step(self, builder):
        game = board(builder)
        jail(game, only_oid(game, BEAR, 1))

        assert game.state.delayed_triggers[0].step == ""


# ----------------------------------------------------------------------
# and it ends when the event happens
# ----------------------------------------------------------------------


class TestItEndsWhenTheEventHappens:
    def test_the_creature_comes_back(self, builder):
        game, bear = jailer_resolved(builder)

        become_monarch(game.state, 1)
        settle(game)

        assert zone_of(game, bear) is Zone.BATTLEFIELD

    def test_it_comes_back_under_its_owners_control(self, builder):
        """"…to the battlefield **under its owner's control**" (610.3)."""
        game, bear = jailer_resolved(builder)

        become_monarch(game.state, 1)
        settle(game)

        assert game.state.objects[bear].controller == game.state.objects[bear].owner == 1

    def test_both_routes_into_the_designation_are_one_clause(self, builder):
        """721.3's combat transfer and the op both go through one primitive.

        Which is why "until an opponent becomes the monarch" is one clause rather
        than one per route, and why this asserts on the *events* rather than on
        how they were caused: `test_monarch.py` is where the transfer is driven
        through combat.
        """
        game, bear = jailer_resolved(builder)

        assert game.state.monarch == 0
        become_monarch(game.state, 1)
        settle(game)

        assert [
            e.player for e in game.state.events if e.type == EventType.BECAME_MONARCH
        ] == [0, 1]
        assert zone_of(game, bear) is Zone.BATTLEFIELD


# ----------------------------------------------------------------------
# whose event it is
# ----------------------------------------------------------------------


class TestWhoseEventItIs:
    """``controller`` is read against the delay's controller, not an object's."""

    def test_the_jailers_own_controller_reclaiming_it_ends_nothing(self, builder):
        """"An **opponent** becomes the monarch." Taking it back is not that."""
        game = board(builder)
        bear = only_oid(game, BEAR, 1)
        become_monarch(game.state, 1)
        jail(game, bear)

        become_monarch(game.state, 0)
        settle(game)

        assert zone_of(game, bear) is Zone.EXILE
        assert len(game.state.delayed_triggers) == 1

    def test_redesignating_the_holder_is_not_an_event(self, builder):
        """Rule 721.2: becoming the monarch while already the monarch does nothing."""
        game = board(builder)
        bear = only_oid(game, BEAR, 1)
        become_monarch(game.state, 1)
        jail(game, bear)

        assert become_monarch(game.state, 1) is False
        settle(game)

        assert zone_of(game, bear) is Zone.EXILE

    def test_you_means_the_delays_own_controller(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 1)
        jail(game, bear, trigger={"event": "becomes_monarch", "controller": "you"})

        become_monarch(game.state, 1)
        settle(game)
        assert zone_of(game, bear) is Zone.EXILE, "an opponent is not 'you'"

        become_monarch(game.state, 0)
        settle(game)
        assert zone_of(game, bear) is Zone.BATTLEFIELD

    def test_it_is_read_off_the_delay_and_not_off_a_source_permanent(self, builder):
        """A subscription installed by player 1 asks about player 1's opponents."""
        game = board(builder)
        bear = only_oid(game, BEAR, 1)
        jail(game, bear, controller=1)

        become_monarch(game.state, 1)
        settle(game)
        assert zone_of(game, bear) is Zone.EXILE, "player 1 is not their own opponent"

        become_monarch(game.state, 0)
        settle(game)
        assert zone_of(game, bear) is Zone.BATTLEFIELD


# ----------------------------------------------------------------------
# the lifetime -- the whole reason this is not `until_leaves`
# ----------------------------------------------------------------------


class TestTheExileOutlivesTheJailer:
    """Killing the Jailer must not be an answer to the Jailer."""

    def test_the_creature_stays_exiled_when_the_jailer_dies(self, builder):
        game, bear = jailer_resolved(builder)
        jailer = only_oid(game, JAILER, 0)

        move_object(game.state, jailer, Zone.GRAVEYARD)
        settle(game)

        assert zone_of(game, bear) is Zone.EXILE

    def test_it_still_comes_back_after_the_jailer_has_died(self, builder):
        """The other direction, and the one a dropped duration would hide.

        A card that exiled permanently would pass the test above and fail this
        one, and nothing on the board would say which had shipped.
        """
        game, bear = jailer_resolved(builder)
        move_object(game.state, only_oid(game, JAILER, 0), Zone.GRAVEYARD)
        settle(game)

        become_monarch(game.state, 1)
        settle(game)

        assert zone_of(game, bear) is Zone.BATTLEFIELD

    def test_the_exile_records_no_oring_link(self, builder):
        """`exiled_by` is the O-Ring link and declares a return this card lacks."""
        game, bear = jailer_resolved(builder)

        assert game.state.objects[bear].exiled_by is None


# ----------------------------------------------------------------------
# what comes back
# ----------------------------------------------------------------------


class TestWhatComesBack:
    def test_a_card_that_left_exile_in_between_is_not_dragged_back(self, builder):
        """400.7: a card that changed zones is a new object.

        The `zone: "exile"` on the binding is what says so. Without it the
        delayed return would reach into a graveyard, which is the one thing a
        record-shaped reference will happily do.
        """
        game = board(builder)
        bear = only_oid(game, BEAR, 1)
        jail(game, bear)
        move_object(game.state, bear, Zone.GRAVEYARD)

        become_monarch(game.state, 1)
        settle(game)

        assert zone_of(game, bear) is Zone.GRAVEYARD

    def test_the_subscription_is_spent_either_way(self, builder):
        """The duration is over whether or not the return found anything."""
        game = board(builder)
        bear = only_oid(game, BEAR, 1)
        jail(game, bear)
        move_object(game.state, bear, Zone.GRAVEYARD)

        become_monarch(game.state, 1)
        settle(game)

        assert game.state.delayed_triggers == []


# ----------------------------------------------------------------------
# the card
# ----------------------------------------------------------------------


class TestPalaceJailer:
    """Both printed sentences, in one resolution, on the shipped card."""

    def test_it_makes_you_the_monarch(self, builder):
        game, _ = jailer_resolved(builder)

        assert game.state.monarch == 0

    def test_it_exiles_a_creature_an_opponent_controls(self, builder):
        game, bear = jailer_resolved(builder)

        assert zone_of(game, bear) is Zone.EXILE
        assert len(game.state.battlefield_objects(1)) == 0

    def test_becoming_the_monarch_yourself_does_not_end_its_own_exile(self, builder):
        """The two triggers are one card, and the first must not undo the second.

        "You become the monarch" fires `becomes_monarch` with *you* as the actor,
        one resolution away from the subscription watching for the same event. A
        clause read as "any" rather than "opponent" would exile the creature and
        hand it straight back.
        """
        game, bear = jailer_resolved(builder)

        assert zone_of(game, bear) is Zone.EXILE
        assert len(game.state.delayed_triggers) == 1


# ----------------------------------------------------------------------
# the load-time guard this capability added
# ----------------------------------------------------------------------


def validate(effect: dict) -> None:
    _validate_effect(effect, "test", {"t1"})


def subscription(**extra) -> dict:
    return {
        "op": "delayed_trigger",
        "trigger": dict(UNTIL_AN_OPPONENT_IS_MONARCH),
        "effects": [{"op": "noop"}],
        **extra,
    }


class TestTheLoaderRefusesADurationItCannotMean:
    def test_both_durations_load(self):
        validate(subscription(duration="until_it_fires"))
        validate(subscription(duration="this_turn"))

    def test_an_omitted_duration_loads(self):
        validate(subscription())

    def test_an_unknown_duration_is_refused(self):
        """It would fall through to `this_turn` and quietly retime the card."""
        with pytest.raises(DslError, match="unknown delayed_trigger duration"):
            validate(subscription(duration="until_end_of_game"))

    def test_a_misspelling_of_the_one_that_matters_is_refused(self):
        with pytest.raises(DslError, match="unknown delayed_trigger duration"):
            validate(subscription(duration="until_fires"))
