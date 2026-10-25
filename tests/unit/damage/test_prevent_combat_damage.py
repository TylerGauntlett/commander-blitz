"""A damage shield that answers combat damage only.

    Seraph of the Sword — "Prevent all combat damage that would be dealt to
    this creature."

`test_prevent_all_damage.py` builds the total shield; this is the same shield
narrowed by one word. "Combat" is the whole card: without it the Seraph is
immune to burn, to a fight and to every ping, which is a much stronger card
than the printed one. The narrowing is `combat_only`, the key `replace_damage`
already reads for Inquisitor's Flail, now also read by `prevent_damage`, on
both the total shield and the numbered absorb.

**Not `replace_damage` with a zero multiplier.** A replacement to zero fires no
DAMAGE_PREVENTED and is not a prevention, so "damage can't be prevented" would
not see it. **Not protection**, which also stops blocking and targeting.

The witness is Seraph of the Sword, in Calling All Angels.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent
from tests.conftest import only_oid

SERAPH = "t_pcd_seraph"
ABSORBER = "t_pcd_absorber"


def board(builder, card_id: str):
    game = builder(players=2).battlefield(0, [card_id]).battlefield(1, ["forest"]).build(advance=False)
    return game, only_oid(game, card_id, 0)


class TestTheTotalShield:
    def test_combat_damage_is_prevented_entirely(self, builder):
        game, seraph = board(builder, SERAPH)
        assert damage_permanent(game.state, seraph, 6, None, is_combat=True) == 0
        assert game.state.objects[seraph].damage == 0

    def test_noncombat_damage_is_dealt_in_full(self, builder):
        """Burn, a fight, a ping: the word "combat" is the card."""
        game, seraph = board(builder, SERAPH)
        assert damage_permanent(game.state, seraph, 2, None) == 2
        assert game.state.objects[seraph].damage == 2


class TestTheNumberedShield:
    def test_combat_damage_is_reduced_by_the_amount(self, builder):
        game, soldier = board(builder, ABSORBER)
        assert damage_permanent(game.state, soldier, 3, None, is_combat=True) == 2

    def test_noncombat_damage_is_not_reduced(self, builder):
        game, soldier = board(builder, ABSORBER)
        assert damage_permanent(game.state, soldier, 3, None) == 3


class TestTheLoader:
    def _card(self, effect: str, **extra) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {"kind": "static", "text": "probe", "effect": effect, "combat_only": True,
                     "affects": {"self_only": True}, **extra}
                ],
            }
        )

    def test_it_loads_on_prevent_damage(self):
        compile_card(self._card("prevent_damage", prevent_all=True))

    def test_it_is_refused_on_a_static_that_cannot_read_it(self):
        with pytest.raises(DslError, match="combat_only"):
            compile_card(self._card("grant_keyword", keywords=["flying"]))
