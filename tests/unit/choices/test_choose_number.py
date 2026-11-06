"""Choosing a number on resolution, and comparing power against it.

    Expel the Interlopers — "Choose a number between 0 and 10. Destroy all
    creatures with power greater than or equal to the chosen number."

The number is chosen as the spell **resolves**, by its controller. The near
miss is a `choose_mode` over eleven destroy modes, and it is a different card:
a top-level `choose_mode` is answered as the spell is cast (601.2b), so the
number would sit announced on the stack for every opponent to respond to, and
the sorcery would be modal (700.2) for anything that asks.

`choose_number` binds the integer under `as`; the selector's `power` reads it
with `{"value": {"binding": …}}`, which `evaluate_value` already understood.
No new `DecisionKind`: `ask_mode` over the labels "0".."10", tagged
`choose_number`. Not `ask_x` -- every seat answers `CHOOSE_X` with its maximum,
which here is the number that destroys nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError

EFFECTS = [
    {"op": "choose_number", "as": "chosen", "min": 0, "max": 10},
    {
        "op": "destroy",
        "objects": {
            "zone": "battlefield",
            "controller": "any",
            "types": ["Creature"],
            "power": {"op": ">=", "value": {"binding": "chosen"}},
            "count": "all",
        },
    },
]


def position(builder):
    """A 2/2, a 6/6 and a 1/1 for player 0; a 3/3 and a 0/4 for player 1."""
    return (
        builder(players=2)
        .battlefield(0, ["t_bear", "t_big", "t_elf"])
        .battlefield(1, ["t_menacer", "t_wall"])
        .library(0, ["island"] * 5)
        .library(1, ["island"] * 5)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def resolve(game, number: int, effects=EFFECTS) -> list:
    """Run the effects, answering ``number`` (a label); return the questions asked."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, effects)
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            labels = [o.label for o in decision.options]
            decision = gen.send([labels.index(str(number))])
    except StopIteration:
        pass
    return asked


def survivors(game) -> list[str]:
    state = game.state
    return sorted(
        state.card_of(obj).id for obj in state.objects.values() if obj.on_battlefield
    )


class TestTheChoice:
    def test_it_asks_the_controller_one_label_question(self, builder):
        game = position(builder)
        (decision,) = resolve(game, 3)
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert decision.player == 0
        assert decision.context["purpose"] == "choose_number"

    def test_the_labels_are_the_printed_range_inclusive(self, builder):
        game = position(builder)
        (decision,) = resolve(game, 3)
        assert [o.label for o in decision.options] == [str(n) for n in range(11)]

    def test_a_floor_shifts_the_ordinal(self, builder):
        game = position(builder)
        effects = [{**EFFECTS[0], "min": 2, "max": 4}, EFFECTS[1]]
        (decision,) = resolve(game, 3, effects)
        assert [o.label for o in decision.options] == ["2", "3", "4"]
        assert survivors(game) == ["t_bear", "t_elf", "t_wall"]

    def test_a_single_number_is_not_asked(self, builder):
        game = position(builder)
        effects = [{**EFFECTS[0], "min": 5, "max": 5}, EFFECTS[1]]
        ctx = EffectContext(state=game.state, controller=0)
        with pytest.raises(StopIteration):
            next(execute(ctx, effects))
        assert ctx.bindings["chosen"] == 5


class TestTheComparison:
    def test_greater_than_or_equal_to_the_number_dies(self, builder):
        game = position(builder)
        resolve(game, 3)
        assert survivors(game) == ["t_bear", "t_elf", "t_wall"]

    def test_the_boundary_is_inclusive(self, builder):
        game = position(builder)
        resolve(game, 2)
        assert survivors(game) == ["t_elf", "t_wall"]

    def test_zero_destroys_every_creature(self, builder):
        """A 0-power creature has power greater than or equal to 0."""
        game = position(builder)
        resolve(game, 0)
        assert survivors(game) == []

    def test_ten_spares_everything_smaller(self, builder):
        game = position(builder)
        resolve(game, 10)
        assert survivors(game) == ["t_bear", "t_big", "t_elf", "t_menacer", "t_wall"]


class TestTheLoader:
    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_as_is_required(self):
        card = _card()
        card["spell_effects"][0].pop("as")
        with pytest.raises(DslError, match="choose_number needs an 'as'"):
            compile_card(CardModel.model_validate(card))

    def test_max_is_required(self):
        card = _card()
        card["spell_effects"][0].pop("max")
        with pytest.raises(DslError, match="choose_number needs a 'max'"):
            compile_card(CardModel.model_validate(card))

    def test_an_inverted_range_is_refused(self):
        card = _card()
        card["spell_effects"][0].update({"min": 5, "max": 2})
        with pytest.raises(DslError, match="below 'min'"):
            compile_card(CardModel.model_validate(card))

    def test_a_bound_that_is_not_a_literal_is_refused(self):
        card = _card()
        card["spell_effects"][0]["max"] = {"const": 10}
        with pytest.raises(DslError, match="non-negative integer"):
            compile_card(CardModel.model_validate(card))


def _card() -> dict:
    return {
        "id": "t_choose_number",
        "name": "Test Choose Number",
        "oracle_text": "Choose a number between 0 and 10. Destroy all creatures with power "
        "greater than or equal to the chosen number.",
        "mana_cost": "{1}{W}{B}",
        "types": ["Sorcery"],
        "spell_effects": [dict(EFFECTS[0]), {**EFFECTS[1], "objects": dict(EFFECTS[1]["objects"])}],
    }
