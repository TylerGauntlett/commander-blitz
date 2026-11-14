"""An additional beginning phase.

    Sphinx of the Second Sun -- "At the beginning of each of your postcombat
    main phases, there is an additional beginning phase after this phase. (The
    beginning phase includes the untap, upkeep, and draw steps.)"

Rules 500.8 and 501-504. The queue that holds an extra combat and an extra main
(`GameState.extra_phases`, `resume_step`) holds this too: a `"beginning"` kind
entered at `Step.UNTAP`, walked through upkeep and draw, and handed back to the
turn at the end of the draw step. What would each be wrong while looking right:

- **The steps must be real.** The untap step untaps, the draw step draws, and
  every upkeep and draw-step trigger fires again. A version that mimicked the
  pieces with an untap op and a draw op would leave the triggers silent.
- **It is not a new turn.** The untap step is also where the engine starts a
  turn -- land drops, cards drawn this turn, "until your next turn" clocks --
  and a second untap step that ran all of that would hand out a second land
  drop and forget the turn's draws. Only 502.1-502.3 run again.
- **"Each of your postcombat main phases" includes an added one** (505.1a), so
  Relentless Assault under the Sphinx makes two beginning phases, and 500.8 puts
  the most recently created phase first when two are added after one phase.
- **A grant made inside it waits for a main phase**, as one made in a turn's own
  upkeep always did, rather than slipping in before the turn resumes.
- **"The next turn's upkeep" is not "the next upkeep"** once a turn can have two
  (`delay`'s `next_turn`: Portent against The Eagles Are Coming).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.state import MAX_EXTRA_PHASES_PER_TURN
from commanderblitz.engine.turn import grant_extra_phases
from tests.conftest import _default_answer, only_oid

SECOND_SUN = "t_second_sun"  # at each of your postcombat mains: +1 beginning phase
SPHINX = "sphinx_of_the_second_sun"  # the shipped card
UPKEEP_GAINER = "t_upkeep_wizard"  # at the beginning of your upkeep, gain 1
DRAW_GAINER = "t_draw_step_gainer"  # at the beginning of your draw step, gain 1
ASSAULT = "t_assault"  # untap your creatures; +1 combat phase, +1 main phase
NEXT_TURNS_UPKEEP = "t_next_turns_upkeep"  # gain 3 at the next turn's upkeep
NEXT_UPKEEP = "t_next_upkeep"  # gain 3 at the next upkeep
WEREWOLF = "t_werewolf"  # daybound

BOLT = "t_bolt"
BOLT_LAND = "mountain"

BEGINNING = ["UNTAP", "UPKEEP", "DRAW"]


def board(builder, mine=(), *, hand=(), turn: int = 3):
    """Player 0's turn ``turn``, in its precombat main.

    With a Bolt and a Mountain to cast it, so that every priority window is a
    real decision: the auto-pass would otherwise roll through the added upkeep
    -- and the rest of the turn -- before a test could look at it.
    """
    return (
        builder(players=2)
        .battlefield(0, [*mine, BOLT_LAND])
        .hand(0, [*hand, BOLT])
        .library(0, ["swamp"] * 30)
        .library(1, ["swamp"] * 30)
        .turn(turn)
        .active(0)
        .build()
    )


def steps_of(game, turn: int) -> list[str]:
    """Every step that ended during one turn, in order, read off the log."""
    return [
        str(event.data["step"])
        for event in game.state.events
        if event.type == EventType.STEP_ENDED and event.turn == turn
    ]


def play(game, *, until=None, cast: str | None = None, at: Step | None = None) -> None:
    """Answer passively until ``until`` holds or the turn ends.

    ``cast`` is cast the first moment it is legal in step ``at``.
    """
    turn = game.state.turn
    for _ in range(600):
        if game.over or game.state.turn != turn or (until is not None and until(game)):
            return
        decision = game.pending()
        if decision is None:
            return
        if cast is not None and (at is None or game.state.step is at):
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == cast
                ),
                None,
            )
            if action is not None:
                game.apply(action)
                cast = None
                continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the turn did not end")


def in_added_untap(game) -> bool:
    return game.state.step is Step.UNTAP and game.state.resume_step is not None


def in_added_upkeep(game) -> bool:
    return game.state.step is Step.UPKEEP and game.state.resume_step is not None


class TestThePhaseIsInsertedAfterThePostcombatMain:
    def test_the_turn_runs_main_then_untap_upkeep_draw_then_the_end_step(self, builder):
        game = board(builder, [SECOND_SUN])
        turn = game.state.turn
        play(game)

        steps = steps_of(game, turn)
        after = steps.index("POSTCOMBAT_MAIN")
        assert steps[after + 1 : after + 5] == [*BEGINNING, "END_STEP"], steps
        assert steps.count("POSTCOMBAT_MAIN") == 1, "no main phase is added"

    def test_without_the_card_the_turn_is_ordinary(self, builder):
        game = board(builder)
        turn = game.state.turn
        play(game)

        assert "UNTAP" not in steps_of(game, turn)

    def test_the_shipped_card_grants_it(self, builder):
        game = board(builder, [SPHINX])
        turn = game.state.turn
        play(game)

        steps = steps_of(game, turn)
        after = steps.index("POSTCOMBAT_MAIN")
        assert steps[after + 1 : after + 4] == BEGINNING, steps

    def test_it_is_only_its_controllers_turn(self, builder):
        """"Each of **your** postcombat main phases."""
        game = board(builder, [SECOND_SUN])
        play(game)
        turn = game.state.turn
        play(game)

        assert game.state.turn == turn + 1
        assert steps_of(game, turn).count("UNTAP") == 1, "the opponent's own untap step only"


