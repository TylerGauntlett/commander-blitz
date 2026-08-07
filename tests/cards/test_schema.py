"""Card file validation: shape, vocabulary and cross-references."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from automtg.cards.loader import compile_card, load_card_file
from automtg.cards.registry import CardRegistry
from automtg.cards.schema import CardModel
from automtg.engine.effects import known_ops
from automtg.engine.errors import DslError
from tests.conftest import CARD_DIR, TEST_CARD_DIR


def all_card_files() -> list[Path]:
    return sorted(CARD_DIR.glob("*.cards.json")) + sorted(TEST_CARD_DIR.glob("*.cards.json"))


class TestFilesLoad:
    @pytest.mark.parametrize("path", all_card_files(), ids=lambda p: p.name)
    def test_file_loads(self, path: Path):
        cards = load_card_file(path)
        assert cards, f"{path.name} defines no cards"

    def test_no_duplicate_ids_across_files(self):
        seen: dict[str, str] = {}
        for path in all_card_files():
            for card in load_card_file(path):
                assert card.id not in seen, (
                    f"{card.id} defined in both {seen[card.id]} and {path.name}"
                )
                seen[card.id] = path.name

    def test_every_card_has_a_distinct_name(self, registry: CardRegistry):
        names: dict[str, str] = {}
        for card in registry:
            if card.is_token:
                continue
            assert card.name not in names, (
                f"{card.id} and {names[card.name]} share the name {card.name!r}"
            )
            names[card.name] = card.id

    def test_token_references_resolve(self, registry: CardRegistry):
        # CardRegistry.from_paths runs validate_token_references; this asserts the
        # shipped set really does go through it.
        assert any(card.is_token for card in registry)


class TestVocabularyIsChecked:
    def _card(self, **overrides) -> dict:
        base = {
            "id": "probe",
            "name": "Probe",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
        }
        base.update(overrides)
        return base

    def test_unknown_op_is_rejected(self):
        model = CardModel.model_validate(
            self._card(types=["Sorcery"], power=None, toughness=None, spell_effects=[{"op": "teleport"}])
        )
        with pytest.raises(DslError, match="unknown effect op"):
            compile_card(model)

    def test_unknown_selector_key_is_rejected(self):
        model = CardModel.model_validate(
            self._card(
                types=["Sorcery"],
                power=None,
                toughness=None,
                spell_effects=[{"op": "destroy", "objects": {"zone": "battlefield", "shiny": True}}],
            )
        )
        with pytest.raises(DslError, match="unknown selector keys"):
            compile_card(model)

    def test_unknown_value_form_is_rejected(self):
        model = CardModel.model_validate(
            self._card(
                types=["Sorcery"],
                power=None,
                toughness=None,
                spell_effects=[{"op": "draw", "amount": {"vibes": 3}}],
            )
        )
        with pytest.raises(DslError, match="unknown value keys"):
            compile_card(model)

    def test_unknown_keyword_is_rejected(self):
        model = CardModel.model_validate(self._card(keywords=["ninjutsu"]))
        with pytest.raises(DslError, match="unknown keyword"):
            compile_card(model)

    def test_unknown_trigger_event_is_rejected(self):
        model = CardModel.model_validate(
            self._card(
                abilities=[
                    {
                        "kind": "triggered",
                        "trigger": {"event": "whenever_it_rains"},
                        "effects": [{"op": "draw"}],
                    }
                ]
            )
        )
        with pytest.raises(DslError, match="unknown trigger event"):
            compile_card(model)

    def test_target_reference_must_be_declared(self):
        model = CardModel.model_validate(
            self._card(
                types=["Instant"],
                power=None,
                toughness=None,
                spell_effects=[{"op": "destroy", "objects": {"target": "t9"}}],
            )
        )
        with pytest.raises(DslError, match="does not declare"):
            compile_card(model)

    def test_creatures_need_power_and_toughness(self):
        model = CardModel.model_validate({"id": "probe", "name": "Probe", "types": ["Creature"]})
        with pytest.raises(DslError, match="power and toughness"):
            compile_card(model)

    def test_unknown_field_is_rejected_by_the_schema(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CardModel.model_validate(self._card(manaCost="{G}"))

    def test_mana_abilities_may_only_add_mana(self):
        model = CardModel.model_validate(
            self._card(
                types=["Land"],
                power=None,
                toughness=None,
                abilities=[
                    {
                        "kind": "activated",
                        "is_mana_ability": True,
                        "cost": {"tap": True},
                        "effects": [{"op": "draw", "amount": {"const": 1}}],
                    }
                ],
            )
        )
        with pytest.raises(DslError, match="may only contain 'add_mana'"):
            compile_card(model)

    def test_static_filters_cannot_read_derived_characteristics(self):
        """The layers-lite constraint is enforced at load time, not discovered at runtime."""
        model = CardModel.model_validate(
            self._card(
                types=["Enchantment"],
                power=None,
                toughness=None,
                abilities=[
                    {
                        "kind": "static",
                        "effect": "buff",
                        "affects": {"controller": "you", "power": {"op": ">=", "value": 3}},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                    }
                ],
            )
        )
        with pytest.raises(DslError, match="printed characteristics"):
            compile_card(model)

    def test_unknown_static_effect_is_rejected(self):
        model = CardModel.model_validate(
            self._card(
                types=["Enchantment"],
                power=None,
                toughness=None,
                abilities=[
                    {"kind": "static", "effect": "win_the_game", "affects": {"controller": "you"}}
                ],
            )
        )
        with pytest.raises(DslError, match="unknown static effect"):
            compile_card(model)


class TestShippedCardsAreSane:
    def test_every_effect_op_used_is_implemented(self, registry: CardRegistry):
        ops = known_ops()
        for card in registry:
            for effect in _walk(card):
                assert effect["op"] in ops, f"{card.id} uses unimplemented op {effect['op']}"

    def test_no_card_file_contains_raw_python(self):
        """Card files are data; nothing in them should look like code."""
        for path in all_card_files():
            text = path.read_text(encoding="utf-8")
            for forbidden in ("lambda", "import ", "__", "eval("):
                assert forbidden not in text, f"{path.name} contains {forbidden!r}"

    def test_files_are_valid_json_objects(self):
        for path in all_card_files():
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, dict) and "cards" in data


def _walk(card):
    def walk(effects):
        for effect in effects:
            yield effect
            for key in ("then", "else", "effects"):
                yield from walk(effect.get(key) or [])
            for mode in effect.get("modes", []) or []:
                yield from walk(mode.get("effects") or [])

    yield from walk(card.spell_effects)
    for ability in card.abilities:
        yield from walk(ability.effects)
