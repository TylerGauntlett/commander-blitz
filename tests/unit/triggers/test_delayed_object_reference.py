"""Naming, from inside a delayed trigger, the object the ability was about.

    Gilraen, Dúnedain Protector — "{2}, {T}: Exile another target creature you
    control. You may return that card to the battlefield under its owner's
    control. If you don't, at the beginning of the next end step, return **that
    card** to the battlefield under its owner's control with a vigilance counter
    and a lifelink counter on it."

Rule 603.7: a resolving ability can create a *delayed* triggered ability, and
what it creates is a new ability with no targets of its own. "That card" is
therefore not a target — it is a reference fixed at the moment the delay was
created, and by the time the delay fires the object has changed zones (400.7),
which is the whole reason the reference has to be written down rather than
looked up.

Three things had to be true together, and the third was missing:

- the op that moved the card records what it moved (``as`` — shipped by
  `test_effect_result_binding.py`);
- ``delay`` carries that record forward, which `op_delay` has always done by
  snapshotting ``ctx.bindings``, and `turn._run_delayed` hands back to the
  delayed context;
- the op that brings the card back can say **what it arrives with**. It could
  not. "…with a vigilance counter and a lifelink counter on it" is one clause
  about one arrival, and `put_onto_battlefield` had no ``counters`` — while
  `return_from_graveyard`, which has carried the identical clause since persist,
  forces its selector's zone to the graveyard and so cannot reach a card in
  exile at all. Worse, the loader *accepted* ``counters`` on any op and every op
  but one ignored it, so the card loaded, resolved, and handed back a creature
  with neither counter and neither keyword. A keyword counter makes that
  invisible: nothing is missing on the board, the creature simply does not have
  vigilance.

The reachable near-misses are all wrong, and each is wrong in its own way:

- ``{"target": "t1"}`` is right during the ability's own resolution and names
  nothing afterwards, because `_run_delayed` builds its context with
  ``targets={}``. Nothing was malformed, so nothing said so — the printed line
  returned no card at all. That spelling is now a load error.
- ``{"zone": "exile", "exiled_with": "self"}`` is **source**-scoped rather than
  resolution-scoped: it names every card this permanent ever exiled, so a second
  activation drags back a card the first activation already declined. It also
  requires ``until_leaves``, which declares an O-Ring return this card does not
  have.
- ``snapshot`` binds a dict of characteristics, not an object anything can move.

Two more decisions worth naming. A delayed ``{"binding": …}`` keeps the *record*
semantics `resolve_pool` split out for `effect_result_binding` — no default zone
— so it still reaches a card sitting in exile; and a card that means "only if it
is still there" writes ``zone`` itself, which is what stops the delayed return
yanking a card back out of a graveyard it reached in between.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader.effects import _validate_effect
from automtg.engine.characteristics import has_keyword
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import resolve_pool
from automtg.engine.enums import ActionKind, Keyword, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.structs import DelayedTrigger, TargetRef
from automtg.engine.turn import _run_delayed
from automtg.engine.zones import move_object
from tests.conftest import oids_of, pass_until

GILRAEN = "gilraen_dunedain_protector"
BEAR = "t_bear"
ELF = "t_elf"
PLAINS = "plains"

#: What the printed card returns the creature with. Written once: the point of
#: the pair is that both arrive, and a test that checked one would pass on an
#: implementation that dropped the other.
RETURNED_WITH = {"vigilance": 1, "lifelink": 1}


# ----------------------------------------------------------------------
# positions
# ----------------------------------------------------------------------


def board(builder, creatures=(BEAR,)):
    """Gilraen, mana, and the creatures she is going to blink."""
    return (
        builder(players=2)
        .battlefield(0, [PLAINS] * 8)
        .battlefield(0, [GILRAEN, *creatures])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def drive(game, ctx, effects) -> None:
    """Run an effect list to completion, taking every option offered."""
    gen = execute(ctx, effects)
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return
        send = list(range(len(decision.options)))


def exile_and_delay(game, oid: int, delayed: list[dict], source: int | None = None):
    """One resolution of "exile that creature, and later do something to it"."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    ctx.targets["t1"] = (TargetRef.obj(oid),)
    drive(
        game,
        ctx,
        [
            {"op": "exile", "as": "exiled", "objects": {"target": "t1"}},
            {"op": "delay", "step": "end_step", "effects": delayed},
        ],
    )
    return ctx


