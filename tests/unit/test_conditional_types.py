"""Statics with an "as long as..." clause, and the one card that needs them.

Arixmethes is a 12/12 Kraken that is *not a creature* while it has a slumber
counter. Two things follow, and both are worth pinning: it cannot attack or be
killed as a creature while asleep, and it can tap for mana the turn it lands,
because summoning sickness is a rule about creatures.

The condition language available to a static is deliberately one question --
"how many counters of this kind are on me" -- since anything that read a derived
characteristic would let one static depend on another's output.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.costs import mana_sources
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import only_oid


def wake_it(game, oid: int) -> None:
    game.state.objects[oid].counters.pop("slumber", None)
    game.state.bump_chars()


class TestArixmethes:
    def board(self, builder, counters: int = 5):
        game = (
            builder(players=2)
            .battlefield(0, ["forest"] * 2 + ["arixmethes_slumbering_isle"])
            .build()
        )
        oid = only_oid(game, "arixmethes_slumbering_isle")
        if counters:
            game.state.objects[oid].counters["slumber"] = counters
        game.state.bump_chars()
        return game, oid

    def test_asleep_it_is_a_land_and_not_a_creature(self, builder):
        game, oid = self.board(builder)
        got = chars(game.state, oid)
        assert "Land" in got.types
        assert "Creature" not in got.types, "the parenthetical is the whole point"

    def test_awake_it_is_the_creature_it_was_printed_as(self, builder):
        game, oid = self.board(builder)
        wake_it(game, oid)
        got = chars(game.state, oid)
        assert "Creature" in got.types
        assert "Land" not in got.types
        assert (got.power, got.toughness) == (12, 12)

    def test_it_taps_for_mana_while_it_sleeps(self, builder):
        """Summoning sickness is a rule about creatures, and it is not one."""
        game, oid = self.board(builder)
        game.state.objects[oid].entered_turn = game.state.turn  # just arrived
        game.state.bump_chars()
        assert any(s.oid == oid for s in mana_sources(game.state, 0))

    def test_it_cannot_attack_while_it_sleeps(self, builder):
        from automtg.engine.enums import Step
        from tests.conftest import advance_to_step

        game, oid = self.board(builder)
        advance_to_step(game, Step.DECLARE_ATTACKERS)
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
        ]


class TestTheConditionLanguageIsSmall:
    base = {
        "id": "probe",
        "name": "Probe",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
    }

    def _with(self, condition):
        return CardModel.model_validate(
            {
                **self.base,
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "set_types",
                        "affects": {"self_only": True},
                        "types": ["Land"],
                        "condition": condition,
                    }
                ],
            }
        )

    def test_the_if_op_s_condition_keys_are_not_borrowable(self):
        """The static language is a *mirror* of the effect one, not that one.

        `zone_is` and `kicked` are real `if` conditions and read a resolving
        object's state, which a static -- evaluated for every permanent on every
        cache miss -- has no business asking.  See `test_static_condition.py`
        for the forms a static *may* use.
        """
        with pytest.raises(DslError, match="exactly one of"):
            compile_card(self._with({"zone_is": "battlefield"}))
        with pytest.raises(DslError, match="exactly one of"):
            compile_card(self._with({"kicked": True}))

    def test_a_condition_names_one_form(self):
        with pytest.raises(DslError, match="exactly one of"):
            compile_card(self._with({"counters": {"counter": "slumber"}, "is_your_turn": True}))

    def test_unknown_comparison_is_rejected(self):
        with pytest.raises(DslError, match="unknown comparison"):
            compile_card(self._with({"counters": {"counter": "slumber", "op": "roughly"}}))

    def test_set_types_needs_types(self):
        model = CardModel.model_validate(
            {
                **self.base,
                "abilities": [
                    {"kind": "static", "effect": "set_types", "affects": {"self_only": True}}
                ],
            }
        )
        with pytest.raises(DslError, match="needs the types"):
            compile_card(model)
