""""If you control a commander as you cast this spell, you may choose both."

    Akroma's Will — "Choose one. If you control a commander as you cast this
    spell, you may choose both instead."

A **ceiling** where entwine's `all_if` is a floor: `all_if` forces every mode,
`up_to_if` only permits more. The difference is the printed word "may", and it
is the whole card whenever taking one mode is the better line.

**This test exists because gate 5 cannot do its job here**, which the authoring
worker established rather than assumed. Replace `up_to_if` with `count: 2` — a
card that always takes both, the exact impostor being guarded against — and the
card still passes its behaviour gate: `ask_mode` short-circuits on
`len(labels) <= count`, takes both without asking, and mode 0's grant is a
*subset* of what both modes do, so `granted` reads the same number. The
expectation language has one `granted` slot, so the absence of mode 1 cannot be
asserted alongside the presence of mode 0 — and an absence-only assertion would
also pass for a card that does nothing.

So the guarantee is here instead: the shape of the *decision*, on boards where
the condition is false and true.

The condition itself is the second thing worth pinning. `commander_color_identity`
is not "you control a commander": it reads printed identity wherever the
commander is, so it answers 2 for one sitting in the command zone and 0 for a
colourless one on the battlefield — wrong in both directions. `exists` over the
battlefield with `is_commander` says the sentence exactly, and the command-zone
row below is what proves it.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.registry import CardRegistry
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.sandbox import GameBuilder
from automtg.engine.zones import move_object

CONTROL_A_COMMANDER = {
    "exists": {"zone": "battlefield", "controller": "you", "is_commander": True}
}


def payload(**overrides) -> dict:
    spec = {
        "op": "choose_mode",
        "count": 1,
        "up_to_if": {"condition": CONTROL_A_COMMANDER, "count": 2},
        "modes": [
            {"label": "A", "effects": [{"op": "draw", "player": "you"}]},
            {"label": "B", "effects": [{"op": "draw", "player": "you"}]},
        ],
    }
    # A `None` override *removes* the key, rather than leaving it present and
    # empty -- the loader rightly refuses `up_to_if: null`, and the impostor
    # below is a card that never had the key at all.
    for key, value in overrides.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value
    return {
        "id": "t_up_to_probe",
        "name": "Up To Probe",
        "oracle_text": "Choose one. If you control a commander, you may choose both.",
        "mana_cost": "{3}{W}",
        "types": ["Instant"],
        "spell_effects": [spec],
    }


def pool(registry: CardRegistry, card_payload: dict) -> CardRegistry:
    card = compile_card(CardModel.model_validate(card_payload))
    return CardRegistry({**{c.id: c for c in registry}, card.id: card})


def decision_on(registry: CardRegistry, card_payload: dict, commander: str | None):
    """Cast the probe and return the mode decision it raises."""
    reg = pool(registry, card_payload)
    builder = (
        GameBuilder(reg, players=2)
        .battlefield(0, ["plains"] * 5)
        .hand(0, ["t_up_to_probe"])
        .library(0, ["plains"] * 10)
    )
    if commander is not None:
        builder = builder.commander(0, ["edgar_markov"])
    game = builder.active(0).build()
    if commander == "battlefield":
        move_object(game.state, game.state.players[0].commanders[0], Zone.BATTLEFIELD)
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CAST))
    return game.pending()


class TestTheDecisionItself:
    def test_without_a_commander_exactly_one_mode(self, real_registry):
        decision = decision_on(real_registry, payload(), None)
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert (decision.min_count, decision.max_count) == (1, 1)

    def test_with_a_commander_on_the_battlefield_up_to_two(self, real_registry):
        decision = decision_on(real_registry, payload(), "battlefield")
        assert (decision.min_count, decision.max_count) == (1, 2)

    def test_a_commander_in_the_command_zone_is_not_controlled(self, real_registry):
        """The row that separates `exists` from `commander_color_identity`.

        The value leaf answers 2 here, because colour identity is a fact about
        the card wherever it is. "You control a commander" is a fact about the
        battlefield.
        """
        decision = decision_on(real_registry, payload(), "command")
        assert (decision.min_count, decision.max_count) == (1, 1)

    def test_one_is_still_the_floor_with_a_commander(self, real_registry):
        """"You **may** choose both" -- never fewer than one."""
        decision = decision_on(real_registry, payload(), "battlefield")
        assert decision.min_count == 1


class TestTheImpostorGateFiveCannotSee:
    def test_a_flat_count_of_two_never_asks(self, real_registry):
        """`count: 2` is the card that always takes both, and it asks nothing.

        `ask_mode` short-circuits when the count covers every mode. That is what
        makes the impostor invisible to the behaviour gate, and visible here.
        """
        decision = decision_on(real_registry, payload(count=2, up_to_if=None), None)
        assert decision is None or decision.kind is not DecisionKind.CHOOSE_MODE

    def test_up_to_if_still_asks_on_the_same_board(self, real_registry):
        decision = decision_on(real_registry, payload(), None)
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_MODE


class TestTheLoaderGuard:
    def test_up_to_if_elsewhere_is_refused(self):
        """It was missing, which is how the option stayed dead code."""
        with pytest.raises(DslError, match="only means anything on choose_mode"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_up_to",
                        "name": "Bad Up To",
                        "mana_cost": "{1}",
                        "types": ["Instant"],
                        "spell_effects": [
                            {
                                "op": "draw",
                                "player": "you",
                                "up_to_if": {"condition": CONTROL_A_COMMANDER},
                            }
                        ],
                    }
                )
            )

    def test_up_to_if_without_a_condition_is_refused(self):
        with pytest.raises(DslError, match="'condition'"):
            compile_card(CardModel.model_validate(payload(up_to_if={"count": 2})))