def fire_the_delays(game) -> None:
    """Run whatever is queued, as entering the end step would.

    Through `turn._run_delayed` rather than by walking the turn, because what is
    under test is the context that function builds -- the `targets={}` in it is
    the whole reason a binding is needed.
    """
    game.state.step = Step.END_STEP
    gen = _run_delayed(game.state)
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return
        send = list(range(len(decision.options)))


def counters(game, oid: int) -> dict[str, int]:
    return dict(game.state.objects[oid].counters)


# ----------------------------------------------------------------------
# the mechanic
# ----------------------------------------------------------------------


class TestADelayCanNameTheObjectItWasAbout:
    """The hole the gap record named: "that card" had no expressible subject."""

    def test_the_delay_carries_the_record_forward(self, builder):
        game = board(builder)
        bear = oids_of(game, BEAR)[0]

        exile_and_delay(game, bear, [{"op": "noop"}])

        assert len(game.state.delayed_triggers) == 1
        assert game.state.delayed_triggers[0].bindings == {"exiled": [bear]}

    def test_nothing_happens_before_the_step_it_names(self, builder):
        """A delayed return that returns straight away is not a delayed return."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]

        exile_and_delay(
            game, bear, [{"op": "put_onto_battlefield", "objects": {"binding": "exiled"}}]
        )

        assert game.state.objects[bear].zone is Zone.EXILE

    def test_the_card_comes_back_at_the_step_it_names(self, builder):
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(
            game, bear, [{"op": "put_onto_battlefield", "objects": {"binding": "exiled"}}]
        )

        fire_the_delays(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.delayed_triggers == []

    def test_it_comes_back_under_its_owners_control(self, builder):
        """"…under its **owner's** control", which need not be the activator.

        Gilraen can only exile a creature *you* control, but control is not
        ownership -- a creature stolen with `gain_control` goes home when she
        blinks it, and the default `put_onto_battlefield` writes is the owner.
        """
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        game.state.objects[bear].owner = 1
        exile_and_delay(
            game, bear, [{"op": "put_onto_battlefield", "objects": {"binding": "exiled"}}]
        )

        fire_the_delays(game)

        assert game.state.objects[bear].controller == 1


class TestTheDelayedContextHasNoTargets:
    """`_run_delayed` builds `targets={}` -- the reason a binding is needed."""

    def test_a_target_inside_a_delay_resolves_to_nothing(self, builder):
        """The runtime fact the load guard below exists to make loud."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        ctx = EffectContext(state=game.state, controller=0)
        ctx.targets["t1"] = (TargetRef.obj(bear),)
        drive(game, ctx, [{"op": "exile", "objects": {"target": "t1"}}])
        game.state.delayed_triggers.append(
            DelayedTrigger(
                step="end_step",
                controller=0,
                effects=({"op": "put_onto_battlefield", "objects": {"target": "t1"}},),
            )
        )

        fire_the_delays(game)

        assert game.state.objects[bear].zone is Zone.EXILE, "the card never came back"

    def test_the_loader_refuses_that_spelling(self):
        with pytest.raises(DslError, match="resolves to nothing"):
            _validate_effect(
                {
                    "op": "delay",
                    "step": "end_step",
                    "effects": [
                        {"op": "put_onto_battlefield", "objects": {"target": "t1"}}
                    ],
                },
                "test",
                {"t1"},
            )

    def test_it_is_refused_however_deeply_it_is_buried(self):
        """A `may` inside a delay is an ordinary shape; the trap survives it."""
        with pytest.raises(DslError, match="resolves to nothing"):
            _validate_effect(
                {
                    "op": "delay",
                    "step": "end_step",
                    "effects": [
                        {
                            "op": "may",
                            "effects": [{"op": "destroy", "objects": {"target": "t1"}}],
                        }
                    ],
                },
                "test",
                {"t1"},
            )

    def test_a_binding_inside_a_delay_loads(self):
        _validate_effect(
            {
                "op": "delay",
                "step": "end_step",
                "effects": [
                    {"op": "put_onto_battlefield", "objects": {"binding": "exiled"}}
                ],
            },
            "test",
            {"t1"},
        )

    def test_a_target_outside_a_delay_is_untouched(self):
        """Every ability that targets and then acts, unchanged."""
        _validate_effect({"op": "destroy", "objects": {"target": "t1"}}, "test", {"t1": "permanent"})


