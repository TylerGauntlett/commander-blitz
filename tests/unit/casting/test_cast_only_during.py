""""Cast this spell only during …": a window on whose turn and which step.

    Illusionist's Gambit -- "Cast this spell only during the declare blockers
    step on an opponent's turn. Remove all attacking creatures from combat and
    untap them. …"

    Delirium -- "Cast this spell only during an opponent's turn. …"

Without a card-level window the only spellings were `cast_during` and `step_is`,
conditions read *inside* the effect: an `if` on one lets the spell be cast in
your own main phase and resolve doing nothing, a castable card where the
printed one is not. `cast_only_during` names whose turn (`yours`, `opponents`)
and which `steps` or `phase`, and the spell cannot be cast outside them.

601.3 holds the restriction against every cast, so it is a "can't" answered in
`player_statics.player_cant_cast_spells` with the card in hand -- the question
the alternative-cost lines and the resolution-time casts (cascade, suspend,
madness, `cast_copy`) already ask -- rather than a timing window in
`casting._timing_ok`, which those casts skip.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import player_cant_cast_while_resolving

GAMBIT = "t_cod_gambit"  # an opponent's declare blockers step
DELIRIUM = "t_cod_delirium"  # an opponent's turn, any step
BEATING = "t_cod_beating"  # combat on your turn, written as a phase
FREE = "t_cod_free"  # the same instant with no window
OMNISCIENCE = "t_hand_omniscience"  # "cast spells from your hand without paying"


def at(builder, step: Step, spell: str = GAMBIT, *, active: int, extra=()):
    """Player 0 holding priority in ``step`` of player ``active``'s turn.

    Built in the active player's precombat main and then *moved*, as
    `test_cast_before_step` does: a turn with no attackers walks straight
    through combat, so a position built in a combat step is not in one by the
    time anything can be asked.

    Player 0 also holds `FREE`, which is castable everywhere. Without it a seat
    whose only card is shut out has nothing but a pass, the engine passes for
    it, and the turn rolls on to a position the test never named.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 2 + list(extra))
        .library(0, ["island"] * 10)
        .library(1, ["island"] * 10)
        .hand(0, [spell] if spell == FREE else [spell, FREE])
        .active(active)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    assert game.pending() is not None and game.pending().player == 0
    assert game.state.active_player == active and game.state.step is Step.PRECOMBAT_MAIN
    game.state.step = step
    return game


def cast_lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def castable(game, card_id: str) -> bool:
    return bool(cast_lines(game, card_id))


class TestTheGambitWindow:
    def test_an_opponents_declare_blockers_step_is_open(self, builder):
        assert castable(at(builder, Step.DECLARE_BLOCKERS, active=1), GAMBIT)

    def test_the_same_step_on_your_own_turn_is_shut(self, builder):
        game = at(builder, Step.DECLARE_BLOCKERS, active=0)
        assert not castable(game, GAMBIT)

    @pytest.mark.parametrize(
        "step",
        [Step.UPKEEP, Step.BEGIN_COMBAT, Step.DECLARE_ATTACKERS, Step.COMBAT_DAMAGE, Step.END_STEP],
        ids=lambda s: s.name.lower(),
    )
    def test_another_step_of_the_opponents_turn_is_shut(self, builder, step):
        assert not castable(at(builder, step, active=1), GAMBIT)

    @pytest.mark.parametrize("active", [0, 1])
    def test_an_unrestricted_instant_is_the_control(self, builder, active):
        """So "cannot be cast" is never "this position offers no casts"."""
        game = at(builder, Step.DECLARE_ATTACKERS, active=active)
        assert castable(game, FREE) and not castable(game, GAMBIT)


class TestAnOpponentsTurn:
    """Delirium: a turn and no step, so every step of it."""

    @pytest.mark.parametrize(
        "step", [Step.UPKEEP, Step.PRECOMBAT_MAIN, Step.END_STEP], ids=lambda s: s.name.lower()
    )
    def test_any_step_of_an_opponents_turn_is_open(self, builder, step):
        assert castable(at(builder, step, DELIRIUM, active=1), DELIRIUM)

    def test_your_own_turn_is_shut(self, builder):
        assert not castable(at(builder, Step.PRECOMBAT_MAIN, DELIRIUM, active=0), DELIRIUM)


