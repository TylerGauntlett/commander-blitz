"""An exile whose duration ends on an *event*, and outlives the thing that made it.

    Palace Jailer — "When this creature enters, you become the monarch. When this
    creature enters, exile target creature an opponent controls **until an
    opponent becomes the monarch**."

Rule 603.7 and rule 610.3. The exile is a one-shot effect with a duration, not an
effect a permanent maintains, and the difference is the whole card. Two things
follow, and they point in opposite directions:

- **Killing the Jailer does not give the creature back.** The delayed ability was
  created by a resolving trigger, not by the permanent, and it does not care what
  happens to the permanent afterwards.
- **Something that is not the Jailer gives the creature back.** The crown moving
  to an opponent — which in an ordinary game means somebody connecting with a
  creature — is the only thing that ends it.

`exile` had exactly one duration, `until_leaves`, and it is the Oblivion Ring
link: the op records `exiled_by` and the *return* is a separate
`leaves_battlefield` trigger on the same card reading `exiled_with: self`. That
is wrong here twice over and in both directions at once. It returns the creature
on an event that must not return it, and it cannot return it on the event that
must. Written that way Palace Jailer would hand the creature back for the price
of killing a 2/2 — a materially weaker card, and one that reads exactly like the
printed one on the board.

`delay` already had the right **lifetime**: `op_delay` captures bindings at
resolution and `state.delayed_triggers` outlives every object, which is why
Gilraen can blink a creature that returns after she has died. What it did not
have is a way to say *when* other than a step name. `DelayedTrigger.event` is
that slot, and the two spellings are exclusive: an event-keyed delay carries
``step=""`` and can never come due at a step instead.

The seam worth naming is that the event bus is a plain function called from the
middle of `primitives.become_monarch`, and the effects a delay carries are a
generator that may stop to ask. So `triggers.arm_delayed` sets a flag where the
event is, and `turn.run_armed_delayed` empties it from `Game._advance`, which is
the loop that can carry a decision — one pass later, which is the moment a real
delayed triggered ability would have gone on the stack.

The boundaries pinned below are each a quietly different card: the exile has no
step it also ends at; a re-designation of the player who already holds the crown
is not the crown *moving*, so it ends nothing; the Jailer's own controller
reclaiming it ends nothing; the link is spent the first time it fires, so the
creature does not come back twice; and a card that left exile in between stays
where it went, because by 400.7 it is a new object.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import DslError, _validate_effect
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.events import EventType
from automtg.engine.primitives import become_monarch
from automtg.engine.structs import TargetRef
from automtg.engine.turn import DELAY_STEPS, _delay_due, has_armed_delayed
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

    ``has_armed_delayed`` is in the loop condition on purpose: an armed delay is
    work the game still owes, and a helper that stopped at "the stack is empty"
    would report the board one pass *before* the exile ends.
    """
    for _ in range(limit):
        state = game.state
        if not (state.pending_triggers or state.stack or has_armed_delayed(state)):
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the position never settled")


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