class TestTheZoneDefaultAgreesWithTheRecordSemantics:
    """A delayed binding is a record, and records outlive the zone they name."""

    def test_a_bare_binding_reaches_a_card_in_exile(self, builder):
        """Defaulting `zone` to the battlefield here would empty the pool."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(game, bear, [{"op": "noop"}])
        delayed = game.state.delayed_triggers[0]
        ctx = EffectContext(state=game.state, controller=0, bindings=dict(delayed.bindings))

        assert resolve_pool(ctx, {"binding": "exiled"}) == [bear]

    def test_a_zone_the_card_writes_is_still_obeyed_when_it_fires(self, builder):
        """"Return that card" cannot reach a card that has left exile (400.7).

        The card writes `zone: "exile"` for exactly this, and it is not
        decoration: something else moving the card in between must end the
        delayed return, not redirect it.
        """
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(
            game,
            bear,
            [{"op": "put_onto_battlefield", "objects": {"binding": "exiled", "zone": "exile"}}],
        )
        move_object(game.state, bear, Zone.GRAVEYARD, to_player=0)

        fire_the_delays(game)

        assert game.state.objects[bear].zone is Zone.GRAVEYARD

    def test_without_the_zone_clause_it_would_be_dragged_back(self, builder):
        """The A/B that makes the clause above load-bearing rather than noise."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(
            game, bear, [{"op": "put_onto_battlefield", "objects": {"binding": "exiled"}}]
        )
        move_object(game.state, bear, Zone.GRAVEYARD, to_player=0)

        fire_the_delays(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD


class TestOneResolutionsRecordIsNotAnothers:
    """"A second activation would drag back a card declined on the first."""

    def two_pending_returns(self, game):
        bear, elf = oids_of(game, BEAR)[0], oids_of(game, ELF)[0]
        gilraen = oids_of(game, GILRAEN)[0]
        for oid in (bear, elf):
            ctx = EffectContext(state=game.state, controller=0, source_oid=gilraen)
            ctx.targets["t1"] = (TargetRef.obj(oid),)
            drive(
                game,
                ctx,
                [
                    # `until_leaves` only so the source-scoped substitute below
                    # has something to read; the binding does not need it.
                    {
                        "op": "exile",
                        "as": "exiled",
                        "until_leaves": True,
                        "objects": {"target": "t1"},
                    },
                    {
                        "op": "delay",
                        "step": "end_step",
                        "effects": [
                            {
                                "op": "put_onto_battlefield",
                                "objects": {"binding": "exiled", "zone": "exile"},
                            }
                        ],
                    },
                ],
            )
        return bear, elf, gilraen

    def test_each_delay_names_only_its_own_card(self, builder):
        game = board(builder, creatures=(BEAR, ELF))
        bear, elf, _ = self.two_pending_returns(game)

        assert [d.bindings["exiled"] for d in game.state.delayed_triggers] == [[bear], [elf]]

    def test_the_source_scoped_substitute_names_both(self, builder):
        """Why `exiled_with` is not the answer, asserted rather than argued."""
        game = board(builder, creatures=(BEAR, ELF))
        bear, elf, gilraen = self.two_pending_returns(game)
        ctx = EffectContext(state=game.state, controller=0, source_oid=gilraen)

        both = resolve_pool(ctx, {"zone": "exile", "exiled_with": "self"})

        assert sorted(both) == sorted([bear, elf])

    def test_both_come_back_once_each(self, builder):
        """Source-scoped, each delay would return both and the second is a no-op
        that hides the bug. Binding-scoped, each returns one."""
        game = board(builder, creatures=(BEAR, ELF))
        bear, elf, _ = self.two_pending_returns(game)

        fire_the_delays(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[elf].zone is Zone.BATTLEFIELD


class TestWhatThePermanentArrivesWith:
    """"…with a vigilance counter and a lifelink counter on it."""

    def test_put_onto_battlefield_places_them(self, builder):
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(
            game,
            bear,
            [
                {
                    "op": "put_onto_battlefield",
                    "objects": {"binding": "exiled", "zone": "exile"},
                    "counters": RETURNED_WITH,
                }
            ],
        )

        fire_the_delays(game)

        assert counters(game, bear) == RETURNED_WITH

    def test_the_counters_are_the_keywords(self, builder):
        """122.1c -- and the reason the two capabilities are one printed card."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(
            game,
            bear,
            [
                {
                    "op": "put_onto_battlefield",
                    "objects": {"binding": "exiled", "zone": "exile"},
                    "counters": RETURNED_WITH,
                }
            ],
        )

        fire_the_delays(game)

        assert has_keyword(game.state, bear, Keyword.VIGILANCE)
        assert has_keyword(game.state, bear, Keyword.LIFELINK)

    def test_a_return_with_no_counters_clause_places_none(self, builder):
        """Every `put_onto_battlefield` shipped before this one, unchanged."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(
            game, bear, [{"op": "put_onto_battlefield", "objects": {"binding": "exiled"}}]
        )

        fire_the_delays(game)

        assert counters(game, bear) == {}

    def test_nothing_arrives_with_counters_if_nothing_arrives(self, builder):
        """The pool was empty, so there is no object to put a counter on."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        exile_and_delay(
            game,
            bear,
            [
                {
                    "op": "put_onto_battlefield",
                    "objects": {"binding": "exiled", "zone": "exile"},
                    "counters": RETURNED_WITH,
                }
            ],
        )
        move_object(game.state, bear, Zone.GRAVEYARD, to_player=0)

        fire_the_delays(game)

        assert counters(game, bear) == {}


class TestTheLoaderGuardOnCounters:
    def test_counters_on_put_onto_battlefield_loads(self):
        _validate_effect(
            {
                "op": "put_onto_battlefield",
                "objects": {"binding": "exiled"},
                "counters": RETURNED_WITH,
            },
            "test",
            {},
        )

    def test_counters_on_return_from_graveyard_still_loads(self):
        """Persist and undying, which have spelled it this way all along."""
        _validate_effect(
            {"op": "return_from_graveyard", "destination": "battlefield",
             "counters": {"-1/-1": 1}},
            "test",
            {},
        )

    def test_counters_on_an_op_that_ignores_them_is_refused(self):
        """It loaded, resolved, and returned a creature without its keywords."""
        with pytest.raises(DslError, match=r"only.*read it"):
            _validate_effect(
                {"op": "return_to_hand", "objects": {"binding": "exiled"},
                 "counters": RETURNED_WITH},
                "test",
                {},
            )

    def test_a_near_miss_keyword_counter_is_still_refused(self):
        """The `keyword_counters` guard, reached through the new clause.

        "a vigilance counter" spelled as `"vigilance counter"` is an inert tally
        and the creature comes back without the keyword -- which on this card is
        the entire second half of the sentence.
        """
        with pytest.raises(DslError, match="exact keyword name"):
            _validate_effect(
                {
                    "op": "put_onto_battlefield",
                    "objects": {},
                    "counters": {"vigilance counter": 1},
                },
                "test",
                {},
            )


# ----------------------------------------------------------------------
# the printed card
# ----------------------------------------------------------------------


def activate(game, target: int | None = None) -> None:
    """Activate Gilraen, optionally at a named creature."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and (target is None or any(ref.id == target for ref in a.targets))
        )
    )