class TestAPhaseOnYourTurn:
    """Savage Beating: "during combat on your turn", the phase compiled to its steps."""

    @pytest.mark.parametrize(
        "step",
        [Step.BEGIN_COMBAT, Step.DECLARE_BLOCKERS, Step.END_OF_COMBAT],
        ids=lambda s: s.name.lower(),
    )
    def test_every_step_of_combat_on_your_turn_is_open(self, builder, step):
        assert castable(at(builder, step, BEATING, active=0), BEATING)

    @pytest.mark.parametrize(
        "step", [Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN], ids=lambda s: s.name.lower()
    )
    def test_outside_combat_is_shut(self, builder, step):
        assert not castable(at(builder, step, BEATING, active=0), BEATING)

    def test_combat_on_an_opponents_turn_is_shut(self, builder):
        assert not castable(at(builder, Step.DECLARE_BLOCKERS, BEATING, active=1), BEATING)


class TestEveryRouteToACast:
    """601.3: the window holds for every cast, not only the paid line from hand."""

    def test_a_free_alternative_line_is_withheld_outside_the_window(self, builder):
        game = at(builder, Step.PRECOMBAT_MAIN, DELIRIUM, active=0, extra=[OMNISCIENCE])
        assert not castable(game, DELIRIUM)

    def test_and_offered_inside_it(self, builder):
        game = at(builder, Step.PRECOMBAT_MAIN, DELIRIUM, active=1, extra=[OMNISCIENCE])
        assert any(a.cast_free for a in cast_lines(game, DELIRIUM))

    def test_a_resolution_time_cast_asks_the_same_question(self, builder):
        """Cascade, suspend, madness and `cast_copy` ask
        `player_cant_cast_while_resolving` with the card, and it refuses."""
        game = at(builder, Step.PRECOMBAT_MAIN, DELIRIUM, active=0)
        card = game.state.card_of(game.state.objects[game.state.players[0].hand[0]])
        assert player_cant_cast_while_resolving(game.state, 0, card)
        game.state.active_idx = 1
        assert not player_cant_cast_while_resolving(game.state, 0, card)


def _model(window, types=("Instant",)):
    return CardModel.model_validate(
        {
            "id": "t_probe",
            "name": "Probe",
            "oracle_text": "Cast this spell only during combat.\nDraw a card.",
            "mana_cost": "{U}",
            "types": list(types),
            "cast_only_during": window,
            "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
        }
    )


class TestTheLoader:
    def test_a_phase_compiles_to_its_steps(self):
        window = compile_card(_model({"phase": "combat"})).cast_only_during
        assert window.turn is None
        assert window.steps == frozenset(
            {
                Step.BEGIN_COMBAT,
                Step.DECLARE_ATTACKERS,
                Step.DECLARE_BLOCKERS,
                Step.FIRST_STRIKE_DAMAGE,
                Step.COMBAT_DAMAGE,
                Step.END_OF_COMBAT,
            }
        )

    def test_a_turn_alone_leaves_every_step_open(self):
        window = compile_card(_model({"turn": "opponents"})).cast_only_during
        assert window.turn == "opponents" and window.steps is None

    @pytest.mark.parametrize(
        ("window", "match"),
        [
            ({"steps": ["declare_blockers_step"]}, "unknown step"),
            ({"phase": "main"}, "unknown phase"),
            ({"steps": ["upkeep"], "phase": "combat"}, "not both"),
            ({"steps": []}, "names no step"),
            ({}, "restricts nothing"),
        ],
        ids=["typo_step", "unknown_phase", "steps_and_phase", "empty_steps", "empty_window"],
    )
    def test_a_window_that_would_load_wrong_is_refused(self, window, match):
        with pytest.raises(DslError, match=match):
            compile_card(_model(window))

    def test_a_land_is_refused(self):
        with pytest.raises(DslError, match="land is played"):
            compile_card(_model({"turn": "yours"}, types=("Land",)))

    @pytest.mark.parametrize(
        "window",
        [{"turn": "an_opponents"}, {"turn": "opponents", "step": "upkeep"}],
        ids=["unknown_turn", "unknown_key"],
    )
    def test_the_schema_refuses_what_it_does_not_know(self, window):
        with pytest.raises(ValidationError):
            _model(window)
