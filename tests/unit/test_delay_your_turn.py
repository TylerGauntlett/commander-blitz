"""Whose end step "the next end step" means.

"Put that card into your hand at the beginning of **your** next end step."
Necropotence -- and fifteen more cards in the catalogue printing "your next"
before a step name.

`delay` recorded a step name and nothing about whose turn it was, and
`_delay_due` matched on the step alone. Every seat has an end step, so for a
delay created on your own turn the two readings agree and the omission is
invisible. The gap opens exactly where the printed word is: an ability used at
instant speed on an **opponent's** turn.

That is not a corner case for the card that motivated this. Necropotence's whole
line of play is paying life on somebody else's end step; under the step-name-only
reading the card comes back that same turn, a full turn early, and on the wrong
side of the opponent's cleanup. The card would look implemented and would be
strictly better than the one printed.

Both readings are printed, so this is a flag and not a change of behaviour:
`t_delay_any_end_step` is "at the beginning of the next end step" and stays due
at the very next one, whoever is taking it.

`turn` on the struct does not stand in. It records the turn the delay was
created on and nothing reads it for timing -- and it could not do this job
anyway, since "your next" is about *whose* turn, not how many have passed.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Step
from automtg.engine.structs import DelayedTrigger
from tests.conftest import pass_until


def board(builder):
    """A two-player game where both seats always have a legal action.

    The card in hand is never played -- `_default_answer` passes priority -- it
    only keeps priority on offer. The engine surfaces a decision only where a
    player could do something, so two empty hands make whole turns pass without
    ever stopping, and `pass_until` sails past the step under test.
    """
    return (
        builder(players=2)
        .hand(0, ["forest"])
        .hand(1, ["forest"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )


def schedule(game, *, controller: int, your_turn: bool) -> None:
    """Hang a "gain 3 life" delay on the next end step, one reading or the other."""
    game.state.delayed_triggers.append(
        DelayedTrigger(
            step="end_step",
            controller=controller,
            effects=({"op": "gain_life", "player": "you", "amount": {"const": 3}},),
            description="test delay",
            turn=game.state.turn,
            your_turn=your_turn,
        )
    )


def run_to_main_of(game, pid: int) -> None:
    """Run until ``pid`` has priority in their own precombat main phase.

    Every assertion here is taken at a main phase, never "the moment the delay
    list empties". An end step offers no priority in this position, so the first
    observable instant *after* a delay comes due is the next main phase -- and a
    test that reads `active_player` when the list goes empty reads whoever is
    active by then, which is not who was active when it fired.
    """
    pass_until(
        game,
        lambda g: g.state.active_player == pid and g.state.step is Step.PRECOMBAT_MAIN,
    )


class TestWhoseEndStep:
    def test_a_plain_delay_fires_at_the_very_next_end_step(self, builder):
        """The control, and the reading the engine already had.

        Scheduled during player 1's turn, it is due at player 1's own end step --
        "the next end step" names no seat -- so it has already paid out by the
        time player 0 next has priority.
        """
        game = board(builder)
        run_to_main_of(game, 1)
        life = game.state.players[0].life
        schedule(game, controller=0, your_turn=False)

        run_to_main_of(game, 0)
        assert game.state.players[0].life == life + 3
        assert not game.state.delayed_triggers

    def test_your_delay_skips_the_opponent_s_end_step(self, builder):
        """The card that needed this. Scheduled on the opponent's turn, it holds.

        Player 1's end step comes and goes between these two checkpoints, and the
        step-name-only reading would have paid out across it -- a full turn early.
        """
        game = board(builder)
        run_to_main_of(game, 1)
        life = game.state.players[0].life
        schedule(game, controller=0, your_turn=True)

        run_to_main_of(game, 0)
        assert game.state.players[0].life == life, (
            "an opponent's end step is not 'your next end step'"
        )
        assert game.state.delayed_triggers, "and it is still waiting, not discarded"

    def test_your_delay_pays_out_at_your_own_end_step(self, builder):
        """The other half: it does fire, one turn later, and only once."""
        game = board(builder)
        run_to_main_of(game, 1)
        life = game.state.players[0].life
        schedule(game, controller=0, your_turn=True)

        run_to_main_of(game, 0)
        run_to_main_of(game, 1)
        assert game.state.players[0].life == life + 3
        assert not game.state.delayed_triggers

    def test_on_your_own_turn_the_two_readings_agree(self, builder):
        """Which is why the omission was invisible until an instant-speed card wanted it."""
        game = board(builder)
        run_to_main_of(game, 0)
        life = game.state.players[0].life
        schedule(game, controller=0, your_turn=True)

        run_to_main_of(game, 1)
        assert game.state.players[0].life == life + 3
        assert not game.state.delayed_triggers

    def test_it_is_the_controller_s_turn_not_a_fixed_seat(self, builder):
        """The comparison is against the delay's own controller."""
        game = board(builder)
        run_to_main_of(game, 0)
        life = game.state.players[1].life
        schedule(game, controller=1, your_turn=True)

        run_to_main_of(game, 1)
        assert game.state.players[1].life == life, "player 0's end step is not player 1's"

        run_to_main_of(game, 0)
        assert game.state.players[1].life == life + 3


class TestTheOpRecordsTheFlag:
    def test_the_flag_is_off_by_default(self, builder, registry):
        game = board(builder)
        ctx = EffectContext(
            state=game.state, controller=0, source_oid=None, targets={}, bindings={}
        )
        list(execute(ctx, list(registry.get("t_delay_any_end_step").spell_effects)))
        assert game.state.delayed_triggers[-1].your_turn is False

    def test_the_flag_is_read_off_the_card(self, builder, registry):
        game = board(builder)
        ctx = EffectContext(
            state=game.state, controller=0, source_oid=None, targets={}, bindings={}
        )
        list(execute(ctx, list(registry.get("t_delay_your_end_step").spell_effects)))
        assert game.state.delayed_triggers[-1].your_turn is True


class TestTheLoaderRefusesNonsense:
    def test_a_non_boolean_your_turn_is_a_load_error(self):
        """A step name here would load clean and schedule against the wrong seat."""
        from automtg.cards.loader import compile_card

        with pytest.raises(DslError, match="your_turn"):
            compile_card(
                CardModel.model_validate({
                    "id": "t_bad_delay",
                    "name": "Test Bad Delay",
                    "oracle_text": "At the beginning of your next end step, you gain 3 life.",
                    "mana_cost": "{U}",
                    "types": ["Instant"],
                    "colors": ["U"],
                    "color_identity": ["U"],
                    "spell_effects": [
                        {
                            "op": "delay",
                            "step": "end_step",
                            "your_turn": "end_step",
                            "text": (
                                "At the beginning of your next end step, you gain 3 life."
                            ),
                            "effects": [
                                {
                                    "op": "gain_life",
                                    "player": "you",
                                    "amount": {"const": 3},
                                }
                            ],
                        }
                    ],
                })
            )
