"""`power` on a `spell_cost_reduction`'s `affects_spells` -- the spell's own power.

    Goreclaw, Terror of Qal Sisma -- "Creature spells you cast with power 4 or
    greater cost {2} less to cast."

The filter reads the spell as it is cast, and a spell's power is its printed
power (601.2f prices it before it resolves) unless a characteristic-defining
ability says otherwise: 604.3 gives a `*/*` its number in every zone, so a
creature whose power counts your creatures is discounted once you control
enough of them, and its printed 0 never is.

Without the key the line would be `types: [Creature]` alone, which discounts
every creature spell -- a bear for {2} less is a different card.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.errors import DslError

GORECLAW = "t_spf_goreclaw"
FOUR = "t_spf_four"
THREE = "t_spf_three"
COUNTED = "t_spf_counted"
BEAR = "t_bear"


def reduction(builder, spell: str, board=(GORECLAW,), *, pid: int = 0, owner: int = 0) -> int:
    game = (
        builder(players=2)
        .battlefield(0, list(board) + ["forest"] * 6)
        .hand(owner, [spell])
        .active(0)
        .max_turns(1)
        .build()
    )
    return cost_reduction(game.state, pid, game.state.registry.get(spell))


class TestTheThreshold:
    def test_power_four_is_discounted(self, builder):
        assert reduction(builder, FOUR) == 2

    def test_power_three_is_not(self, builder):
        assert reduction(builder, THREE) == 0

    def test_without_goreclaw_nothing_is(self, builder):
        assert reduction(builder, FOUR, board=()) == 0


class TestACharacteristicDefiningPower:
    def test_a_star_power_reads_its_cda_in_hand(self, builder):
        """Goreclaw and three bears: four creatures, so the */* is a 4."""
        assert reduction(builder, COUNTED, board=(GORECLAW, BEAR, BEAR, BEAR)) == 2

    def test_below_the_threshold_it_is_not_discounted(self, builder):
        """Goreclaw alone: the */* is a 1, and its printed 0 is never the answer."""
        assert reduction(builder, COUNTED) == 0


class TestTheLoader:
    def _card(self, filt) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_spf_probe",
                "name": "Power Discount Probe",
                "mana_cost": "{1}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "spell_cost_reduction",
                        "affects_spells": filt,
                        "amount": {"const": 1},
                    }
                ],
            }
        )

    def test_a_comparison_loads(self):
        compile_card(self._card({"types": ["Creature"], "power": {"op": ">=", "value": 4}}))

    def test_a_malformed_comparison_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self._card({"types": ["Creature"], "power": {"op": "~", "value": 4}}))