def jail(game, oid: int, *, controller: int = 0, event=None, source: int | None = None):
    """One resolution of "exile it until <event>", written as a card writes it."""
    return run(
        game,
        [
            {"op": "exile", "as": "jailed", "objects": {"target": "t1"}},
            {
                "op": "delay",
                "event": dict(event or UNTIL_AN_OPPONENT_IS_MONARCH),
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
        source=source,
        target=oid,
    )


def zone_of(game, oid: int) -> Zone:
    return game.state.objects[oid].zone


# ----------------------------------------------------------------------
# the duration is an event, and only an event
# ----------------------------------------------------------------------


class TestTheDurationIsAnEventAndNotAStep:
    """An event-keyed delay must not also come due at some step."""

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

    def test_the_creature_stays_exiled_through_whole_turns(self, builder):
        """"Until" with no end in sight is the ordinary case, not an edge."""
        game, bear = jailer_resolved(builder)
        assert zone_of(game, bear) is Zone.EXILE

        start = game.state.turn
        for _ in range(400):
            if game.state.turn >= start + 3 or game.over:
                break
            decision = game.pending()
            if decision is None:
                game._advance()
                continue
            game.apply(_default_answer(game, decision))

        assert zone_of(game, bear) is Zone.EXILE
        assert len(game.state.delayed_triggers) == 1


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
        """"…to the battlefield **under its owner's control**" (610.3).

        The Jailer took a creature its opponent owned; ending the duration must
        not leave it on the wrong side of the table.
        """
        game, bear = jailer_resolved(builder)

        become_monarch(game.state, 1)
        settle(game)

        assert game.state.objects[bear].controller == game.state.objects[bear].owner == 1

    def test_the_event_is_what_arms_it(self, builder):
        game, _bear = jailer_resolved(builder)
        assert not has_armed_delayed(game.state)

        become_monarch(game.state, 1)

        assert has_armed_delayed(game.state)

    def test_both_routes_into_the_designation_are_one_clause(self, builder):
        """721.3's combat transfer and the op both go through one primitive.

        Which is why "until an opponent becomes the monarch" is one clause rather
        than one per route, and why this asserts on the *events* rather than on
        how they were caused: the transfer is what the printed card is priced
        against, and `test_monarch.py` is where it is driven through combat.
        """
        game, bear = jailer_resolved(builder)

        assert game.state.monarch == 0
        become_monarch(game.state, 1, source=None)
        settle(game)

        assert [e.player for e in game.state.events if e.type == EventType.BECAME_MONARCH] == [0, 1]
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
        """Rule 721.2: becoming the monarch while already the monarch does nothing.

        The crown *moving* is the event, so a card that says "you become the
        monarch" while an opponent already holds it does end this -- and one
        aimed at the player who already holds it does not.
        """
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
        jail(game, bear, event={"event": "becomes_monarch", "controller": "you"})

        become_monarch(game.state, 1)
        settle(game)
        assert zone_of(game, bear) is Zone.EXILE, "an opponent is not 'you'"

        become_monarch(game.state, 0)
        settle(game)
        assert zone_of(game, bear) is Zone.BATTLEFIELD

    def test_any_takes_whoever_it_was(self, builder):
        game = board(builder)
        bear = only_oid(game, BEAR, 1)
        jail(game, bear, event={"event": "becomes_monarch", "controller": "any"})

        become_monarch(game.state, 0)
        settle(game)

        assert zone_of(game, bear) is Zone.BATTLEFIELD

    def test_it_is_read_off_the_delay_and_not_off_a_source_permanent(self, builder):
        """The reason `_delayed_matches` exists rather than reusing `_matches`.

        A delay scheduled by player 1's effect asks about player 1's opponents,
        even when the permanent it names belongs to somebody else -- and even
        when there is no permanent at all, which is the ordinary case here.
        """
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
        """`exiled_by` is the O-Ring link and declares a return this card lacks.

        Set, it would be readable by any `{"zone": "exile", "exiled_with":
        "self"}` selector -- an invitation to write the return the wrong way, on
        a card whose whole point is that the return is not the Jailer's.
        """
        game, bear = jailer_resolved(builder)

        assert game.state.objects[bear].exiled_by is None


# ----------------------------------------------------------------------
# once, and then the link is spent
# ----------------------------------------------------------------------


class TestItFiresOnceAndIsDischarged:
    def test_the_delay_is_struck_off_when_it_fires(self, builder):
        game, _bear = jailer_resolved(builder)

        become_monarch(game.state, 1)
        settle(game)

        assert game.state.delayed_triggers == []

    def test_a_second_monarch_change_returns_nothing_more(self, builder):
        """The creature is back on the battlefield; a repeat must not move it."""
        game, bear = jailer_resolved(builder)
        become_monarch(game.state, 1)
        settle(game)
        move_object(game.state, bear, Zone.GRAVEYARD)

        become_monarch(game.state, 0)
        become_monarch(game.state, 1)
        settle(game)

        assert zone_of(game, bear) is Zone.GRAVEYARD

    def test_two_exiles_each_get_their_own_creature_back(self, builder):
        """Two delays, two records, one event: both, and each its own card."""
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

    def test_the_delay_is_spent_either_way(self, builder):
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
        one resolution away from the delay that is watching for the same event.
        A clause read as "any" rather than "opponent" would exile the creature
        and hand it straight back.
        """
        game, bear = jailer_resolved(builder)

        assert zone_of(game, bear) is Zone.EXILE
        assert len(game.state.delayed_triggers) == 1


# ----------------------------------------------------------------------
# the load-time guards
# ----------------------------------------------------------------------


def validate(effect: dict) -> None:
    _validate_effect(effect, "test", {"t1"})


def delay_effect(**extra) -> dict:
    return {"op": "delay", "effects": [{"op": "noop"}], **extra}


class TestTheLoaderRefusesWhatItCannotMean:
    """Every refusal here is a card that would otherwise load and be different."""

    def test_the_working_spelling_loads(self):
        validate(delay_effect(event=dict(UNTIL_AN_OPPONENT_IS_MONARCH)))

    def test_a_step_and_an_event_together_are_refused(self):
        """Two ways to come due is two moments the exile could end."""
        with pytest.raises(DslError, match="not both"):
            validate(delay_effect(step="end_step", event=dict(UNTIL_AN_OPPONENT_IS_MONARCH)))

    def test_an_unknown_event_is_refused(self):
        with pytest.raises(DslError, match="unknown trigger event"):
            validate(delay_effect(event={"event": "becomes_emperor", "controller": "opponent"}))

    def test_an_event_with_no_controller_is_refused(self):
        """The one place this differs from a printed trigger, which defaults to "you".

        A duration clause states whose it is, and there is no source permanent to
        read an implicit one off -- so guessing would ship a different card in
        either direction.
        """
        with pytest.raises(DslError, match="must say whose event"):
            validate(delay_effect(event={"event": "becomes_monarch"}))

    def test_an_unknown_controller_is_refused(self):
        with pytest.raises(DslError, match="must say whose event"):
            validate(delay_effect(event={"event": "becomes_monarch", "controller": "everyone"}))

    @pytest.mark.parametrize("key,value", [("source", "self"), ("filter", {}), ("condition", {})])
    def test_the_source_scoped_keys_are_refused(self, key, value):
        """They read a permanent, and a delay's permanent is routinely gone.

        Accepted, they would give an exile whose ending depended on whether the
        Jailer was still alive -- which is exactly the `until_leaves` behaviour
        this capability exists to replace.
        """
        with pytest.raises(DslError, match="unknown key"):
            validate(
                delay_effect(event={**UNTIL_AN_OPPONENT_IS_MONARCH, key: value})
            )

    def test_a_bare_event_name_is_refused(self):
        with pytest.raises(DslError, match="a delay's event is an object"):
            validate(delay_effect(event="becomes_monarch"))

    def test_a_target_inside_an_event_keyed_delay_is_still_refused(self):
        """The same 603.7 refusal the step form has: a delay has no targets."""
        with pytest.raises(DslError, match="resolves to nothing"):
            validate(
                {
                    "op": "delay",
                    "event": dict(UNTIL_AN_OPPONENT_IS_MONARCH),
                    "effects": [
                        {"op": "put_onto_battlefield", "objects": {"target": "t1"}}
                    ],
                }
            )

    def test_an_event_keyed_delay_still_needs_effects(self):
        with pytest.raises(DslError, match="needs 'effects'"):
            validate({"op": "delay", "event": dict(UNTIL_AN_OPPONENT_IS_MONARCH)})
