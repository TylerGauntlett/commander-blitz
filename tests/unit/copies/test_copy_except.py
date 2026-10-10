"""A copy's exception can rewrite the copiable values rule 707.9b lists.

707.9b: "Some copy effects modify a characteristic or ability as part of the
copying process. That characteristic becomes part of the copiable values of the
copy." So "…except it's legendary", "…except it's an artifact in addition to its
other types" and "…except it's a 4/4 black Zombie" are not effects *on* the
token — they are what the token is, and every later reader has to see them.

`copy_permanent`'s `except_` already carried embalm's `colors`, `add_subtypes`
and `no_mana_cost`, and Espers to Magicite's replacing `types`. Three printed
clauses were still unsayable, one capability between them:

- **Adagia, Windswept Bastion** — "…a copy of target artifact or enchantment you
  control, except it's legendary." `add_supertypes`. Without it the token is
  not legendary and the legend rule (704.5j) never applies, which is the whole
  point of the exception. The legend rule used to read the *printed* card, so
  the key alone would have looked right in `chars` and done nothing.
- **Faerie Artisans** — "…except it's an artifact in addition to its other
  types." `add_types`, the addition beside `types`' replacement: the copy stays
  a creature *and* is seen by every artifact selector.
- **Champion of Wits** — Eternalize (702.129a): "…except it's a 4/4 black Zombie
  Snake Wizard with no mana cost." `power`/`toughness`, a base size applied
  before any layer, so counters and anthems land on top of the 4/4. Snake
  Wizard is the printed line, so `add_subtypes: ["Zombie"]` already says the
  rest; eternalize is embalm's activated shape with this bigger exception.

The counterfactual beside each claim is the same copy without the key.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.effects.values import evaluate_value
from commanderblitz.engine.errors import DslError

LEGENDARY = {"add_supertypes": ["Legendary"]}
ARTIFACT = {"add_types": ["Artifact"]}
ETERNALIZED = {
    "power": 4,
    "toughness": 4,
    "colors": ["B"],
    "add_subtypes": ["Zombie"],
    "no_mana_cost": True,
}


def board(builder, card: str):
    """``(game, oid)``: the permanent a copy will be made of."""
    game = builder(players=2).battlefield(0, [card]).build()
    return game, game.state.battlefield[0]


def copy(game, oid: int, overrides: dict | None = None, amount: int = 1) -> list[int]:
    spec: dict = {"op": "copy_permanent", "objects": {"self_only": True}, "amount": amount}
    if overrides is not None:
        spec["except_"] = overrides
    ctx = EffectContext(state=game.state, controller=0, source_oid=oid)
    list(execute(ctx, [{**spec, "as": "made"}]))
    return list(ctx.bindings["made"])


class TestExceptItsLegendary:
    def test_the_token_is_legendary(self, builder):
        game, ring = board(builder, "sol_ring")
        (token,) = copy(game, ring, LEGENDARY)
        assert "Legendary" in chars(game.state, token).supertypes

    def test_the_original_is_not(self, builder):
        """The exception is on the copy; the card it copied is untouched."""
        game, ring = board(builder, "sol_ring")
        copy(game, ring, LEGENDARY)
        assert "Legendary" not in chars(game.state, ring).supertypes

    def test_the_legend_rule_applies_to_two_such_tokens(self, builder):
        """704.5j -- the reason the printed card says it."""
        game, ring = board(builder, "sol_ring")
        tokens = copy(game, ring, LEGENDARY, amount=2)
        sba.run(game.state)
        alive = [t for t in tokens if t in game.state.battlefield]
        assert len(alive) == 1, "two legendary Sol Rings under one controller"
        assert ring in game.state.battlefield, "the non-legendary original is not in it"

    def test_without_the_clause_both_stay(self, builder):
        game, ring = board(builder, "sol_ring")
        tokens = copy(game, ring, amount=2)
        sba.run(game.state)
        assert all(t in game.state.battlefield for t in tokens)

    def test_a_legendary_selector_finds_it(self, builder):
        game, ring = board(builder, "sol_ring")
        (token,) = copy(game, ring, LEGENDARY)
        ctx = EffectContext(state=game.state, controller=0)
        found = resolve_pool(ctx, {"zone": "battlefield", "supertypes": ["Legendary"]})
        assert found == [token]


class TestExceptItsAnArtifactInAddition:
    def test_it_is_an_artifact(self, builder):
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ARTIFACT)
        assert "Artifact" in chars(game.state, token).types

    def test_it_is_still_a_creature(self, builder):
        """"In addition to its other types" -- the half `types` would drop."""
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ARTIFACT)
        assert "Creature" in chars(game.state, token).types
        assert (chars(game.state, token).power, chars(game.state, token).toughness) == (2, 2)

    def test_an_artifact_selector_sees_it(self, builder):
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ARTIFACT)
        ctx = EffectContext(state=game.state, controller=0)
        assert resolve_pool(ctx, {"zone": "battlefield", "types": ["Artifact"]}) == [token]

    def test_without_the_clause_no_artifact_selector_does(self, builder):
        game, bear = board(builder, "grizzly_bears")
        copy(game, bear)
        ctx = EffectContext(state=game.state, controller=0)
        assert resolve_pool(ctx, {"zone": "battlefield", "types": ["Artifact"]}) == []


class TestEternalize:
    def test_it_is_a_4_4(self, builder):
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ETERNALIZED)
        c = chars(game.state, token)
        assert (c.power, c.toughness) == (4, 4), "not the printed 2/2"

    def test_it_is_black(self, builder):
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ETERNALIZED)
        assert chars(game.state, token).colors == frozenset({"B"})

    def test_it_has_mana_value_0(self, builder):
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ETERNALIZED)
        ctx = EffectContext(state=game.state, controller=0)
        assert evaluate_value(ctx, {"mana_value_of": token}) == 0

    def test_it_is_a_zombie_as_well(self, builder):
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ETERNALIZED)
        assert {"Zombie", "Bear"} <= chars(game.state, token).subtypes

    def test_counters_layer_on_top_of_the_new_size(self, builder):
        """707.9b: 4/4 is the copiable value, so a +1/+1 counter makes a 5/5
        rather than being overwritten by the exception."""
        game, bear = board(builder, "grizzly_bears")
        (token,) = copy(game, bear, ETERNALIZED)
        game.state.objects[token].counters["+1/+1"] = 1
        game.state.bump_chars()
        c = chars(game.state, token)
        assert (c.power, c.toughness) == (5, 5)

    def test_the_original_keeps_its_size(self, builder):
        game, bear = board(builder, "grizzly_bears")
        copy(game, bear, ETERNALIZED)
        c = chars(game.state, bear)
        assert (c.power, c.toughness) == (2, 2)


def _card(**overrides) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_copy_except",
            "name": "Test Copy Except",
            "oracle_text": "Create a token that's a copy of target creature.",
            "mana_cost": "{2}{U}",
            "types": ["Sorcery"],
            "targets": [
                {"id": "t1", "kind": "permanent", "count": 1, "selector": {"types": ["Creature"]}}
            ],
            "spell_effects": [
                {"op": "copy_permanent", "objects": {"target": "t1"}, "except_": overrides}
            ],
        }
    )


class TestTheLoaderChecksIt:
    @pytest.mark.parametrize("overrides", [LEGENDARY, ARTIFACT, ETERNALIZED])
    def test_the_printed_shapes_load(self, overrides):
        compile_card(_card(**overrides), source="test")

    def test_an_unknown_supertype_is_refused(self):
        """"legendary" in lower case is a copy the legend rule never sees."""
        with pytest.raises(DslError, match="unknown supertype"):
            compile_card(_card(add_supertypes=["legendary"]), source="test")

    def test_an_unknown_added_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            compile_card(_card(add_types=["Artefact"]), source="test")

    def test_an_empty_addition_is_refused(self):
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(_card(add_types=[]), source="test")

    def test_replacing_and_adding_types_together_is_refused(self):
        with pytest.raises(DslError, match="'add_types'"):
            compile_card(_card(types=["Artifact"], add_types=["Enchantment"]), source="test")

    def test_half_a_size_is_refused(self):
        with pytest.raises(DslError, match="as a pair"):
            compile_card(_card(power=4), source="test")

    @pytest.mark.parametrize("bad", [-1, "4", True, {"power_of": "self"}])
    def test_a_size_must_be_a_number(self, bad):
        with pytest.raises(DslError, match="non-negative integer"):
            compile_card(_card(power=bad, toughness=4), source="test")