class TestTheStepsAreRealSteps:
    def test_the_untap_step_untaps(self, builder):
        game = board(builder, [SECOND_SUN, "island"])
        land = only_oid(game, "island", 0)
        game.state.objects[land].tapped = True
        play(game, until=lambda g: g.state.step is Step.UPKEEP)

        assert game.state.resume_step is not None, "this is the added upkeep"
        assert not game.state.objects[land].tapped

    def test_a_permanent_that_skips_its_next_untap_spends_it_here(self, builder):
        """"Doesn't untap during its controller's next untap step": this is one."""
        game = board(builder, [SECOND_SUN, "island"])
        land = only_oid(game, "island", 0)
        game.state.objects[land].tapped = True
        game.state.objects[land].skip_next_untap = True
        play(game, until=lambda g: g.state.step is Step.UPKEEP)

        assert game.state.objects[land].tapped
        assert not game.state.objects[land].skip_next_untap

    def test_the_draw_step_draws(self, builder):
        game = board(builder, [SECOND_SUN])
        hand = len(game.state.players[0].hand)
        play(game, until=lambda g: g.state.step is Step.END_STEP)

        assert len(game.state.players[0].hand) == hand + 1

    def test_upkeep_and_draw_step_triggers_fire_again(self, builder):
        game = board(builder, [SECOND_SUN, UPKEEP_GAINER, DRAW_GAINER])
        life = game.state.players[0].life
        play(game, until=lambda g: g.state.step is Step.END_STEP)

        assert game.state.players[0].life == life + 2

    def test_step_is_reads_the_added_step(self, builder):
        game = board(builder, [SECOND_SUN])
        play(game, until=in_added_upkeep)

        assert game.state.step is Step.UPKEEP

    def test_the_upkeep_gives_priority(self, builder):
        """An upkeep is a priority window (503.1), so instants can be cast in it."""
        game = board(builder, [SECOND_SUN])
        play(game, until=in_added_upkeep)

        assert game.pending() is not None
        assert any(a.kind is ActionKind.PASS for a in game.legal_actions())


class TestItIsTheSameTurn:
    def test_no_turn_begins(self, builder):
        game = board(builder, [SECOND_SUN])
        turn = game.state.turn
        begun = game.state.players[0].turns_begun
        play(game, until=lambda g: g.state.step is Step.END_STEP)

        assert game.state.turn == turn
        assert game.state.players[0].turns_begun == begun
        assert not [
            e for e in game.state.events if e.type == EventType.TURN_BEGAN and e.turn == turn
        ]

    def test_the_land_drop_is_not_given_back(self, builder):
        game = board(builder, [SECOND_SUN])
        game.state.players[0].lands_played = 1
        play(game, until=lambda g: g.state.step is Step.END_STEP)

        assert game.state.players[0].lands_played == 1

    def test_the_cards_drawn_this_turn_are_not_forgotten(self, builder):
        game = board(builder, [SECOND_SUN])
        game.state.cards_drawn_this_turn[0] = 2
        play(game, until=lambda g: g.state.step is Step.END_STEP)

        assert game.state.cards_drawn_this_turn[0] == 3

    def test_an_until_your_next_turn_clock_keeps_running(self, builder):
        """Detain ends at the start of the detainer's next turn, not at an untap step."""
        game = board(builder, [SECOND_SUN, "t_bear"])
        bear = only_oid(game, "t_bear", 0)
        game.state.objects[bear].detained_by = 0
        play(game, until=lambda g: g.state.step is Step.END_STEP)

        assert game.state.objects[bear].detained_by == 0


