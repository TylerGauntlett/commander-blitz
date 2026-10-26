"""`colorless`: a filter clause for objects with no colour (105.2c).

    Forsaken Monument -- "Colorless creatures you control get +2/+2." and
    "Whenever you cast a colorless spell, you gain 2 life."

105.2c: an object with no colour is colorless, and colorless is not a colour.
So `colors` has no letter to name it, and an empty `colors` list is no test at
all -- the anthem written that way pumps every creature you control. The effect
selector could say it as `not_colors` over all five letters, but the static and
trigger filter languages carry neither that key nor any other way to ask, so
both of Forsaken Monument's filtered lines were unsayable.

`colorless: true` matches zero colours and `false` one or more, in all four
readers of the filter languages that carry it:

* a static's filter (`characteristics._matches`), which may not read another
  static's output -- so it reads `_base_colors`: the printed colours, a copy
  exception's repaint and a face-down shell's none, never a `set_colors`
  static's result;
* a trigger filter (`triggers.matches_card_filter`), which runs outside the
  layer pipeline and so reads *derived* colours for a subject on the
  battlefield or the stack;
* the effect selector (`selectors.matches`), whose colours were derived already;
* a cost reduction's filter (`cost_reduction._object_matches`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.triggers import matches_card_filter
from tests.conftest import action_for_card, oids_of, only_oid, pt, settle

ANTHEM = "t_colorless_anthem"
WATCHER = "t_colorless_cast_watcher"
GOLEM = "t_colorless_golem"  # {2} colorless 2/2 artifact creature
TRINKET = "t_colorless_trinket"  # {1} colorless instant: draw a card
BLEACHER = "t_bleacher"  # set_colors []: every creature is colorless
BEAR = "t_bear"  # {1}{G} green 2/2
RITE = "t_plain_instant"  # {W} white instant: gain 1 life


def position(builder, mine=(), *, hand=()):
    return (
        builder(players=2)
        .battlefield(0, [*mine, *(["plains"] * 3 + ["forest"] * 3)])
        .hand(0, list(hand))
        .library(0, ["forest"] * 10)
        .active(0)
        .build()
    )


class TestTheAnthem:
    def test_a_colorless_creature_gets_it(self, builder):
        game = position(builder, [ANTHEM, GOLEM])
        assert pt(game, only_oid(game, GOLEM, 0)) == (4, 4)

    def test_a_coloured_creature_does_not(self, builder):
        game = position(builder, [ANTHEM, BEAR])
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2)

    def test_an_opponents_colorless_creature_does_not(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [ANTHEM])
            .battlefield(1, [GOLEM])
            .build()
        )
        assert pt(game, only_oid(game, GOLEM, 1)) == (2, 2)

    def test_a_copy_exception_repaint_is_seen(self, builder):
        """707.9b: "…except it's a black Zombie" changes what the object *is*,
        so the filter sees it -- `_base_colors`, not the printed face alone."""
        game = position(builder, [ANTHEM, GOLEM])
        golem = only_oid(game, GOLEM, 0)
        game.state.objects[golem].copy_overrides = {"colors": ["B"]}
        game.state.bump_chars()
        assert pt(game, golem) == (2, 2)

    def test_gone_with_its_source(self, builder):
        game = position(builder, [ANTHEM, GOLEM])
        game.state.battlefield.remove(only_oid(game, ANTHEM, 0))
        game.state.bump_chars()
        assert pt(game, only_oid(game, GOLEM, 0)) == (2, 2)


class TestTheCastTrigger:
    @staticmethod
    def cast(builder, card_id: str) -> int:
        game = position(builder, [WATCHER], hand=[card_id])
        game.apply(action_for_card(game, ActionKind.CAST, card_id))
        settle(game)
        return game.state.players[0].life

    def test_a_colorless_spell_gains_two(self, builder):
        assert self.cast(builder, TRINKET) == 42

    def test_a_colorless_creature_spell_gains_two(self, builder):
        assert self.cast(builder, GOLEM) == 42

    def test_a_coloured_spell_does_not(self, builder):
        assert self.cast(builder, RITE) == 41  # the Rite's own 1, nothing more
        assert self.cast(builder, BEAR) == 40


class TestDerivedColours:
    def test_the_trigger_filter_sees_a_set_colors_repaint(self, builder):
        """Outside the pipeline, so a `set_colors` static's output is seen: a
        green creature made colorless is a colorless permanent."""
        game = position(builder, [WATCHER, BEAR, BLEACHER])
        state = game.state
        source = state.objects[only_oid(game, WATCHER, 0)]
        bear = only_oid(game, BEAR, 0)
        assert matches_card_filter(state, bear, {"colorless": True}, source)
        assert not matches_card_filter(state, bear, {"colorless": False}, source)

    def test_without_the_repaint_it_is_green(self, builder):
        game = position(builder, [WATCHER, BEAR])
        state = game.state
        source = state.objects[only_oid(game, WATCHER, 0)]
        assert not matches_card_filter(state, only_oid(game, BEAR, 0), {"colorless": True}, source)

    def test_the_static_filter_does_not(self, builder):
        """Inside the pipeline a filter may not read another static's output
        (`characteristics` module docstring), so the anthem reads the bear's
        base colours. Recorded in docs/rules-coverage.md."""
        game = position(builder, [ANTHEM, BEAR, BLEACHER])
        assert pt(game, only_oid(game, BEAR, 0)) == (2, 2)


class TestTheSelector:
    def test_it_picks_the_colorless_permanents(self, builder):
        game = position(builder, [GOLEM, BEAR])
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        golem, bear = only_oid(game, GOLEM, 0), only_oid(game, BEAR, 0)
        assert matches(ctx, golem, {"types": ["Creature"], "colorless": True})
        assert not matches(ctx, bear, {"types": ["Creature"], "colorless": True})
        assert matches(ctx, bear, {"types": ["Creature"], "colorless": False})
        # Lands are colorless too (105.2c); the filter does not care what it is.
        assert all(
            matches(ctx, oid, {"colorless": True}) for oid in oids_of(game, "plains", 0)
        )


def _card(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_bad_monument",
            "name": "Bad Monument",
            "oracle_text": ability["text"],
            "mana_cost": "{5}",
            "types": ["Artifact"],
            "abilities": [ability],
        }
    )


def _anthem(filt: dict) -> CardModel:
    return _card(
        {
            "kind": "static",
            "text": "Colorless creatures you control get +2/+2.",
            "effect": "buff",
            "affects": filt,
            "power": {"const": 2},
            "toughness": {"const": 2},
        }
    )


def _watcher(filt: dict) -> CardModel:
    return _card(
        {
            "kind": "triggered",
            "text": "Whenever you cast a colorless spell, you gain 2 life.",
            "trigger": {"event": "spell_cast", "controller": "you", "filter": filt},
            "effects": [{"op": "gain_life", "amount": {"const": 2}, "player": "you"}],
        }
    )


class TestTheLoader:
    def test_the_shapes_load(self):
        compile_card(_anthem({"types": ["Creature"], "colorless": True}))
        compile_card(_watcher({"colorless": True}))

    @pytest.mark.parametrize("value", ["C", ["C"], 1, 0, None])
    def test_a_non_bool_is_refused_on_a_static(self, value):
        with pytest.raises(DslError, match="colorless"):
            compile_card(_anthem({"types": ["Creature"], "colorless": value}))

    @pytest.mark.parametrize("value", ["C", ["C"], 1])
    def test_a_non_bool_is_refused_on_a_trigger(self, value):
        with pytest.raises(DslError, match="colorless"):
            compile_card(_watcher({"colorless": value}))

    def test_a_non_bool_is_refused_inside_an_any_of_branch(self):
        with pytest.raises(DslError, match="colorless"):
            compile_card(
                _anthem({"any_of": [{"colorless": "yes"}, {"subtypes": ["Golem"]}]})
            )
