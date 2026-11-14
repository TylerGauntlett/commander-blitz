""""During each opponent's end step, you may cast spells as though they had flash."

Final-Word Phantom. A static ability's `condition` asking which step the game
is in: the `step_is` leaf, the effect-level leaf's name and `Step` spelling,
admitted into the static condition language beside `is_your_turn`. Rule 611.3a:
a static ability's effect applies whenever its condition is true and stops the
moment it is not, with nothing on the stack. The near miss is a triggered "at
the beginning of each opponent's end step" plus `grant_flash_permission`, which
uses the stack, can be responded to, and grants nothing to a Phantom flashed in
after the trigger point -- a different card.

Two reads, and both must be live. The cast permission is asked at legality by
`player_casts_as_though_flash`, which walks the board on every call. A layered
static is read through `chars`, cached per `char_version`, so `turn.advance`
bumps it on every step change: without the bump an answer computed in the
second main phase would survive into the end step and the static would never
switch on (or, read in the end step, never switch off).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import legality, turn
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import only_oid, pt

PERMISSION = "t_end_step_flash"
BRUISER = "t_end_step_bruiser"
SORCERY = "t_sorcery"  # {R} red sorcery


def position(builder, *source: str, active: int = 1, step: Step = Step.END_STEP):
    """Player 0 controls the permission; by default it is player 1's end step."""
    lands = ["mountain", "mountain", "forest", "forest"]
    return (
        builder(players=2)
        .battlefield(0, lands + list(source))
        .battlefield(1, lands)
        .hand(0, [SORCERY])
        .hand(1, [SORCERY])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(active)
        .step(step)
        .build(advance=False)
    )


def can_cast(game, pid: int) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SORCERY
        for a in legality._priority_actions(game.state, pid)
    )


class TestThePermission:
    def test_during_an_opponents_end_step_a_sorcery_is_castable(self, builder):
        assert can_cast(position(builder, PERMISSION), 0)

    def test_without_the_source_it_is_not(self, builder):
        assert not can_cast(position(builder), 0)

    @pytest.mark.parametrize(
        "step", [Step.UPKEEP, Step.PRECOMBAT_MAIN, Step.DECLARE_ATTACKERS, Step.CLEANUP]
    )
    def test_in_any_other_step_of_their_turn_it_is_not(self, builder, step):
        assert not can_cast(position(builder, PERMISSION, step=step), 0)

    def test_in_your_own_end_step_it_is_not(self, builder):
        """The "opponent's" half: `is_your_turn` false, not merely the step."""
        assert not can_cast(position(builder, PERMISSION, active=0), 0)

    def test_it_is_scoped_to_its_controller(self, builder):
        game = position(builder, PERMISSION, active=0)
        assert not can_cast(game, 1)


class TestTheStepMoving:
    def test_the_permission_switches_on_and_off_as_the_step_advances(self, builder):
        game = position(builder, PERMISSION, step=Step.POSTCOMBAT_MAIN)
        assert not can_cast(game, 0)
        turn.advance(game.state)
        assert game.state.step is Step.END_STEP
        assert can_cast(game, 0)
        turn.advance(game.state)
        assert game.state.step is Step.CLEANUP
        assert not can_cast(game, 0)

    def test_a_layered_static_is_re_read_on_the_step_change(self, builder):
        """`chars` is cached; `turn.advance` must invalidate it."""
        game = position(builder, BRUISER, active=0, step=Step.POSTCOMBAT_MAIN)
        oid = only_oid(game, BRUISER)
        assert pt(game, oid) == (1, 1)
        turn.advance(game.state)
        assert pt(game, oid) == (3, 1)
        turn.advance(game.state)
        assert pt(game, oid) == (1, 1)


class TestTheLoader:
    def card(self, condition):
        return {
            "id": "t_probe_phantom",
            "name": "Probe Phantom",
            "mana_cost": "{3}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "static",
                    "text": "During each end step, you may cast spells as though they had flash.",
                    "effect": "cast_as_though_flash",
                    "affects_player": "you",
                    "condition": condition,
                }
            ],
        }

    @pytest.mark.parametrize("want", ["end_step", ["end_step", "cleanup"]])
    def test_a_step_or_a_list_loads(self, want):
        compiled = compile_card(CardModel.model_validate(self.card({"step_is": want})))
        assert compiled.abilities[0].static["condition"] == {"step_is": want}

    @pytest.mark.parametrize("want", ["end", "ending", ["end_step", "combat"]])
    def test_a_name_that_is_not_a_step_is_refused(self, want):
        with pytest.raises(DslError, match="step_is: must name one of"):
            compile_card(CardModel.model_validate(self.card({"step_is": want})))

    @pytest.mark.parametrize("want", [[], 3, None])
    def test_an_empty_or_non_name_is_refused(self, want):
        with pytest.raises(DslError, match="step_is"):
            compile_card(CardModel.model_validate(self.card({"step_is": want})))