class TestAnAddedMainPhaseIsAPostcombatMainPhase:
    def test_relentless_assault_makes_two_beginning_phases(self, builder):
        """505.1a: the main phase Relentless Assault adds is a postcombat main
        phase, so the Sphinx triggers in it -- and in the turn's own one after."""
        game = board(builder, [SECOND_SUN, "mountain", "mountain", "mountain"], hand=[ASSAULT])
        turn = game.state.turn
        play(game, cast=ASSAULT, at=Step.PRECOMBAT_MAIN)

        steps = steps_of(game, turn)
        assert steps.count("UNTAP") == 2, steps
        assert steps.count("BEGIN_COMBAT") == 2, steps
        # The extra combat, its main and that main's beginning phase, then the
        # combat the turn always had, its main, and that one's.
        mains = [i for i, s in enumerate(steps) if s == "POSTCOMBAT_MAIN"]
        assert [steps[i + 1] for i in mains] == ["UNTAP", "UNTAP"], steps
        assert steps[mains[0] + 4] == "BEGIN_COMBAT", "the turn's own combat is still owed"
        assert steps[-2:] == ["END_STEP", "CLEANUP"]

    def test_the_most_recently_created_phase_comes_first(self, builder):
        """500.8. The Sphinx's trigger resolves as the postcombat main begins and
        Relentless Assault is cast after it, so the combat and main come first and
        the beginning phase after them -- two of them, for the new main phase."""
        game = board(builder, [SECOND_SUN, "mountain", "mountain", "mountain"], hand=[ASSAULT])
        turn = game.state.turn
        play(game, cast=ASSAULT, at=Step.POSTCOMBAT_MAIN)

        steps = steps_of(game, turn)
        first = steps.index("POSTCOMBAT_MAIN")
        assert steps[first + 1] == "BEGIN_COMBAT", steps
        second = steps.index("POSTCOMBAT_MAIN", first + 1)
        assert steps[second + 1 :] == [*BEGINNING, *BEGINNING, "END_STEP", "CLEANUP"], steps


class TestAGrantMadeInsideIt:
    def test_waits_for_a_main_phase_and_none_comes(self, builder):
        """An extra combat granted in the added upkeep is "after this main phase"
        for a main phase this turn no longer has, so it never happens."""
        game = board(builder, [SECOND_SUN])
        turn = game.state.turn
        play(game, until=in_added_upkeep)
        grant_extra_phases(game.state, ["combat"])
        play(game)

        steps = steps_of(game, turn)
        assert steps.count("BEGIN_COMBAT") == 1, steps
        assert game.state.extra_phases == [] and game.state.deferred_phases == []

    def test_follows_the_next_main_phase_when_there_is_one(self, builder):
        """Relentless Assault in the precombat main: the Sphinx's first beginning
        phase comes before the turn's own combat, so a combat granted in it
        follows the turn's own postcombat main -- after the beginning phase the
        Sphinx makes there, which was created later (500.8)."""
        game = board(builder, [SECOND_SUN, "mountain", "mountain", "mountain"], hand=[ASSAULT])
        turn = game.state.turn
        play(game, cast=ASSAULT, at=Step.PRECOMBAT_MAIN, until=in_added_upkeep)
        grant_extra_phases(game.state, ["combat"])
        assert game.state.deferred_phases == ["combat"]
        play(game)

        steps = steps_of(game, turn)
        assert steps.count("BEGIN_COMBAT") == 3, steps
        last_main = len(steps) - 1 - steps[::-1].index("POSTCOMBAT_MAIN")
        assert steps[last_main + 1 : last_main + 5] == [*BEGINNING, "BEGIN_COMBAT"], steps
        assert steps[-3:] == ["END_OF_COMBAT", "END_STEP", "CLEANUP"], "a bare combat, no main"


