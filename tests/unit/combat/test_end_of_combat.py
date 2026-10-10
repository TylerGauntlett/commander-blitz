"""Scheduling something for "at end of combat" — and for *which* combat.

    Flamerush Rider — "Whenever this creature attacks, create a token that's a
    copy of another target attacking creature and that's tapped and attacking.
    **Exile the token at end of combat.**"

Rule 511 gives every combat phase an end of combat step, and `Step.END_OF_COMBAT`
has always existed and always been walked through — but nothing could be attached
to it, because `turn.DELAY_STEPS` named only `upkeep`, `draw_step`,
`begin_combat` and `end_step`. `{"op": "delay", "step": "end_of_combat"}` was a
load error, and the nearest reachable step is not a rounding error on this card:
a token exiled at the *end step* survives the whole postcombat main phase, where
it can be sacrificed for value, tapped for an ability, or — since `extra_combat`
shipped — **attack again in a second combat**. Stopping exactly that is what the
printed line is for.

Which makes the second question the substance rather than the first. Every other
delay step happens once a turn, so its name is the whole of its timing. A combat
phase does not: Relentless Assault, Combat Celebrant, Aggravated Assault and
Seize the Day all give a turn two or three of them. So "at end of combat" is
defined here as **the end of the combat the delay was created in** (rule 603.7),
and outside a combat phase as the end of the next combat to begin.

`GameState.combat_number` is the identity that lets the engine say that.
`CombatState` cannot: `combat.end_combat` throws it away as the END_OF_COMBAT
step begins, which is *before* `_run_delayed` reads anything. So `op_delay`
stamps the number and `turn._delay_due` compares it.

**Honest about what the stamp changes today: nothing observable.** In the turn
machine as it stands, "the combat it was created in" and "the next END_OF_COMBAT
step" are the same step, because every combat that begins reaches its own end of
combat step before any later combat begins — including a combat nobody attacked
in, which `turn.next_step` routes straight there. The stamp is what makes that a
*statement* instead of a coincidence: it is the difference between an exile that
is timed to a combat and one that is timed to whichever end of combat step comes
round next, and only the first stays right if a future effect ever ends a combat
phase early. `TestTheStampIsAGuard` is the part of that which is not visible from
a card.

The witnesses are `t_rider` (Flamerush Rider's shape: an attack trigger that
copies itself tapped and attacking, then delays the exile), `t_ephemeral_host`
(a sorcery that schedules the same exile from a main phase, where there is no
combat to belong to) and `t_second_wind` (Combat Celebrant's: an attack trigger
that grants an extra combat from inside declare-attackers), played together so
the exile and the second combat race each other.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import CombatState, DelayedTrigger
from commanderblitz.engine.turn import DELAY_STEPS, _delay_due
from tests.conftest import _default_answer, action_for_card, find_action, oids_of

RIDER = "t_rider"  # attacks: copy itself tapped and attacking; exile it at EOC
HOST = "t_ephemeral_host"  # sorcery: make a Warrior token; exile it at EOC
SECOND_WIND = "t_second_wind"  # attacks: untap the others, +1 combat phase
WARRIOR = "t_warrior_token"
BEAR = "t_bear"
MOUNTAIN = "mountain"


# ----------------------------------------------------------------------
# positions and observation
# ----------------------------------------------------------------------


def rider_position(builder, *, extra_combat: bool = False):
    """A board that will attack, and optionally get a second combat for it.

    `t_second_wind` grants its extra combat from *inside* declare-attackers, so
    the grant and the delayed exile are created during the same combat — the one
    arrangement in which "this combat" and "the turn" can be told apart.
    """
    others = [SECOND_WIND] if extra_combat else []
    return (
        builder(players=2)
        .battlefield(0, [RIDER, *others])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def host_position(builder):
    return (
        builder(players=2)
        .battlefield(0, [MOUNTAIN] * 2)
        .hand(0, [HOST])
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def play_turn(game, *, attack: bool = True, limit: int = 400) -> None:
    """Play the active turn to its end, attacking with everything."""
    turn = game.state.turn
    for _ in range(limit):
        if game.over or game.state.turn != turn:
            return
        decision = game.pending()
        if decision is None:
            return
        if attack and decision.kind is DecisionKind.DECLARE_ATTACKERS:
            for add in [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]:
                game.apply(add)
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        game.apply(_default_answer(game, decision))


def stop_at(game, step: Step, *, attack: bool = True, skip_current: bool = False, limit: int = 400):
    """Play forward and stand in ``step``, without answering its decision.

    Only usable for steps that hand a player a decision: the engine runs straight
    through the ones that do not, so `END_OF_COMBAT` is never a place a test can
    stand. That is what the event log above is for.

    ``skip_current`` steps past the occurrence the game is already standing in,
    which is how a test walks from one combat's declare-attackers to the next's.
    """
    was = game.state.step if skip_current else None
    for _ in range(limit):
        if game.state.step is step and was is not step:
            return
        was = game.state.step
        if game.over:
            raise AssertionError(f"the game ended before {step.name}")
        decision = game.pending()
        if decision is None:
            raise AssertionError(f"nothing left to decide before {step.name}")
        if attack and decision.kind is DecisionKind.DECLARE_ATTACKERS:
            for add in [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]:
                game.apply(add)
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never reached {step.name}")


def exiles_of(game, card_id: str) -> list[tuple[int, int, int]]:
    """Every exile of ``card_id``, as ``(turn, step, which combat of that turn)``.

    Read off the event log rather than sampled from the board, because the claim
    is about *when*: a token that has ended up in exile says nothing about
    whether it went at the end of combat, at the end step, or on the way out of
    the turn.

    The third number is the 0-based combat within its turn — counted by how many
    end of combat steps that turn had already finished — which is what pins an
    exile to a particular combat rather than to a moment. One exile with a zero
    and one with a one is two combats each ending their own token.
    """
    ended = 0
    turn = None
    out: list[tuple[int, int, int]] = []
    for event in game.state.events:
        if event.turn != turn:
            turn, ended = event.turn, 0
        if event.type == EventType.STEP_ENDED and event.data.get("step") == "END_OF_COMBAT":
            ended += 1
        elif (
            event.type == EventType.ZONE_CHANGE
            and event.data.get("to") == Zone.EXILE.value
            and event.data.get("card") == card_id
        ):
            out.append((event.turn, event.step, ended))
    return out


def steps_of(game, turn: int) -> list[str]:
    return [
        str(e.data["step"])
        for e in game.state.events
        if e.type == EventType.STEP_ENDED and e.turn == turn
    ]


def copies_of(game, card_id: str) -> list[int]:
    """The token copies on the battlefield — everything but the original."""
    return [oid for oid in oids_of(game, card_id) if game.state.objects[oid].is_token]


# ----------------------------------------------------------------------


class TestTheStepIsReachableAtAll:
    """Before this, `{"step": "end_of_combat"}` was a load error."""

    def test_end_of_combat_is_a_delay_step(self):
        assert DELAY_STEPS["end_of_combat"] is Step.END_OF_COMBAT

    def test_the_loader_accepts_it(self):
        _validate_effect(
            {"op": "delay", "step": "end_of_combat", "effects": [{"op": "noop"}]},
            "test",
            {},
        )

    def test_a_misspelling_is_still_refused(self):
        """What makes the whitelist worth having: `end_combat` is not the name."""
        with pytest.raises(DslError, match="unknown delay step"):
            _validate_effect(
                {"op": "delay", "step": "end_combat", "effects": [{"op": "noop"}]},
                "test",
                {},
            )

    def test_the_four_older_steps_are_untouched(self):
        assert set(DELAY_STEPS) == {
            "upkeep",
            "draw_step",
            "begin_combat",
            "end_of_combat",
            "end_step",
        }


class TestTheTokenGoesAtTheEndOfCombat:
    """Flamerush Rider's second sentence, on a card, in a real combat."""

    def test_the_copy_is_made_and_is_attacking(self, builder):
        game = rider_position(builder)
        stop_at(game, Step.DECLARE_BLOCKERS)

        copies = copies_of(game, RIDER)
        assert len(copies) == 1, "the attack trigger made it"
        assert game.state.combat is not None and game.state.combat.attacking(copies[0])

    def test_the_exile_happens_in_the_end_of_combat_step(self, builder):
        """The claim, at the resolution the substitute step would have got wrong."""
        game = rider_position(builder)
        turn = game.state.turn
        play_turn(game)

        assert exiles_of(game, RIDER) == [(turn, Step.END_OF_COMBAT, 0)]

    def test_it_is_gone_by_the_postcombat_main_phase(self, builder):
        """`end_step` would have left it here, alive for a whole main phase."""
        game = rider_position(builder)
        stop_at(game, Step.POSTCOMBAT_MAIN)

        assert copies_of(game, RIDER) == []
        assert len(oids_of(game, RIDER)) == 1, "the original is still there"

    def test_it_hits_before_it_leaves(self, builder):
        """Created tapped and attacking, so the damage is real and comes first."""
        game = rider_position(builder)
        life = game.state.players[1].life
        power = game.state.registry.get(RIDER).power

        play_turn(game)

        assert game.state.players[1].life == life - 2 * power

    def test_the_delay_does_not_outlive_its_step(self, builder):
        game = rider_position(builder)
        stop_at(game, Step.POSTCOMBAT_MAIN)

        assert game.state.delayed_triggers == []


class TestWhenThereIsNoCombatInProgress:
    """Scheduled outside a combat phase, it waits for the next one's end."""

    def test_it_is_exiled_at_the_end_of_that_turns_combat(self, builder):
        """`combat_number + 1` is *this* turn's combat, not the next turn's."""
        game = host_position(builder)
        turn = game.state.turn
        game.apply(action_for_card(game, ActionKind.CAST, HOST))
        play_turn(game, attack=False)

        assert exiles_of(game, WARRIOR) == [(turn, Step.END_OF_COMBAT, 0)]
        assert oids_of(game, WARRIOR) == []

    def test_a_combat_nobody_attacked_in_still_ends_it(self, builder):
        """The other route into `END_OF_COMBAT`, and why the strict match is safe.

        With nothing able to attack, `turn.next_step` sends declare-attackers
        straight to the end of combat step, skipping blockers and both damage
        steps. It is still that combat's end and the delay is still due there —
        so no reachable combat can begin and never reach the step its delays are
        stamped for.
        """
        game = host_position(builder)
        turn = game.state.turn
        game.apply(action_for_card(game, ActionKind.CAST, HOST))
        play_turn(game, attack=False)

        steps = steps_of(game, turn)
        assert "DECLARE_BLOCKERS" not in steps, "nothing attacked"
        assert steps.count("END_OF_COMBAT") == 1
        assert exiles_of(game, WARRIOR) == [(turn, Step.END_OF_COMBAT, 0)]


class TestWhichCombatItIs:
    """A turn with two combats, and a token that belongs to exactly one of them."""

    def test_the_turn_really_has_two_combats(self, builder):
        game = rider_position(builder, extra_combat=True)
        turn = game.state.turn
        play_turn(game)

        assert steps_of(game, turn).count("END_OF_COMBAT") == 2

    def test_the_first_token_is_gone_before_the_second_combat(self, builder):
        """The printed line's whole purpose: the copy must not attack again.

        `t_second_wind` untaps the other creatures as it attacks, so a token that
        survived the first end of combat would be untapped, unsick and on the
        board when attackers are declared for the second combat.
        """
        game = rider_position(builder, extra_combat=True)
        turn = game.state.turn
        stop_at(game, Step.DECLARE_BLOCKERS)

        assert len(copies_of(game, RIDER)) == 1, "the first combat's copy is here"

        stop_at(game, Step.DECLARE_ATTACKERS)  # the second combat's

        assert copies_of(game, RIDER) == [], "nothing left over from the first combat"
        assert exiles_of(game, RIDER) == [(turn, Step.END_OF_COMBAT, 0)], "already gone"

    def test_each_token_is_exiled_at_its_own_combats_end(self, builder):
        """Two tokens, two end of combat steps, one each and in that order.

        The rider attacks in both combats, so the second one makes a copy of its
        own. The first exile happens with no end of combat step behind it and the
        second with exactly one, which is the two of them being timed to their
        own combats rather than both waiting for a single moment.
        """
        game = rider_position(builder, extra_combat=True)
        turn = game.state.turn
        play_turn(game)

        assert exiles_of(game, RIDER) == [
            (turn, Step.END_OF_COMBAT, 0),
            (turn, Step.END_OF_COMBAT, 1),
        ]
        assert len(oids_of(game, RIDER)) == 1, "the rider itself survived both"
        assert game.state.delayed_triggers == [], "neither delay is left over"

    def test_the_second_combat_is_two_attackers_short_of_the_first(self, builder):
        """The damage, which is what a player would notice.

        First combat: rider, its copy and the granting creature. Second: the
        rider and *its* new copy — the granter is tapped and the first copy is
        in exile. A first token that survived would add its power again.
        """
        game = rider_position(builder, extra_combat=True)
        life = game.state.players[1].life
        rider = game.state.registry.get(RIDER).power
        wind = game.state.registry.get(SECOND_WIND).power

        play_turn(game)

        assert game.state.players[1].life == life - (2 * rider + wind) - 2 * rider