def blink(game, answer: ActionKind, target: int | None = None) -> None:
    """The whole printed card: activate, answer "you may", finish the turn.

    The turn has to actually end, because the half under test is the half that
    happens at the beginning of the *next* end step. `pass_until` on the turn
    number rather than on the step, so this reads the same whether the position
    stops for a declare-attackers decision on the way or not.
    """
    turn = game.state.turn
    activate(game, target)
    game.apply(next(a for a in game.legal_actions() if a.kind is answer))
    pass_until(game, lambda g: g.state.turn > turn)


class TestGilraenOnACard:
    """The printed card, activated in a real position."""

    def test_declining_returns_it_at_the_end_step_with_both_counters(self, builder):
        game = board(builder)
        bear = oids_of(game, BEAR)[0]

        blink(game, ActionKind.NO)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert counters(game, bear) == RETURNED_WITH
        assert has_keyword(game.state, bear, Keyword.VIGILANCE)
        assert has_keyword(game.state, bear, Keyword.LIFELINK)

    def test_it_is_still_in_exile_while_the_question_is_being_asked(self, builder):
        """The blink really happens; the "you may" is not a no-op."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]

        activate(game)

        assert game.state.objects[bear].zone is Zone.EXILE

    def test_the_next_end_step_is_this_turns(self, builder):
        """"At the beginning of the **next** end step" -- not next turn's.

        The activation happens in a precombat main phase, so this turn's end
        step is still ahead of it. A delay that waited a turn would leave the
        creature in exile through the opponent's whole turn, which is a
        different and much worse card.
        """
        game = board(builder)
        bear = oids_of(game, BEAR)[0]
        activate(game)

        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.NO))
        pass_until(game, lambda g: g.state.turn > 1)

        assert game.state.turn == 2, "the opponent's turn has only just begun"
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert counters(game, bear) == RETURNED_WITH

    def test_accepting_returns_it_now_and_bare(self, builder):
        """"If you don't" -- taking the option is what forgoes the counters."""
        game = board(builder)
        bear = oids_of(game, BEAR)[0]

        blink(game, ActionKind.YES)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert counters(game, bear) == {}
        assert not has_keyword(game.state, bear, Keyword.VIGILANCE)

    def test_accepting_schedules_nothing(self, builder):
        """The delay lives in the `else`; a stray one returns the card twice."""
        game = board(builder)
        activate(game)

        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))

        assert game.state.delayed_triggers == []

    def test_she_cannot_blink_herself(self, builder):
        """"another target creature you control" -- `exclude_self`."""
        game = board(builder)
        gilraen = oids_of(game, GILRAEN)[0]

        targets = {
            ref.id
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            for ref in a.targets
        }

        assert gilraen not in targets

    def test_a_second_activation_leaves_the_first_card_alone(self, builder):
        """The failure `exiled_with` would have had: a card declined on the
        first activation, dragged back -- or re-countered -- by the second.

        Two turns apart, because the cost taps her. That is the honest shape of
        the bug too: the source-scoped pool accumulates for as long as the
        permanent is on the battlefield, so the older entry is still in it.
        """
        game = board(builder, creatures=(BEAR, ELF))
        bear, elf = oids_of(game, BEAR)[0], oids_of(game, ELF)[0]

        blink(game, ActionKind.NO, target=bear)
        assert counters(game, bear) == RETURNED_WITH, "the first blink worked"

        pass_until(
            game,
            lambda g: any(a.kind is ActionKind.ACTIVATE for a in g.legal_actions()),
        )
        blink(game, ActionKind.NO, target=elf)

        assert counters(game, elf) == RETURNED_WITH, "the second card got its own"
        assert counters(game, bear) == RETURNED_WITH, "the first got no second helping"
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD


