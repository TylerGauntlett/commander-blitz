""""When this creature enters, you may pay {2}{R} any number of times. When you
pay this cost one or more times, put that many +1/+1 counters on this
creature…"                                       -- Bloodthirsty Adversary

`any_amount`'s announcement over a whole price instead of one symbol: after the
yes the player says how many times, from 1 up to what they can pay, the price
is charged that many times over (`ManaCost.scaled`, so {2}{R} at two is
{4}{R}{R}) and the count is bound for "that many". Its own key,
`any_number_of_times`, because `any_amount` refuses {R}{R} for "any amount of
{R}" -- there it would charge pairs -- and that refusal is worth keeping.

The ceiling is a count of whole prices, so it is limited by the scarcest
symbol: one Mountain beside five Forests pays {2}{R} once, not twice.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

SPELL = "t_adversary_spell"  # {0}: you may pay {2}{R} any number of times; gain that much


def position(builder, *, mountains: int, forests: int):
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * mountains + ["forest"] * forests)
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [SPELL, "forest"])
        .build()
    )


def cast_and_answer(game, *, times: int | None):
    """Cast it, say yes (or no, with ``times`` None), and pick ``times``.

    Returns the ceiling the count question offered, or None if none was asked.
    """
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SPELL
        )
    )
    ceiling = None
    for _ in range(100):
        decision = game.pending()
        if decision is None or (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return ceiling
        if decision.kind is DecisionKind.MAY and decision.player == 0:
            kind = ActionKind.NO if times is None else ActionKind.YES
            game.apply(next(a for a in game.legal_actions() if a.kind is kind))
            continue
        if decision.kind is DecisionKind.CHOOSE_X:
            ceiling = max(o.value for o in decision.options)
            index = next(i for i, o in enumerate(decision.options) if o.value == times)
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the spell never finished resolving")


def tapped(game) -> int:
    return sum(1 for obj in game.state.battlefield_objects(0) if obj.tapped)


class TestTheWholePriceIsMultiplied:
    def test_twice_is_six_mana_and_two_life(self, builder):
        game = position(builder, mountains=3, forests=3)
        before = game.state.players[0].life
        ceiling = cast_and_answer(game, times=2)

        assert ceiling == 2
        assert game.state.players[0].life == before + 2
        assert tapped(game) == 6

    def test_once_is_three_mana(self, builder):
        game = position(builder, mountains=3, forests=3)
        cast_and_answer(game, times=1)

        assert tapped(game) == 3

    def test_the_red_limits_the_count(self, builder):
        """Six lands, one of them red: {2}{R} twice needs two red."""
        game = position(builder, mountains=1, forests=5)
        before = game.state.players[0].life
        cast_and_answer(game, times=1)

        assert game.state.players[0].life == before + 1

    def test_declining_pays_nothing(self, builder):
        game = position(builder, mountains=3, forests=3)
        before = game.state.players[0].life
        cast_and_answer(game, times=None)

        assert game.state.players[0].life == before
        assert tapped(game) == 0


def compile_with(effect):
    return compile_card(
        CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "You may pay {2}{R} any number of times.",
                "types": ["Sorcery"],
                "spell_effects": [effect],
            }
        )
    )


GAIN = [{"op": "gain_life", "player": "you", "amount": {"binding": "paid"}}]


class TestTheLoaderPlacesIt:
    def test_a_whole_price_loads(self):
        compile_with(
            {"op": "may", "pay": {"mana": "{2}{R}"}, "any_number_of_times": {"as": "paid"},
             "effects": GAIN}
        )

    @pytest.mark.parametrize("mana", ["{1}", "{X}", "{R/G}", ""])
    def test_a_price_with_no_one_value_is_refused(self, mana):
        with pytest.raises(DslError, match="any_number_of_times"):
            compile_with(
                {"op": "may", "pay": {"mana": mana}, "any_number_of_times": {"as": "paid"},
                 "effects": GAIN}
            )

    def test_it_needs_a_binding(self):
        with pytest.raises(DslError, match="binding name"):
            compile_with(
                {"op": "may", "pay": {"mana": "{2}{R}"}, "any_number_of_times": {},
                 "effects": GAIN}
            )

    def test_not_beside_any_amount(self):
        with pytest.raises(DslError, match="any_number_of_times"):
            compile_with(
                {"op": "may", "pay": {"mana": "{R}"}, "any_number_of_times": {"as": "paid"},
                 "any_amount": {"as": "paid"}, "effects": GAIN}
            )

    def test_not_on_another_op(self):
        with pytest.raises(DslError, match="any_number_of_times"):
            compile_with({"op": "draw", "any_number_of_times": {"as": "paid"}})
