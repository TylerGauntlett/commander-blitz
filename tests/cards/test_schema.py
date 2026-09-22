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
        """Distinct among the cards a name can *mean*, which is what `by_name` indexes.

        Faces are skipped for the reason tokens are: they are entries in the
        pool but not things a deck list, an import or a search can name. Two
        objects sharing a printed name is real Magic -- the spell half of
        Emeritus of Woe // Demonic Tutor is called Demonic Tutor, and so is the
        card 2,600 decks play -- so the invariant worth holding is that exactly
        one of them is reachable by that name, which is the test below.
        """
        names: dict[str, str] = {}
        for card in registry:
            if card.is_token or card.parent_face or card.front_face:
                continue
            assert card.name not in names, (
                f"{card.id} and {names[card.name]} share the name {card.name!r}"
            )
            names[card.name] = card.id

    def test_a_name_a_face_shares_resolves_to_the_whole_card(self, registry: CardRegistry):
        """The half of the invariant that actually protects a deck import.

        `importer.import_deck` turns a deck list's names into cards through
        `by_name` and nothing else, so a face winning that lookup is a card
        nobody can play: `registry._deck_problems` refuses a face outright, and
        the whole list fails rather than the one card. That is exactly what
        happened while the Emeritus spell half held the id `demonic_tutor`.
        """
        for card in registry:
            if card.is_token or not (card.parent_face or card.front_face):
                continue
            found = registry.by_name(card.name)
            assert found is None or found.id != card.id, (
                f"{card.id} is a face but answers to the name {card.name!r}"
            )

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

    def test_self_enters_is_restricted_to_the_card_itself(self):
        """`self_enters` and `permanent_enters` are the same engine event.

        What separates them is `source: "self"`, so omitting it produced a card
        that fired on *every* permanent entering -- silently, and invisible until
        a second permanent showed up. The name can only mean one thing, so the
        loader makes it mean it rather than trusting each card file to remember.
        """
        model = CardModel.model_validate(
            self._card(
                abilities=[
                    {
                        "kind": "triggered",
                        "trigger": {"event": "self_enters"},
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ]
            )
        )
        card = compile_card(model)
        assert card.abilities[0].trigger.source == "self"

    def test_permanent_enters_is_left_alone(self):
        model = CardModel.model_validate(
            self._card(
                abilities=[
                    {
                        "kind": "triggered",
                        "trigger": {"event": "permanent_enters"},
                        "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                    }
                ]
            )
        )
        card = compile_card(model)
        assert card.abilities[0].trigger.source is None

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
        """The layers-lite constraint is enforced at load time, not discovered at runtime.

        `power` used to be the exemplar here and no longer is: it is in
        `STATIC_FILTER_KEYS`, under a restriction rather than as an exception --
        what a static filter reads is `characteristics._base_pt`, the size
        before any layer, so it still cannot see another static's output. The
        restriction is measured in `tests/unit/test_static_power_filter.py`.

        `modified` takes its place, and it is a key the effect-side selector
        language has and the static one deliberately does not: the cards that
        print the word grant something once rather than continuously.
        """
        model = CardModel.model_validate(
            self._card(
                types=["Enchantment"],
                power=None,
                toughness=None,
                abilities=[
                    {
                        "kind": "static",
                        "effect": "buff",
                        "affects": {"controller": "you", "modified": True},
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
