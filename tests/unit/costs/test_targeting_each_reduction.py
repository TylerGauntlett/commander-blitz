"""A discount gated on **every** target: "if it targets two creatures you control".

    Wayta, Trainer Prodigy -- "{2}{G}, {T}: Target creature you control fights
    another target creature. This ability costs {2} less to activate if it
    targets two creatures you control."

The `targeting` gate a card's own `cost_reduction` takes is true when **any**
object target matches (Ephara's Dispersal: "if it targets an attacking
creature"). On Wayta that reading is always true, because the first target is a
creature you control by construction, so every fight would cost {G}.
`targeting_each` on an activated ability's `mana_reduction` asks it of every
object target (`cost_reduction.every_target_matches`), priced per tuple by
legality as Strong Back's equip discount already is.

`t_wy_fighter` is the ability without its {T}, on an enchantment; one Forest
pays {G}, and only an aim at two of your own creatures is that cheap.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError

FIGHTER = "t_wy_fighter"
BEAR = "t_bear"


def aims(builder, *, forests: int) -> set[tuple[str, str]]:
    """Whose creatures each offered activation points at, as (first, second)."""
    game = (
        builder(players=2)
        .battlefield(0, [FIGHTER, BEAR, BEAR, *["forest"] * forests])
        .battlefield(1, [BEAR])
        .library(0, ["forest"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    fighter = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == FIGHTER)
    out = set()
    for a in game.legal_actions():
        if a.kind is ActionKind.ACTIVATE and a.source == fighter:
            whose = tuple(
                "mine" if game.state.objects[ref.id].controller == 0 else "theirs"
                for ref in a.targets
            )
            out.add(whose)
    return out


class TestEveryTargetMustMatch:
    def test_two_of_yours_cost_only_g(self, builder):
        assert aims(builder, forests=1) == {("mine", "mine")}

    def test_at_full_price_either_aim_is_offered(self, builder):
        assert aims(builder, forests=3) == {("mine", "mine"), ("mine", "theirs")}


class TestTheLoader:
    def card(self, reduction, *, kind="activated"):
        ability = {
            "kind": "activated",
            "text": "{2}{G}: Draw a card.",
            "cost": {"mana": "{2}{G}", "mana_reduction": reduction},
            "effects": [{"op": "draw", "player": "you"}],
        }
        return CardModel.model_validate(
            {
                "id": "t_bad_each",
                "name": "Test Bad Each",
                "oracle_text": "{2}{G}: Draw a card.",
                "mana_cost": "{G}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def test_the_shape_loads(self):
        compile_card(
            self.card({"amount": 2, "targeting_each": {"types": ["Creature"]}}), source="t"
        )

    def test_a_card_level_reduction_may_not_take_it(self):
        model = CardModel.model_validate(
            {
                "id": "t_bad_each_spell",
                "name": "Test Bad Each Spell",
                "oracle_text": "Draw a card.",
                "mana_cost": "{2}{G}",
                "types": ["Sorcery"],
                "cost_reduction": {"amount": 2, "targeting_each": {"types": ["Creature"]}},
                "spell_effects": [{"op": "draw", "player": "you"}],
            }
        )
        with pytest.raises(DslError, match="targeting_each"):
            compile_card(model, source="t")

    def test_an_empty_filter_is_refused(self):
        with pytest.raises(DslError):
            compile_card(self.card({"amount": 2, "targeting_each": {}}), source="t")
