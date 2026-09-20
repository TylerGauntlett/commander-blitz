"""Equip abilities as a class a card can name.

    "**Equip** abilities you activate that target enchanted creature cost {3}
    less to activate."                                    -- Strong Back
    "You may activate **equip** abilities any time you could cast an instant."
                                                          -- Leonin Shikari

An equip ability compiles to an ordinary activated ability whose effect is
`attach`, and nothing told it apart from any other. `loader/vocabulary.py` says
so out loud beside `activate_loyalty_as_though_instant`: "Leonin Shikari's … wants
this seam pointed at equip, and nothing on `Ability` marks an equip ability yet."

**Declared, not inferred.** Guessing from the shape would sweep in every
reconfigure card and Vault 101 -- all of them activated abilities that attach a
permanent, none of them printing the word. So the card says it, and the loader
holds the declaration to 702.6: an activated ability, sorcery-speed only, whose
whole effect is the attach. The word cannot be written without the mechanic, and
the mechanic cannot be renamed into it.

The 95 equip abilities already in the pool carry the marker too, applied by the
same rule the template now writes it by -- otherwise the class would name only
cards authored after today.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.errors import DslError


def equip_ability(**extra):
    base = {
        "kind": "activated",
        "text": "Equip {2}",
        "sorcery_speed_only": True,
        "is_equip": True,
        "cost": {"mana": "{2}"},
        "targets": [
            {
                "id": "equip_target",
                "kind": "permanent",
                "count": 1,
                "selector": {
                    "zone": "battlefield",
                    "controller": "you",
                    "types": ["Creature"],
                },
            }
        ],
        "effects": [{"op": "attach", "objects": {"target": "equip_target"}}],
    }
    base.update(extra)
    return base


def card(ability):
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "Equip {2}",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "subtypes": ["Equipment"],
            "abilities": [ability],
        }
    )


class TestTheMarkerSurvivesCompilation:
    def test_it_reaches_the_compiled_ability(self):
        compiled = compile_card(card(equip_ability()))
        assert compiled.abilities[0].is_equip is True

    def test_an_unmarked_ability_is_not_equip(self):
        """The default, and what every reconfigure ability keeps."""
        compiled = compile_card(card(equip_ability(is_equip=False)))
        assert compiled.abilities[0].is_equip is False


class TestTheShippedPoolCarriesIt:
    def test_a_real_equipment_is_marked(self, real_registry):
        """Applied by the same rule the template writes it by, so the class
        names the cards already in the pool and not only new ones."""
        card_def = real_registry.get("slagwurm_armor")
        assert any(a.is_equip for a in card_def.abilities)

    def test_and_its_other_ability_is_not(self, real_registry):
        card_def = real_registry.get("slagwurm_armor")
        marked = [a for a in card_def.abilities if a.is_equip]
        assert len(marked) == 1
        assert "Equip" in marked[0].text

    def test_a_reconfigure_ability_is_not_marked(self, registry):
        """The near miss the declaration exists to keep out: an activated,
        sorcery-speed ability whose whole effect is an attach, printing no such
        word."""
        card_def = registry.get("t_reconfigurer")
        assert not any(a.is_equip for a in card_def.abilities)


class TestTheLoaderHoldsItToTheShape:
    def test_a_static_may_not_claim_it(self):
        with pytest.raises(DslError, match="marks an \\*activated\\* ability"):
            compile_card(
                card(
                    {
                        "kind": "static",
                        "text": "Equipped creature gets +1/+1.",
                        "is_equip": True,
                        "effect": "buff",
                        "affects": {"attached": True},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                    }
                )
            )

    def test_an_instant_speed_ability_may_not(self):
        """702.6b. An equip that could be activated in response is a different
        card, and Leonin Shikari is the card that grants that exception."""
        with pytest.raises(DslError, match="sorcery-speed only"):
            compile_card(card(equip_ability(sorcery_speed_only=False)))

    def test_an_ability_that_does_something_else_may_not(self):
        """The half that stops the word being renamed onto a better ability:
        "Equip {2}. Draw a card." is not equip."""
        with pytest.raises(DslError, match="attaches this permanent and does"):
            compile_card(
                card(
                    equip_ability(
                        effects=[
                            {"op": "attach", "objects": {"target": "equip_target"}},
                            {"op": "draw", "amount": {"const": 1}},
                        ]
                    )
                )
            )

    def test_an_ability_that_attaches_nothing_may_not(self):
        with pytest.raises(DslError, match="attaches this permanent and does"):
            compile_card(
                card(equip_ability(effects=[{"op": "draw", "amount": {"const": 1}}]))
            )
