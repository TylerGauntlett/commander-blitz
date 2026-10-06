"""Sagas (rule 714): a card whose text is a numbered list nobody plays.

Oath of Eorl is the witness -- "(As this Saga enters and after your draw step,
add a lore counter. Sacrifice after III.)" plus three chapters -- and it is the
only Saga in the pool, so everything the sandbox cannot reach is asserted here.

**This reverses a documented decision.** `docs/rules-coverage.md` listed sagas
under **Not implemented**, beside planeswalkers and battles, on the grounds that
each is a rules subsystem rather than a card. That was true and it was a
decision; what it was waiting for was somewhere for the three rules-supplied
behaviours to live, and the monarch had just shown where -- a turn-based action
in `turn`, a state-based action in `sba`, and nothing at all written on the card.

**The reminder text is the mechanic, and none of it is an ability.** Read the
line back: a lore counter as it enters, a lore counter each precombat main
phase, sacrifice after the last chapter. All three are things *the game* does to
a Saga, which is why they are in `engine/sagas.py` rather than compiled from the
card, and why the printed reminder line is parenthetical -- it is telling you the
rules, not giving you an ability.

The gap record for Oath of Eorl proposed a kludge and then refused it, naming
four ways it diverges. Each one is a class below, because each ships a quietly
different card:

`TestEnteringWithALoreCounter`
    714.2b is part of **entering**, not a `self_enters` trigger. A trigger puts
    the counter on after the Saga is already down and after every other enters
    trigger has seen it empty, so chapter I would be a round of priority late and
    interruptible before it started.

`TestTheTurnBasedAction`
    714.2d is a **turn-based action** at the precombat main phase, not a
    `draw_step` trigger. It uses no stack, nobody holds priority between the
    counter and the chapter, and it is the active player's Sagas only -- a
    `draw_step` trigger fires on every player's draw step unless each card
    remembers to gate itself.

`TestChaptersTriggerOnReaching`
    714.2c fires when the count **becomes** the chapter number, not when a
    counter is placed. The two come apart under proliferate, under a counter
    removed and put back, and under a placement of more than one at once.

`TestTheSacrifice`
    704.5s is a **state-based action** checked while a chapter is not on the
    stack, not an effect appended to the final chapter. Appended, the Saga is
    sacrificed in the middle of its own last chapter resolving -- which on Oath
    of Eorl means granting the crown from a permanent already in a graveyard.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import sagas, sba, turn
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from automtg.engine.primitives import add_counters, remove_counters
from tests.conftest import (
    _default_answer,
    action_for_card,
    battlefield_ids,
    only_oid,
    pass_until,
)

SAGA = "t_saga"  # I draw, II gain 2 life, III make a Human Soldier
SHORT = "t_saga_one_chapter"  # I draw, and that is the whole card
UNFINISHED = "t_saga_unfinished"  # I draw, but `final_chapter: 3`
WATCHER = "t_saga_watcher"  # "whenever a lore counter is put on a permanent you control"
BEAR = "t_bear"
TOKEN = "human_soldier_1_1_w"


def board(
    builder,
    *,
    cards=(SAGA,),
    lore: int | None = None,
    step: Step = Step.PRECOMBAT_MAIN,
    active: int = 0,
):
    """A position with ``cards`` on player 0's battlefield, and the first oid.

    ``advance=False`` throughout: every claim below is about a permanent nobody
    has to play a turn to see, and advancing runs the engine's auto-pass, which
    rolls straight through the precombat main phase this file is mostly about.

    ``lore`` overrides the counter `GameBuilder` gives a placed Saga. Placing a
    Saga is not the same as one entering -- no replacement runs and no chapter
    fires -- which is exactly what makes it a way to stand a Saga part-way
    through its story.
    """
    b = builder().battlefield(1, [BEAR]).turn(3).step(step).active(active)
    b = b.battlefield(0, list(cards), counters={sagas.LORE: lore} if lore else None)
    game = b.build(advance=False)
    return game, only_oid(game, cards[0])


def cast_from_hand(builder, card_id: str = SAGA):
    """A game whose only interesting move is casting ``card_id``, already made.

    Built with the ordinary ``advance=True``, unlike :func:`board`: a card has to
    be *cast* for 714.2b to happen at all, and casting needs a player holding
    priority rather than a frozen position.
    """
    game = (
        builder()
        .hand(0, [card_id])
        .battlefield(0, ["plains"] * 5)
        .battlefield(1, [BEAR])
        .build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    return game


def settle(game, limit: int = 60) -> None:
    """Resolve whatever is waiting, answering every decision passively."""
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the chapter never resolved")


def run_step(game) -> None:
    """Run the current step's turn-based actions and nothing after them.

    `GameBuilder.build` leaves `step_started` true -- the position *is* in the
    step rather than about to enter it -- so the actions have notionally happened
    and something must ask for them. Driven directly rather than through
    `game._advance()`, which keeps auto-passing into later turns and would make a
    lore count impossible to attribute to one phase.
    """
    game.state.step_started = False
    gen = turn.begin_step(game.state)
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def chapter_events(game) -> list:
    return [e for e in game.state.events if e.type == EventType.CHAPTER_REACHED]


def chapters(game) -> list[int]:
    return [e.data["chapter"] for e in chapter_events(game)]


def lore(game, oid: int) -> int:
    return game.state.objects[oid].counter(sagas.LORE)


def card(model: dict):
    """Compile one card definition, so a load-time refusal can be asserted."""
    base = {
        "id": "x",
        "name": "X",
        "types": ["Enchantment"],
        "subtypes": ["Saga"],
        "mana_cost": "{2}",
    }
    return compile_card(CardModel.model_validate({**base, **model}))


DRAW = {"op": "draw", "player": "you", "amount": {"const": 1}}


# ----------------------------------------------------------------------
# the card
# ----------------------------------------------------------------------


class TestTheChapterAbility:
    """714.1b: "chapter abilities are triggered abilities"."""

    def test_a_chapter_is_a_triggered_ability(self, registry):
        ability = registry.get(SAGA).abilities[0]
        assert ability.is_chapter
        assert ability.is_triggered, (
            "714.1b says so, and reading it any other way means a second copy of "
            "the trigger pipeline -- collection, APNAP queueing, the stack, "
            "target choice -- for one kind of ability"
        )
        assert ability.chapter == 1

    def test_the_trigger_comes_from_the_rules(self, registry):
        """No card writes it, because the printed line has no word for *when*.

        "II — Create two 2/2 red Human Knight creature tokens" says what happens
        and never says when. All of the timing is 714.2c, so the loader supplies
        the trigger for the same reason it supplies `source: "self"` on
        `self_enters` -- and with a stronger argument, since here there is
        nothing an author could even leave out.
        """
        spec = registry.get(SAGA).abilities[1].trigger
        assert spec is not None
        assert (spec.event, spec.source, spec.chapter) == ("chapter", "self", 2)

    def test_the_final_chapter_is_derived(self, registry):
        assert registry.get(SAGA).final_chapter == 3
        assert registry.get(SHORT).final_chapter == 1

    def test_a_declared_final_chapter_outranks_the_derivation(self, registry):
        """The one case the field exists for: a Saga with a chapter unwritten.

        Derived, this card's final chapter would be I, and 704.5s would bin it
        two chapters early -- a strictly better card than the printed one,
        arriving in silence. Declared, it sits out II and III doing nothing,
        which is the printed card minus two lines and is visible to anyone who
        plays it.
        """
        assert registry.get(UNFINISHED).final_chapter == 3

    def test_a_non_saga_may_not_print_a_chapter(self):
        with pytest.raises(DslError, match="Saga"):
            card({
                "subtypes": [],
                "abilities": [{"kind": "chapter", "chapter": 1, "effects": [DRAW]}],
            })

    def test_a_saga_with_no_chapters_is_an_inert_proxy(self):
        """Allowed, and it is what `data/generated/` makes of an unimplemented one.

        A proxy prints the real name, cost, colours and type line with its rules
        text doing nothing, and seven Sagas in the catalog are proxied that way.
        Refusing the shape would make those cards unrepresentable rather than
        unimplemented -- so instead `final_chapter` is `None`, which is what
        every rule in `engine.sagas` tests: no lore counter as it enters, nothing
        to advance, nothing to be sacrificed for reaching. 704.5s agrees, asking
        for "a Saga permanent **with one or more chapter abilities**".

        An *authored* Saga cannot use the same hole: its printed chapter lines
        would go unclaimed and the residual gate would reject the card.
        """
        inert = card({"abilities": []})
        assert inert.final_chapter is None
        assert inert.replacements == ()

    def test_a_chapter_may_not_write_its_own_trigger(self):
        with pytest.raises(DslError, match=r"714\.2c"):
            card({
                "abilities": [{
                    "kind": "chapter", "chapter": 1, "effects": [DRAW],
                    "trigger": {"event": "upkeep"},
                }],
            })

    def test_a_final_chapter_below_the_last_one_written_is_refused(self):
        with pytest.raises(DslError, match="could never trigger"):
            card({
                "final_chapter": 1,
                "abilities": [
                    {"kind": "chapter", "chapter": 1, "effects": [DRAW]},
                    {"kind": "chapter", "chapter": 2, "effects": [DRAW]},
                ],
            })

    def test_chapter_is_refused_on_any_other_kind(self):
        with pytest.raises(DslError, match="only means anything on a chapter"):
            card({
                "abilities": [
                    {"kind": "chapter", "chapter": 1, "effects": [DRAW]},
                    {"kind": "triggered", "chapter": 2, "effects": [DRAW],
                     "trigger": {"event": "upkeep"}},
                ],
            })

    def test_a_chapter_cannot_be_granted_to_something_else(self):
        """`is_triggered` is True for a chapter, and grantability is not.

        A granted chapter would wait on a comparison against lore counters on a
        creature, which nothing puts there -- so it would be accepted and never
        fire, the "looks implemented, does nothing" shape the loader's grantable
        check exists to refuse.
        """
        with pytest.raises(DslError, match="not chapter"):
            card({
                "abilities": [{"kind": "chapter", "chapter": 1, "effects": [DRAW]}],
                "grantable_abilities": [
                    {"kind": "chapter", "chapter": 1, "effects": [DRAW]}
                ],
            })


# ----------------------------------------------------------------------
# 714.2b -- the counter it enters with
# ----------------------------------------------------------------------


class TestEnteringWithALoreCounter:
    """714.2b: "as a Saga enters, its controller puts a lore counter on it"."""

    def cast_it(self, builder, card_id: str = SAGA):
        """Cast a Saga from hand for real and let everything settle."""
        game = cast_from_hand(builder, card_id)
        settle(game)
        return game

    def test_it_is_a_replacement_and_not_a_trigger(self, registry):
        """The counter is compiled onto the card the way loyalty is.

        Both are a number the *rules* turn into counters as the permanent
        enters, so both are one `self_enters_with_counters` entry the loader
        writes and no author does.
        """
        entries = [
            r for r in registry.get(SAGA).replacements
            if r.get("counter") == sagas.LORE
        ]
        assert entries == [{
            "event": "self_enters_with_counters",
            "counter": "lore",
            "amount": 1,
            "modify": {},
            "condition": None,
        }]

    def test_a_cast_saga_arrives_with_one(self, builder):
        game = self.cast_it(builder)
        assert lore(game, only_oid(game, SAGA)) == 1

    def test_chapter_one_resolves_off_the_entry_counter(self, builder):
        """The whole point of 714.2b: chapter I happens when the Saga lands.

        `t_saga`'s chapter I draws, so a hand that went from empty to one card is
        the observation. Without the entry counter a Saga would sit dormant until
        its controller's next precombat main phase, which is a turn of delay on
        every Saga ever printed.
        """
        game = self.cast_it(builder)
        assert chapters(game) == [1]
        assert len(game.state.players[0].hand) == 1

    def test_the_counter_is_on_before_the_enters_event(self, builder):
        """Written as a `self_enters` trigger it would not be.

        Every other enters trigger on the board reads the Saga as it arrives, and
        614.1c's rule for entering-with is that the permanent is *never seen*
        without them. The order of the events is the observable form of that:
        the replacement writes the counter directly, and by ENTERS_BATTLEFIELD it
        is already there. Its one COUNTER_PLACED (122.6: a counter given as it
        enters is still "put" on it) is reported after the arrival, and it
        reaches no second chapter I.
        """
        game = self.cast_it(builder)
        oid = only_oid(game, SAGA)
        entered = next(
            e for e in game.state.events
            if e.type == EventType.ENTERS_BATTLEFIELD and e.data.get("oid") == oid
        )
        reached = next(e for e in chapter_events(game))
        assert game.state.events.index(entered) < game.state.events.index(reached)
        placed = [
            e for e in game.state.events
            if e.type == EventType.COUNTER_PLACED and e.data.get("oid") == oid
        ]
        assert [(e.data["counter"], e.data["amount"]) for e in placed] == [(sagas.LORE, 1)]
        assert game.state.events.index(entered) < game.state.events.index(placed[0])
        assert chapters(game) == [1]

    def test_a_one_chapter_saga_is_cast_and_gone(self, builder):
        """I, then 704.5s, in the one window between the cast and priority.

        The shortest complete Saga there is, and it exercises the whole rule in
        one resolution: it enters with its final chapter's worth of lore
        counters, chapter I triggers off that, and the state-based action bins it
        as soon as chapter I has left the stack.
        """
        game = self.cast_it(builder, SHORT)
        assert chapters(game) == [1]
        assert len(game.state.players[0].hand) == 1
        assert SHORT not in battlefield_ids(game, 0)
        assert [
            o.def_id for o in game.state.objects.values() if o.zone is Zone.GRAVEYARD
        ].count(SHORT) == 1


# ----------------------------------------------------------------------
# 714.2d -- the tick
# ----------------------------------------------------------------------


class TestTheTurnBasedAction:
    """714.2d: a lore counter on each Saga you control, as your precombat main begins."""

    def test_the_precombat_main_phase_adds_one(self, builder):
        game, oid = board(builder, lore=1)
        run_step(game)
        assert lore(game, oid) == 2

    def test_it_advances_the_chapter(self, builder):
        game, _oid = board(builder, lore=1)
        run_step(game)
        settle(game)
        assert chapters(game) == [2]
        assert game.state.players[0].life == 42, "chapter II gains 2 life"

    def test_it_is_the_active_player_s_sagas_only(self, builder):
        """"each Saga **they** control", where they is the active player.

        This is the half a `draw_step` trigger gets wrong by default: DRAW_STEP
        fires on every player's draw step, so a Saga built on it advances twice a
        round unless every card in the pool remembers `is_your_turn`. Here the
        rule holds the gate and no card can forget it.
        """
        game, oid = board(builder, lore=1, active=1)
        run_step(game)
        assert lore(game, oid) == 1

    def test_every_saga_you_control_advances(self, builder):
        game = (
            builder()
            .battlefield(0, [SAGA, SAGA])
            .battlefield(1, [BEAR])
            .turn(3)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oids = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == SAGA]
        run_step(game)
        assert [lore(game, oid) for oid in oids] == [2, 2]

    def test_nothing_goes_on_the_stack(self, builder):
        """A turn-based action, so there is nothing to respond to.

        The counter and the chapter it causes are one uninterrupted event: the
        counter is placed with nobody holding priority, and only the chapter
        *ability* -- which is a real triggered ability -- uses the stack. Written
        as a trigger, an opponent would get a window between the two and could
        answer the Saga after it had already advanced.
        """
        game, oid = board(builder, lore=1)
        run_step(game)
        assert game.state.stack == []
        assert [t.source_oid for t in game.state.pending_triggers] == [oid]

    def test_the_placement_is_an_ordinary_counter_placement(self, builder):
        """Through `add_counters`, so everything watching counters sees it.

        `t_saga_watcher` reads "whenever a lore counter is put on a permanent you
        control". A tick written as a direct `obj.add_counter` would be invisible
        to it, and to `proliferate`'s notion of what is on the board.
        """
        game = (
            builder()
            .battlefield(0, [SAGA, WATCHER])
            .battlefield(1, [BEAR])
            .turn(3)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        run_step(game)
        placed = [
            e for e in game.state.events
            if e.type == EventType.COUNTER_PLACED and e.data.get("counter") == sagas.LORE
        ]
        assert len(placed) == 1
        settle(game)
        assert len(game.state.players[0].hand) == 1, "the watcher saw the tick"
        assert game.state.players[0].life == 42, "and chapter II happened as well"


# ----------------------------------------------------------------------
# 714.2c -- reaching, not placing
# ----------------------------------------------------------------------


class TestChaptersTriggerOnReaching:
    """714.2c: the count **becomes** N, having been below it."""

    def test_a_chapter_fires_when_the_count_reaches_it(self, builder):
        game, oid = board(builder, lore=1)
        add_counters(game.state, oid, sagas.LORE, 1)
        assert chapters(game) == [2]

    def test_two_counters_at_once_fire_two_chapters_in_order(self, builder):
        """Proliferate is one placement; skipping a chapter is not allowed.

        A Saga taken from I to III fires II and then III, and in that order,
        because 714.2c is a comparison against each ability's number rather than
        a reaction to a placement. Written against the placement, the card would
        fire once -- and against the total, it would fire III alone and quietly
        skip a chapter's worth of card.
        """
        game, oid = board(builder, lore=1)
        add_counters(game.state, oid, sagas.LORE, 2)
        assert chapters(game) == [2, 3]

    def test_a_counter_that_reaches_nothing_new_fires_nothing(self, builder):
        """The other half of "was less than the number before".

        A Saga already at III that gains a fourth lore counter has reached no new
        chapter. Written against the total rather than the crossing, chapter III
        would fire again on every counter of every kind for the rest of the game.
        """
        game, oid = board(builder, lore=3)
        add_counters(game.state, oid, sagas.LORE, 1)
        assert chapters(game) == []

    def test_a_counter_removed_and_put_back_re_triggers(self, builder):
        """714.2c is about the crossing, so crossing twice fires twice.

        The boundary that makes "reaching" the right word rather than a
        paraphrase of "the total is now N": remove the second counter and put it
        back, and chapter II happens again. That is the rule, and it is what
        makes the comparison have to be before/after rather than a high-water
        mark.
        """
        game, oid = board(builder, lore=2)
        remove_counters(game.state, oid, sagas.LORE, 1)
        add_counters(game.state, oid, sagas.LORE, 1)
        assert chapters(game) == [2]

    def test_only_the_saga_that_reached_it_fires(self, builder):
        """`source: "self"` on the supplied trigger, and it is load-bearing.

        One CHAPTER_REACHED event exists per Saga per number, and every chapter
        ability on the table is a candidate for every one of them. Without the
        self-scope a table with two Sagas would run both of them off one tick.
        """
        game = (
            builder()
            .battlefield(0, [SAGA, SAGA])
            .battlefield(1, [BEAR])
            .turn(3)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oids = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == SAGA]
        add_counters(game.state, oids[0], sagas.LORE, 1)
        assert [t.source_oid for t in game.state.pending_triggers] == [oids[0]]

    def test_a_number_the_card_prints_no_ability_for_fires_nothing(self, builder):
        """`t_saga_unfinished` prints I and declares III as its last chapter."""
        game, oid = board(builder, cards=(UNFINISHED,), lore=1)
        add_counters(game.state, oid, sagas.LORE, 1)
        assert chapters(game) == []

    def test_a_counter_of_another_kind_advances_nothing(self, builder):
        game, oid = board(builder, lore=1)
        add_counters(game.state, oid, "+1/+1", 2)
        assert chapters(game) == []

    def test_a_lore_counter_on_something_that_is_not_a_saga(self, builder):
        game, _ = board(builder)
        bear = only_oid(game, BEAR, 1)
        add_counters(game.state, bear, sagas.LORE, 5)
        assert chapters(game) == []


# ----------------------------------------------------------------------
# 704.5s -- the sacrifice
# ----------------------------------------------------------------------


class TestTheSacrifice:
    """704.5s: at or past the final chapter, with no chapter on the stack."""

    def test_a_finished_saga_is_sacrificed(self, builder):
        game, oid = board(builder, lore=3)
        sba.run(game.state)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_it_waits_for_its_own_last_chapter(self, builder):
        """The clause that makes the state-based action the right shape.

        Appended to chapter III's effects, the sacrifice would happen part-way
        through chapter III resolving -- so on Oath of Eorl, whose chapter III
        puts a counter on a creature and *then* grants the crown, the crown would
        be handed out by a permanent already in a graveyard. 704.5s waits for the
        chapter to leave the stack, and this is that wait.
        """
        game, oid = board(builder, lore=2)
        add_counters(game.state, oid, sagas.LORE, 1)
        assert lore(game, oid) == 3
        sba.run(game.state)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD, (
            "chapter III has triggered and has not left the stack"
        )
        settle(game)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert battlefield_ids(game, 0).count(TOKEN) == 1, "chapter III still resolved"

    def test_the_wait_covers_the_queue_as_well_as_the_stack(self, builder):
        """"Triggered but hasn't left the stack" starts before it gets there.

        State-based actions run *before* a player would receive priority, which
        is the same moment `drain_to_stack` is about to use -- so a chapter
        spends this window in `pending_triggers` and not on the stack at all.
        Checking `state.stack` alone would sacrifice every Saga the instant its
        final chapter triggered, and throw that chapter away with it.
        """
        game, oid = board(builder, lore=2)
        add_counters(game.state, oid, sagas.LORE, 1)
        assert game.state.stack == []
        assert [t.source_oid for t in game.state.pending_triggers] == [oid]
        assert sagas.chapter_on_stack(game.state, oid)
        assert not sagas.finished(game.state, oid)

    def test_overshooting_the_final_chapter_still_finishes_it(self, builder):
        """"Greater than **or equal to**", and the difference is a proliferate.

        An equality test would leave a Saga proliferated past its last chapter on
        the battlefield for the rest of the game -- a permanent with no way to
        ever be finished, which is the direction nothing complains about.
        """
        game, oid = board(builder, lore=5)
        sba.run(game.state)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_a_saga_short_of_its_last_chapter_stays(self, builder):
        game, oid = board(builder, lore=2)
        sba.run(game.state)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD

    def test_a_saga_whose_last_chapter_is_unwritten_still_finishes(self, builder):
        """`final_chapter` is what 704.5s compares against, not the last ability.

        `t_saga_unfinished` prints chapter I only and declares III. It is
        sacrificed at three lore counters, having done nothing since I -- the
        printed card minus two lines, rather than a card that ends two turns
        early.
        """
        game, oid = board(builder, cards=(UNFINISHED,), lore=3)
        sba.run(game.state)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_it_is_a_sacrifice_and_not_a_destruction(self, builder):
        """So indestructible does not save it (701.17b).

        Worth pinning because the alternative is not "a Saga that survives" but
        "a Saga that is finished and can never leave", and an opponent making
        your Saga indestructible is a real play.
        """
        game, oid = board(builder, lore=3)
        add_counters(game.state, oid, "indestructible", 1)
        sba.run(game.state)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert [
            e for e in game.state.events
            if e.type == EventType.SACRIFICED and e.data.get("oid") == oid
        ], "a sacrifice, so 'whenever you sacrifice a permanent' sees it"

    def test_a_non_saga_with_lore_counters_is_left_alone(self, builder):
        game, _ = board(builder)
        bear = only_oid(game, BEAR, 1)
        add_counters(game.state, bear, sagas.LORE, 9)
        sba.run(game.state)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD


# ----------------------------------------------------------------------
# the whole story
# ----------------------------------------------------------------------


class TestTheWholeStory:
    def test_three_turns_from_cast_to_graveyard(self, builder):
        """The card as a player experiences it, which no single rule above is.

        Cast on turn 3: chapter I now, chapter II at the next precombat main,
        chapter III the one after, then the graveyard. It is here because the
        four rules are only correct *together* -- an entry counter with no tick
        stalls at I, a tick with no sacrifice never ends, and a sacrifice
        checked one moment earlier eats chapter III.
        """
        game = cast_from_hand(builder, SAGA)
        settle(game)
        oid = only_oid(game, SAGA)
        start = game.state.turn
        assert (chapters(game), lore(game, oid)) == ([1], 1)

        pass_until(game, lambda g: g.state.turn == start + 2)
        settle(game)
        assert chapters(game) == [1, 2]
        assert game.state.players[0].life == 42

        pass_until(game, lambda g: g.state.turn == start + 4)
        settle(game)
        assert chapters(game) == [1, 2, 3]
        assert battlefield_ids(game, 0).count(TOKEN) == 1
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
