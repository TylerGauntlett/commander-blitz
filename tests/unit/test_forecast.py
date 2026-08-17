"""Forecast — an ability played from hand that leaves the card there.

    "Forecast — {1}{U}, Reveal this card from your hand: … (Activate only
    during your upkeep and only once each turn.)"

Cycling and embalm are activated from outside the battlefield and both pay for
it by *leaving* — a self-discard, a self-exile. The loader turned that into a
rule, because an ability offered from hand whose cost is only mana can be
activated for ever without the card ever going anywhere.

Forecast breaks the rule and is not an infinite engine, and the reason is the
parenthetical: **once each turn, during your upkeep**. So the guard gained a
fourth satisfier, and it needs *both* halves — `once_each_turn` alone is still a
free ability every turn for the whole game, which is exactly what forecast's
upkeep window is there to price.

Two things had to be counted that were not:

- **which step it is**, as an activation restriction checked where
  `sorcery_speed_only` is, since it is permission to activate at all (602.5c);
- **activations, not resolutions.** `resolutions_this_turn` already existed and
  is the wrong number: an ability whose first activation was countered has still
  had its go, and counting resolutions would hand it back.

"Your" upkeep is the ordinary `condition: {"is_your_turn": true}` and is
deliberately not folded into the step list, because the two are separable.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from tests.conftest import pass_until

ISLAND = "island"
SPHINX = "t_forecaster"


def position(builder, lands: int = 3):
    return (
        builder(players=2)
        .battlefield(0, [ISLAND] * lands)
        .hand(0, [SPHINX])
        .library(0, [ISLAND] * 20)
        .library(1, [ISLAND] * 20)
        .build()
    )


def forecast_line(game):
    sphinx = next(
        (o for o in game.state.players[0].hand if game.state.objects[o].def_id == SPHINX),
        None,
    )
    if sphinx is None:
        return None
    return next(
        (
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == sphinx
        ),
        None,
    )


def to_my_upkeep(game, turn: int) -> None:
    pass_until(
        game,
        lambda g: (
            g.state.turn >= turn
            and g.state.step is Step.UPKEEP
            and (d := g.pending()) is not None
            and d.player == 0
        ),
    )


class TestWhenItIsOffered:
    def test_it_is_offered_in_your_upkeep(self, builder):
        game = position(builder)
        to_my_upkeep(game, 3)
        assert forecast_line(game) is not None

    def test_it_is_not_offered_in_your_main_phase(self, builder):
        """The step restriction, and the only thing stopping it being free value."""
        game = position(builder)
        pass_until(
            game,
            lambda g: g.state.step is Step.PRECOMBAT_MAIN
            and (d := g.pending()) is not None
            and d.player == 0
            and g.state.turn >= 3,
        )
        assert forecast_line(game) is None

    def test_it_is_not_offered_without_the_mana(self, builder):
        game = position(builder, lands=1)
        to_my_upkeep(game, 3)
        assert forecast_line(game) is None


class TestOnceEachTurn:
    def test_the_second_activation_is_not_offered(self, builder):
        game = position(builder, lands=6)
        to_my_upkeep(game, 3)
        game.apply(forecast_line(game))
        pass_until(game, lambda g: not g.state.stack)

        assert forecast_line(game) is None, "once each turn"

    def test_it_comes_back_next_turn(self, builder):
        """A per-turn cap, not a one-way flag: the ledger clears at cleanup."""
        game = position(builder, lands=6)
        to_my_upkeep(game, 3)
        game.apply(forecast_line(game))
        pass_until(game, lambda g: not g.state.stack)

        to_my_upkeep(game, 5)
        assert forecast_line(game) is not None

    def test_activations_are_counted_not_resolutions(self, builder):
        """Counted before the cost is paid, so the allowance is spent either way."""
        game = position(builder, lands=6)
        to_my_upkeep(game, 3)
        sphinx = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == SPHINX
        )
        action = forecast_line(game)
        game.apply(action)

        assert game.state.turn_ledger.activations(sphinx, action.ability_index) == 1


class TestTheCardStaysInHand:
    def test_it_is_still_in_hand_afterwards(self, builder):
        """Unlike cycling and embalm, the cost does not remove it."""
        game = position(builder, lands=6)
        to_my_upkeep(game, 3)
        sphinx = next(
            o for o in game.state.players[0].hand if game.state.objects[o].def_id == SPHINX
        )
        game.apply(forecast_line(game))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[sphinx].zone is Zone.HAND

    def test_the_effect_happened(self, builder):
        game = position(builder, lands=6)
        to_my_upkeep(game, 3)
        life = game.state.players[0].life
        game.apply(forecast_line(game))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.players[0].life == life + 2


class TestTheWidenedGuard:
    def _ability(self, **extra) -> dict:
        base = {
            "kind": "activated",
            "active_zones": ["hand"],
            "cost": {"mana": "{1}"},
            "effects": [{"op": "gain_life", "player": "you"}],
        }
        base.update(extra)
        return base

    def _card(self, ability: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_forecast_probe",
                "name": "Forecast Probe",
                "mana_cost": "{3}{U}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [ability],
            }
        )

    def test_both_halves_satisfy_it(self):
        compile_card(
            self._card(self._ability(activate_steps=["upkeep"], once_each_turn=True))
        )

    def test_once_each_turn_alone_does_not(self):
        """Still a free ability every turn for the whole game."""
        with pytest.raises(DslError, match="outside the battlefield"):
            compile_card(self._card(self._ability(once_each_turn=True)))

    def test_a_step_alone_does_not(self):
        with pytest.raises(DslError, match="outside the battlefield"):
            compile_card(self._card(self._ability(activate_steps=["upkeep"])))

    def test_neither_is_still_refused(self):
        with pytest.raises(DslError, match="outside the battlefield"):
            compile_card(self._card(self._ability()))

    def test_they_are_refused_on_a_static(self):
        """They restrict *activating*; ignored elsewhere they would read as working."""
        with pytest.raises(DslError, match="only mean anything on an activated ability"):
            compile_card(
                self._card(
                    {
                        "kind": "static",
                        "effect": "buff",
                        "affects": {"self_only": True},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "once_each_turn": True,
                    }
                )
            )