class TestTheCapStillHolds:
    def test_grants_past_the_cap_are_dropped(self, builder):
        game = board(builder)
        queued = grant_extra_phases(game.state, ["beginning"] * 100)

        assert len(queued) == MAX_EXTRA_PHASES_PER_TURN

    def test_a_turn_full_of_beginning_phases_ends(self, builder):
        game = board(builder)
        turn = game.state.turn
        grant_extra_phases(game.state, ["beginning"] * MAX_EXTRA_PHASES_PER_TURN)
        play(game)

        assert game.state.turn == turn + 1
        assert steps_of(game, turn).count("UNTAP") == MAX_EXTRA_PHASES_PER_TURN


class TestTheNextTurnsUpkeep:
    def test_the_next_upkeep_is_the_added_one(self, builder):
        """The Eagles Are Coming: "at the beginning of the next upkeep"."""
        game = board(builder, [SECOND_SUN, "island"], hand=[NEXT_UPKEEP])
        life = game.state.players[0].life
        play(game, cast=NEXT_UPKEEP, at=Step.PRECOMBAT_MAIN, until=lambda g: g.state.step is Step.END_STEP)

        assert game.state.players[0].life == life + 3

    def test_the_next_turns_upkeep_is_not(self, builder):
        """Portent: "at the beginning of the next turn's upkeep"."""
        game = board(builder, [SECOND_SUN, "island"], hand=[NEXT_TURNS_UPKEEP])
        life = game.state.players[0].life
        play(game, cast=NEXT_TURNS_UPKEEP, at=Step.PRECOMBAT_MAIN, until=lambda g: g.state.step is Step.END_STEP)

        assert game.state.players[0].life == life
        assert len(game.state.delayed_triggers) == 1

    def test_it_comes_in_the_next_turn(self, builder):
        game = board(builder, [SECOND_SUN, "island"], hand=[NEXT_TURNS_UPKEEP])
        life = game.state.players[0].life
        play(game, cast=NEXT_TURNS_UPKEEP, at=Step.PRECOMBAT_MAIN)
        play(game, until=lambda g: g.state.step is Step.DRAW)

        assert game.state.players[0].life == life + 3
        assert game.state.delayed_triggers == []


class TestDayAndNight:
    def test_the_added_untap_step_asks_about_the_previous_turn(self, builder):
        """502.2 again, about the turn before this one -- in which a spell was
        cast, so it stays day although nothing has been cast this turn."""
        game = board(builder, [SECOND_SUN, WEREWOLF])
        game.state.day_night = "day"
        game.state.spells_cast_last_turn = (game.state.turn - 1, 1)
        game.state.turn_ledger.spells_cast.clear()
        play(game, until=lambda g: g.state.step is Step.UPKEEP)

        assert game.state.resume_step is not None
        assert game.state.day_night == "day"

    def test_a_turn_with_a_spell_in_it_keeps_it_day(self, builder):
        """The record crosses the cleanup that clears the ledger it is read from."""
        game = board(builder, [WEREWOLF])
        game.state.day_night = "day"
        game.state.turn_ledger.spells_cast[0] = 1
        play(game)
        play(game, until=lambda g: g.state.step is Step.UPKEEP)

        assert game.state.day_night == "day"

    def test_a_turn_without_one_makes_it_night(self, builder):
        game = board(builder, [WEREWOLF])
        game.state.day_night = "day"
        game.state.turn_ledger.spells_cast.clear()
        play(game)
        play(game, until=lambda g: g.state.step is Step.UPKEEP)

        assert game.state.day_night == "night"


def _compile(effects):
    return compile_card(
        CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "oracle_text": "",
                "types": ["Sorcery"],
                "mana_cost": "{1}",
                "spell_effects": effects,
            }
        )
    )


class TestTheLoaderRefuses:
    @pytest.mark.parametrize("key", ["player", "controller", "amount"])
    def test_a_key_the_op_does_not_take(self, key):
        with pytest.raises(DslError, match="extra_beginning_phase takes no"):
            _compile([{"op": "extra_beginning_phase", key: 1}])

    def test_a_next_turn_that_is_not_a_flag(self):
        with pytest.raises(DslError, match="next_turn"):
            _compile(
                [
                    {
                        "op": "delay",
                        "step": "upkeep",
                        "next_turn": "yes",
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ]
            )