class TestWhatOpDelayRecords:
    """The stamp itself, read off `state.delayed_triggers`."""

    def schedule(self, game, step: str = "end_of_combat") -> DelayedTrigger:
        ctx = EffectContext(state=game.state, controller=0)
        for _ in execute_one(
            ctx, {"op": "delay", "step": step, "effects": [{"op": "noop"}]}
        ):  # pragma: no cover - `delay` asks nothing
            pass
        return game.state.delayed_triggers[-1]

    def test_inside_a_combat_it_names_that_combat(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [BEAR])
            .step(Step.DECLARE_ATTACKERS)
            .build(advance=False)
        )
        game.state.combat = CombatState(declaring_player=0)
        game.state.combat_number = 4

        assert self.schedule(game).combat == 4

    def test_outside_a_combat_it_names_the_next_one(self, builder):
        game = builder(players=2).step(Step.PRECOMBAT_MAIN).build(advance=False)
        game.state.combat_number = 4
        game.state.combat = None

        assert self.schedule(game).combat == 5

    def test_during_the_end_of_combat_step_it_names_the_next_one(self, builder):
        """603.7: this step's own firing has already been and gone.

        `combat.end_combat` clears `state.combat` as the step begins and
        `_run_delayed` runs immediately after, so anything resolving in the
        step's priority window is scheduling for a combat still to come.
        """
        game = (
            builder(players=2).battlefield(0, [BEAR]).step(Step.END_OF_COMBAT).build()
        )
        before = game.state.combat_number

        assert game.state.combat is None, "`end_combat` has already run"
        assert self.schedule(game).combat == before + 1

    def test_the_other_steps_record_no_combat(self, builder):
        """They happen once a turn, so the step name is the whole of the timing."""
        game = builder(players=2).step(Step.PRECOMBAT_MAIN).build(advance=False)

        assert self.schedule(game, "end_step").combat is None
        assert self.schedule(game, "upkeep").combat is None


class TestTheStampIsAGuard:
    """`_delay_due` directly — the part of "this combat" a card cannot show.

    Every combat reachable today ends in its own END_OF_COMBAT step before any
    later one begins, so a bare step-name match happens to pick the same moment.
    These are the assertions that keep it a statement rather than a coincidence.
    """

    def position(self, builder):
        game = builder(players=2).step(Step.END_OF_COMBAT).build(advance=False)
        game.state.combat_number = 2
        return game

    def delay(self, combat: int | None) -> DelayedTrigger:
        return DelayedTrigger(step="end_of_combat", controller=0, combat=combat)

    def test_it_is_due_at_the_combat_it_names(self, builder):
        game = self.position(builder)

        assert _delay_due(game.state, self.delay(2))

    def test_it_is_not_due_at_a_later_combat(self, builder):
        """The exile would land on the extra combat the card exists to skip."""
        game = self.position(builder)

        assert not _delay_due(game.state, self.delay(1))

    def test_it_is_not_due_at_an_earlier_combat(self, builder):
        game = self.position(builder)

        assert not _delay_due(game.state, self.delay(3))

    def test_it_is_never_due_in_another_step(self, builder):
        game = builder(players=2).step(Step.END_STEP).build(advance=False)
        game.state.combat_number = 2

        assert not _delay_due(game.state, self.delay(2))

    def test_an_unstamped_delay_is_due_on_the_step_name_alone(self, builder):
        """The four older steps, unchanged: no combat to compare, so no compare."""
        game = builder(players=2).step(Step.END_STEP).build(advance=False)

        assert _delay_due(game.state, DelayedTrigger(step="end_step", controller=0))


class TestCombatNumberItself:
    def test_a_second_combat_gets_its_own_number(self, builder):
        game = rider_position(builder, extra_combat=True)
        stop_at(game, Step.DECLARE_ATTACKERS)
        first = game.state.combat_number

        stop_at(game, Step.DECLARE_ATTACKERS, skip_current=True)

        assert game.state.combat_number == first + 1

    def test_it_does_not_restart_each_turn(self, builder):
        """Monotonic, so `combat_number + 1` is never a number already used."""
        game = rider_position(builder)
        stop_at(game, Step.DECLARE_ATTACKERS)
        turn, first = game.state.turn, game.state.combat_number

        stop_at(game, Step.DECLARE_ATTACKERS, skip_current=True)

        assert game.state.turn > turn, "a later turn's combat"
        assert game.state.combat_number > first
