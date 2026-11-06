"""Paying an amount of energy that is not a printed constant.

Two printings, one cost key. 107.14 makes energy a resource a player spends and
never borrows, so whatever decides the amount, the player must have it:

- **Computed** -- Confiscation Coup: "you may pay an amount of {E} equal to
  that permanent's mana value. If you do, gain control of it." `pay_energy` in a
  `may`'s `pay` is a value expression, read with the resolving spell's targets
  and fixed to an integer before `can_pay`, the way `pay_life` already is for
  Niv-Mizzet, Ghost Counsel. Without it the only spelling is a fixed
  `pay_energy`, which steals a 6-drop for the price of a 2-drop, or a free
  `gain_control`.
- **Chosen** -- Territorial Aetherkite, Rampaging Aetherhood, Pia Nalaar,
  Chief Mechanic: "you may pay one or more {E}", and the effect reads the
  amount paid. `any_amount` beside `pay: {"pay_energy": 1}` asks `choose_x`
  from 1 up to the player's energy, charges exactly that, and binds it. A fixed
  `pay_energy: 1` would be a card that only ever spends one.

0 is never offered after the yes ("one or more"; paying none is not paying), and
a player without enough energy is not asked at all.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.carddef import Cost
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, activations, only_oid

FONT = "t_energy_font"
COUP = "t_energy_coup"


def font_with(builder, energy: int):
    """The Font, untapped, with player 0 holding ``energy``."""
    b = builder(players=2).battlefield(0, [FONT]).library(0, ["forest"] * 5).active(0)
    b.state.players[0].energy = energy
    game = b.build()
    return game, only_oid(game, FONT)


def coup_with(builder, energy: int, victim: str):
    """The Coup in hand with four Islands, facing ``victim``."""
    b = (
        builder(players=2)
        .hand(0, [COUP])
        .battlefield(0, ["island"] * 4)
        .battlefield(1, [victim])
        .library(0, ["forest"] * 5)
        .active(0)
    )
    b.state.players[0].energy = energy
    game = b.build()
    return game, only_oid(game, victim)


def run_until(game, kind: DecisionKind | None):
    """Answer passively until ``kind`` is asked (or, for None, the stack empties)."""
    for _ in range(100):
        decision = game.pending()
        if kind is not None and decision is not None and decision.kind is kind:
            return decision
        if kind is None and not game.state.stack and not game.state.pending_triggers:
            return None
        assert decision is not None, "the game stopped"
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"never reached {kind}")


def answer(game, kind: ActionKind) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is kind))


def choose(game, value: int) -> None:
    decision = game.pending()
    index = next(i for i, o in enumerate(decision.options) if o.value == value)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


def tap_font(game, font: int) -> None:
    (action,) = activations(game, font)
    game.apply(action)


def cast_coup(game, victim: int) -> None:
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == COUP
            and TargetRef.obj(victim) in a.targets
        )
    )


def energy(game) -> int:
    return game.state.players[0].energy


def life(game) -> int:
    return game.state.players[0].life


class TestTheChosenAmount:
    def test_the_ceiling_is_the_energy_the_player_has(self, builder):
        game, font = font_with(builder, 4)
        tap_font(game, font)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_X
        assert [o.value for o in decision.options] == [1, 2, 3, 4]

    def test_n_is_paid_and_n_is_read_back(self, builder):
        game, font = font_with(builder, 5)
        start = life(game)
        tap_font(game, font)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        choose(game, 3)
        run_until(game, None)

        assert energy(game) == 2
        assert life(game) == start + 3

    def test_all_of_it_can_be_paid(self, builder):
        game, font = font_with(builder, 3)
        start = life(game)
        tap_font(game, font)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        choose(game, 3)
        run_until(game, None)

        assert energy(game) == 0
        assert life(game) == start + 3

    def test_one_energy_asks_no_count(self, builder):
        game, font = font_with(builder, 1)
        start = life(game)
        tap_font(game, font)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        assert game.pending() is None or game.pending().kind is not DecisionKind.CHOOSE_X
        run_until(game, None)

        assert energy(game) == 0
        assert life(game) == start + 1

    def test_no_energy_is_not_asked(self, builder):
        game, font = font_with(builder, 0)
        start = life(game)
        tap_font(game, font)
        for _ in range(100):
            decision = game.pending()
            assert decision is None or decision.kind is not DecisionKind.MAY
            if not game.state.stack and not game.state.pending_triggers:
                break
            game.apply(_default_answer(game, decision))
        assert life(game) == start

    def test_declining_pays_nothing(self, builder):
        game, font = font_with(builder, 4)
        start = life(game)
        tap_font(game, font)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.NO)
        run_until(game, None)

        assert energy(game) == 4
        assert life(game) == start

    def test_zero_is_never_on_offer(self, builder):
        game, font = font_with(builder, 4)
        tap_font(game, font)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)

        assert 0 not in [o.value for o in game.pending().options]


class TestTheComputedAmount:
    def test_it_costs_the_targets_mana_value(self, builder):
        """Serra Angel is mana value 5: five of six energy go, and the Angel
        changes sides."""
        game, angel = coup_with(builder, 6, "serra_angel")
        cast_coup(game, angel)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        run_until(game, None)

        assert energy(game) == 1
        assert game.state.objects[angel].controller == 0

    def test_exactly_enough_is_payable(self, builder):
        game, angel = coup_with(builder, 5, "serra_angel")
        cast_coup(game, angel)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        run_until(game, None)

        assert energy(game) == 0
        assert game.state.objects[angel].controller == 0

    def test_one_short_is_not_offered(self, builder):
        """107.14: four energy cannot pay five, so there is no yes to give and
        "if you do" is false."""
        game, angel = coup_with(builder, 4, "serra_angel")
        cast_coup(game, angel)
        for _ in range(100):
            decision = game.pending()
            assert decision is None or decision.kind is not DecisionKind.MAY
            if not game.state.stack and not game.state.pending_triggers:
                break
            game.apply(_default_answer(game, decision))

        assert energy(game) == 4
        assert game.state.objects[angel].controller == 1

    def test_mana_value_zero_is_paid_with_nothing(self, builder):
        game, thopter = coup_with(builder, 0, "ornithopter")
        cast_coup(game, thopter)
        run_until(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        run_until(game, None)

        assert game.state.objects[thopter].controller == 0

    def test_the_expression_is_described_as_x(self):
        assert Cost(pay_energy={"const": 2}).describe() == "Pay X {E}"


def compile_with(effect: dict, cost: dict | None = None) -> None:
    ability = {
        "kind": "activated",
        "text": "{T}: You may pay one or more {E}.",
        "cost": cost or {"tap": True},
        "effects": [effect],
    }
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_font",
                "name": "Bad Font",
                "oracle_text": "{T}: You may pay one or more {E}.",
                "mana_cost": "{2}",
                "types": ["Artifact"],
                "abilities": [ability],
            }
        )
    )


GAIN = [{"op": "gain_life", "player": "you", "amount": {"binding": "paid"}}]
GOOD = {"as": "paid"}


class TestTheLoader:
    def test_the_chosen_shape_loads(self):
        compile_with({"op": "may", "pay": {"pay_energy": 1}, "any_amount": GOOD, "effects": GAIN})

    def test_the_computed_shape_loads(self):
        compile_with(
            {"op": "may", "pay": {"pay_energy": {"count": {"zone": "battlefield"}}},
             "effects": GAIN}
        )

    def test_a_pair_of_energy_per_count_is_refused(self):
        """{E}{E} at a time would charge pairs and bind a count that is not the
        energy paid."""
        with pytest.raises(DslError, match="pay_energy': 1"):
            compile_with(
                {"op": "may", "pay": {"pay_energy": 2}, "any_amount": GOOD, "effects": GAIN}
            )

    def test_energy_and_mana_together_are_refused(self):
        with pytest.raises(DslError, match="any_amount"):
            compile_with(
                {"op": "may", "pay": {"pay_energy": 1, "mana": "{R}"}, "any_amount": GOOD,
                 "effects": GAIN}
            )

    def test_chosen_and_computed_together_are_refused(self):
        with pytest.raises(DslError, match="chosen or computed"):
            compile_with(
                {"op": "may", "pay": {"pay_energy": {"const": 2}}, "any_amount": GOOD,
                 "effects": GAIN}
            )

    def test_a_malformed_expression_is_refused(self):
        with pytest.raises(DslError, match="pay_energy"):
            compile_with(
                {"op": "may", "pay": {"pay_energy": {"no_such_value": 1}}, "effects": GAIN}
            )

    def test_an_expression_is_refused_as_an_abilitys_own_cost(self):
        """Only a resolving `may` has the context to read one; an activated
        ability's cost is priced by legality before any effect runs."""
        with pytest.raises(Exception, match="pay_energy"):
            compile_with(
                {"op": "gain_life", "player": "you", "amount": 1},
                cost={"tap": True, "pay_energy": {"const": 2}},
            )
