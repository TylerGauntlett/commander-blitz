"""An additional combat phase, and the additional main phase after it.

"After this main phase, there is an additional combat phase followed by an
additional main phase" (Relentless Assault, Resurgence, Savage Beating);
"after this phase, there is an additional combat phase" (Combat Celebrant).
Rules 506.1 and 505.1b.

The reason this needed engine work rather than an op is `Step`: an ordered
`IntEnum` of exactly thirteen values that `turn.next_step` walks upward one
integer at a time, so a *repeated* phase had no representation at all. It does
not need one -- an extra phase is the same steps entered again -- and what has to
be remembered is only that the phase the turn was about to enter is still owed.
Hence `GameState.extra_phases` (a queue of phase kinds) and
`GameState.resume_step` (one bookmark).

Four things would each be wrong in a way that looks right in a one-line test:

- **The rest of the turn must survive the insertion.** An extra combat granted
  in a *precombat* main is inserted before the combat the turn already had, so a
  version that simply re-entered `BEGIN_COMBAT` and walked on from there would
  silently eat the ordinary combat phase and its postcombat main.
- **An extra combat is not an extra main phase.** Combat Celebrant grants one
  combat and no main; the engine's own step order puts a postcombat main after
  every combat, so the bookmark exists to say "this combat was inserted, come
  back to where the turn was" rather than falling through it.
- **"After this main phase" is not "right now".** Aggravated Assault can be
  activated during an upkeep, and its extra combat waits for the precombat main
  to end rather than jumping in front of it.
- **An unspent grant must expire.** Nothing in an end step has a main or combat
  phase left to come after, and a queue that survived the turn boundary would
  hand the next player a combat they did not pay for.

The witnesses are `t_assault` (Relentless Assault's shape: untap, then a combat
and a main) and `t_second_wind` (Combat Celebrant's: an `attacks` trigger that
grants the combat from *inside* declare-attackers, with no extra main). The
shipped card is Resurgence, the back half of Response // Resurgence.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.state import MAX_EXTRA_PHASES_PER_TURN
from commanderblitz.engine.turn import grant_extra_phases
from tests.conftest import _default_answer, find_action

ASSAULT = "t_assault"  # untap your creatures; +1 combat phase, +1 main phase
SECOND_WIND = "t_second_wind"  # 3/2; on attacking, untap the others; +1 combat


def steps_of(game, turn: int) -> list[str]:
    """Every step that ended during one turn, in order.

    Read off the event log rather than sampled, because the claim is about the
    *sequence*: a repeated phase is only visible as two `BEGIN_COMBAT`s with the
    rest of the turn still in the right places around them.
    """
    return [
        str(event.data["step"])
        for event in game.state.events
        if event.type == EventType.STEP_ENDED and event.turn == turn
    ]


def play_out(game, *, attack: bool = False, cast: str | None = None, at: Step | None = None) -> None:
    """Play the current turn to its end.

    ``cast`` is played the first moment it is legal in ``at`` -- Relentless
    Assault is a *postcombat* main-phase card, because untapping the creatures
    that already attacked is the whole point of it.
    """
    turn = game.state.turn
    for _ in range(400):
        if game.over or game.state.turn != turn:
            return
        decision = game.pending()
        if decision is None:
            return
        if cast is not None and (at is None or game.state.step is at):
            action = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == cast
                ),
                None,
            )
            if action is not None:
                game.apply(action)
                continue
        if attack and decision.kind is DecisionKind.DECLARE_ATTACKERS:
            for add in [a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER]:
                game.apply(add)
            game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        game.apply(_default_answer(game, decision))


def assault_position(builder, copies: int = 1):
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * (3 * copies) + ["t_bear"])
        .hand(0, [ASSAULT] * copies)
        .build()
    )


class TestTheSpellFromAMainPhase:
    """Relentless Assault: cast after combat, attack again."""

    def test_the_turn_gets_a_second_combat_and_a_second_main(self, builder):
        game = assault_position(builder)
        turn = game.state.turn
        play_out(game, attack=True, cast=ASSAULT, at=Step.POSTCOMBAT_MAIN)

        steps = steps_of(game, turn)
        assert steps.count("BEGIN_COMBAT") == 2, steps
        assert steps.count("POSTCOMBAT_MAIN") == 2, steps
        assert steps.count("PRECOMBAT_MAIN") == 1, "no extra precombat main"

    def test_the_extra_phases_come_after_the_main_phase_that_made_them(self, builder):
        """"After this main phase" -- so the combat is inserted, not appended."""
        game = assault_position(builder)
        turn = game.state.turn
        play_out(game, attack=True, cast=ASSAULT, at=Step.POSTCOMBAT_MAIN)

        steps = steps_of(game, turn)
        second_combat = steps.index("BEGIN_COMBAT", steps.index("BEGIN_COMBAT") + 1)
        assert steps.index("POSTCOMBAT_MAIN") < second_combat, steps
        assert steps.index("END_STEP") > second_combat, "the extra combat is before the end step"

    def test_a_creature_that_already_attacked_attacks_again(self, builder):
        """The point of the card. Untapped by its first sentence, so it can."""
        game = assault_position(builder)
        life = game.state.players[1].life
        power = game.state.registry.get("t_bear").power

        play_out(game, attack=True, cast=ASSAULT, at=Step.POSTCOMBAT_MAIN)

        assert game.state.players[1].life == life - 2 * power, "two combats, two hits"

    def test_the_additional_main_phase_fires_the_postcombat_main_trigger(self, builder):
        """"At the beginning of **each** of your postcombat main phases" (505.1b)."""
        game = assault_position(builder)
        turn = game.state.turn
        play_out(game, attack=True, cast=ASSAULT, at=Step.POSTCOMBAT_MAIN)

        fired = [
            e
            for e in game.state.events
            if e.type == EventType.POSTCOMBAT_MAIN and e.turn == turn
        ]
        assert len(fired) == 2

    def test_it_is_not_an_extra_land_drop(self, builder):
        """Another sorcery window, not another land: rule 305.2 is per *turn*."""
        game = (
            builder(players=2)
            .battlefield(0, ["mountain"] * 3 + ["t_bear"])
            .hand(0, [ASSAULT, "forest", "forest"])
            .build()
        )
        turn = game.state.turn
        played = []
        for _ in range(400):
            if game.over or game.state.turn != turn:
                break
            decision = game.pending()
            if decision is None:
                break
            land = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND), None
            )
            if land is not None:
                played.append(game.state.step.name)
                game.apply(land)
                continue
            spell = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CAST
                    and game.state.objects[a.source].def_id == ASSAULT
                ),
                None,
            )
            game.apply(spell or _default_answer(game, decision))

        assert steps_of(game, turn).count("POSTCOMBAT_MAIN") == 2, "the extra main happened"
        assert len(played) == 1, f"one land drop for the whole turn, got {played}"

    def test_the_ordinary_combat_survives_a_grant_from_the_precombat_main(self, builder):
        """Cast precombat, the extra phases go *in front of* the turn's own combat.

        Two copies, the second cast during the additional main phase the first
        one made -- which is the case the single bookmark exists for. All three
        combats happen and the turn still ends with its own postcombat main.
        """
        game = assault_position(builder, copies=2)
        turn = game.state.turn
        play_out(game, cast=ASSAULT, at=Step.PRECOMBAT_MAIN)
        play_out(game, cast=ASSAULT)

        steps = steps_of(game, turn)
        assert steps.count("BEGIN_COMBAT") == 3, steps
        assert steps.count("POSTCOMBAT_MAIN") == 3, steps
        assert steps[-2:] == ["END_STEP", "CLEANUP"], steps


class TestTheTriggerFromInsideCombat:
    """Combat Celebrant: granted in declare-attackers, and no extra main phase."""

    def test_an_extra_combat_granted_while_attacking_happens(self, builder):
        game = builder(players=2).battlefield(0, [SECOND_WIND, "t_bear"]).build()
        turn = game.state.turn
        play_out(game, attack=True)

        assert steps_of(game, turn).count("BEGIN_COMBAT") == 2

    def test_it_grants_no_additional_main_phase(self, builder):
        """The engine's step order puts a main after every combat; this must not.

        Combat Celebrant prints one extra combat and no extra main, so the turn
        gets exactly the one postcombat main it always had -- reached *after* the
        second combat, because the bookmark is where the turn resumes.
        """
        game = builder(players=2).battlefield(0, [SECOND_WIND, "t_bear"]).build()
        turn = game.state.turn
        play_out(game, attack=True)

        steps = steps_of(game, turn)
        assert steps.count("POSTCOMBAT_MAIN") == 1, steps
        assert steps.index("POSTCOMBAT_MAIN") > steps.index(
            "BEGIN_COMBAT", steps.index("BEGIN_COMBAT") + 1
        ), steps

    def test_the_untapped_others_get_to_attack_twice(self, builder):
        game = builder(players=2).battlefield(0, [SECOND_WIND, "t_bear"]).build()
        life = game.state.players[1].life
        wind = game.state.registry.get(SECOND_WIND).power
        bear = game.state.registry.get("t_bear").power

        play_out(game, attack=True)

        # Everything attacks once; only the *other* creature is untapped for the
        # second combat, which is what "all other creatures you control" says.
        assert game.state.players[1].life == life - (wind + bear) - bear


class TestWhenTheExtraPhaseIsTakenUp:
    def test_a_grant_in_the_beginning_phase_waits_for_the_main_phase(self, builder):
        """Aggravated Assault in an upkeep: "after this main phase", not before it."""
        game = builder(players=2).battlefield(0, ["t_bear"]).step(Step.UPKEEP).build(
            advance=False
        )
        turn = game.state.turn
        grant_extra_phases(game.state, ["combat"])
        game._advance()
        play_out(game)

        steps = steps_of(game, turn)
        assert steps.index("PRECOMBAT_MAIN") < steps.index("BEGIN_COMBAT"), steps
        assert steps.count("BEGIN_COMBAT") == 2, steps

    def test_an_unspent_grant_expires_at_the_turn_boundary(self, builder):
        """Granted in an end step, there is no phase left for it to follow."""
        game = builder(players=2).battlefield(0, ["t_bear"]).step(Step.END_STEP).build(
            advance=False
        )
        grant_extra_phases(game.state, ["combat", "main"])
        game._advance()
        play_out(game)

        assert game.state.extra_phases == [], "the queue does not cross the turn boundary"
        assert game.state.resume_step is None
        assert game.state.extra_phases_taken == 0

    def test_it_does_not_leak_into_the_next_players_turn(self, builder):
        game = builder(players=2).battlefield(0, ["t_bear"]).step(Step.END_STEP).build(
            advance=False
        )
        turn = game.state.turn
        grant_extra_phases(game.state, ["combat", "main"])
        game._advance()
        play_out(game)
        play_out(game)

        assert steps_of(game, turn + 1).count("BEGIN_COMBAT") == 1, "an ordinary turn"


class TestTheLoopGuard:
    """A printed infinite combo must not be an unbounded turn."""

    def test_a_turn_takes_at_most_the_cap(self, builder):
        game = builder(players=2).battlefield(0, ["t_bear"]).build()
        turn = game.state.turn
        queued = grant_extra_phases(game.state, ["combat"] * 100)

        assert len(queued) == MAX_EXTRA_PHASES_PER_TURN
        play_out(game)
        assert steps_of(game, turn).count("BEGIN_COMBAT") == MAX_EXTRA_PHASES_PER_TURN + 1

    def test_a_second_grant_cannot_get_past_it(self, builder):
        """The cap counts phases *entered*, not the queue, which drains."""
        game = builder(players=2).battlefield(0, ["t_bear"]).build()
        grant_extra_phases(game.state, ["combat"] * MAX_EXTRA_PHASES_PER_TURN)

        assert grant_extra_phases(game.state, ["combat"]) == []

    def test_an_unknown_phase_kind_is_dropped_rather_than_entered(self, builder):
        """The queue is read by name, so only the two kinds it knows get in."""
        game = builder(players=2).battlefield(0, ["t_bear"]).build()

        assert grant_extra_phases(game.state, ["extra_turn"]) == []
        assert game.state.extra_phases == []


class TestTheLoaderGuardsIt:
    """Both halves of the printed sentence, or the card is refused at load time."""

    def sorcery(self, effect: dict) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{2}{R}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }

    def test_a_misspelled_extra_main_is_refused(self):
        """Dropped silently it makes a four-mana sorcery into a lesser card."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.sorcery({"op": "extra_combat", "extra_main": "yes"})
                )
            )

    def test_a_player_is_refused(self):
        """An extra phase belongs to the turn, so there is no seat to name."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.sorcery({"op": "extra_combat", "player": "you"})
                )
            )

    def test_the_plain_form_compiles(self, registry):
        card = registry.get(ASSAULT)
        assert [e["op"] for e in card.spell_effects] == ["untap", "extra_combat"]
        assert card.spell_effects[1]["extra_main"] is True
