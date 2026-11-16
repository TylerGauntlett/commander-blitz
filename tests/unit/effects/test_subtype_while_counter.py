"""A subtype for as long as a counter stays: `add_subtype`'s ``while_counter``.

"Whenever Xolatoyac enters or attacks, put a flood counter on target land.
**That land is an Island in addition to its other types for as long as it has a
flood counter on it.**" Xolatoyac, the Smiling Flood is the witness. Rule
611.2b: a continuous effect from a resolved ability may last "for as long as"
a stated condition holds, and the condition here is on the land, not on
Xolatoyac -- so the Island outlives the creature that made it, and ends the
moment the last flood counter comes off, and a flood counter put back later
does not revive a duration that has already ended.

Three near misses all load and all make a different card:

- **The plain op** has no clock. The land would stay an Island after its last
  flood counter is removed.
- **An `add_subtype` static** over lands with flood counters ends when
  Xolatoyac leaves the battlefield, and it would also make a land flooded by
  any other source an Island.
- **A turn clock** (``until_end_of_turn``, ``until_your_next_turn``) ends on a
  step the printed effect never mentions.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import (
    add_counters,
    clear_until_eot,
    clear_until_next_turn,
    remove_counters,
)
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid

FLOOD = "flood"


def a_forest_and_a_source(builder):
    """Player 0 controls a Forest and `t_flyer`, the effect's stand-in source.
    Returns ``(game, forest, source)``."""
    game = builder(players=2).battlefield(0, ["forest", "t_flyer"]).build()
    return game, only_oid(game, "forest"), only_oid(game, "t_flyer")


def flood(game, land: int, source: int) -> None:
    """Resolve Xolatoyac's trigger body against ``land``: the counter, then the type."""
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        targets={"t1": (TargetRef.obj(land),)},
    )
    gen = execute(
        ctx,
        [
            {"op": "add_counters", "counter": FLOOD, "amount": 1, "objects": {"target": "t1"}},
            becomes_an_island(),
        ],
    )
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def becomes_an_island() -> dict:
    return {
        "op": "add_subtype",
        "subtypes": ["Island"],
        "objects": {"target": "t1"},
        "duration": "while_counter",
        "counter": FLOOD,
    }


def island_only(game, land: int, source: int) -> None:
    """The type sentence alone, with no counter put on first."""
    ctx = EffectContext(
        state=game.state,
        controller=0,
        source_oid=source,
        targets={"t1": (TargetRef.obj(land),)},
    )
    gen = execute(ctx, [becomes_an_island()])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def subtypes(game, oid: int) -> set[str]:
    return set(chars(game.state, oid).subtypes)


class TestWhatItAdds:
    def test_the_land_is_an_island_in_addition(self, builder):
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)

        assert {"Forest", "Island"} <= subtypes(game, forest)
        assert game.state.objects[forest].counter(FLOOD) == 1
        assert game.state.objects[forest].added_subtypes == (), "not the one-shot's field"

    def test_a_land_without_the_counter_gets_nothing(self, builder):
        """611.2b: the duration is already over before it begins."""
        game, forest, source = a_forest_and_a_source(builder)
        island_only(game, forest, source)

        assert "Island" not in subtypes(game, forest)
        assert not game.state.objects[forest].until_eot


class TestHowLongItLasts:
    def test_it_outlives_cleanup_and_the_next_turn(self, builder):
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        clear_until_eot(game.state)
        clear_until_next_turn(game.state, 0)
        clear_until_next_turn(game.state, 1)

        assert "Island" in subtypes(game, forest)

    def test_it_outlives_its_source(self, builder):
        """What the static form gets wrong: the condition is on the land."""
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        destroy(game.state, source)

        assert not game.state.objects[source].on_battlefield
        assert "Island" in subtypes(game, forest)

    def test_it_stands_while_any_flood_counter_remains(self, builder):
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        add_counters(game.state, forest, FLOOD, 1)
        remove_counters(game.state, forest, FLOOD, 1)

        assert "Island" in subtypes(game, forest)

    def test_it_ends_with_the_last_flood_counter(self, builder):
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        remove_counters(game.state, forest, FLOOD, 1)

        assert "Island" not in subtypes(game, forest)
        assert "Forest" in subtypes(game, forest)
        assert not game.state.objects[forest].until_eot

    def test_a_counter_put_back_does_not_revive_it(self, builder):
        """The duration ended; a new counter is not the same "as long as"."""
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        remove_counters(game.state, forest, FLOOD, 1)
        add_counters(game.state, forest, FLOOD, 1)

        assert "Island" not in subtypes(game, forest)

    def test_another_kind_of_counter_going_leaves_it(self, builder):
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        add_counters(game.state, forest, "charge", 1)
        remove_counters(game.state, forest, "charge", 1)

        assert "Island" in subtypes(game, forest)

    def test_a_second_flood_is_its_own_entry_and_ends_with_the_first(self, builder):
        """Two triggers, two counters: the type lasts until both are gone."""
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        flood(game, forest, source)
        remove_counters(game.state, forest, FLOOD, 1)
        assert "Island" in subtypes(game, forest)

        remove_counters(game.state, forest, FLOOD, 1)
        assert "Island" not in subtypes(game, forest)

    def test_leaving_the_battlefield_takes_it_back(self, builder):
        game, forest, source = a_forest_and_a_source(builder)
        flood(game, forest, source)
        destroy(game.state, forest)

        assert not game.state.objects[forest].until_eot


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_flood_a_land",
                "name": "Test Flood A Land",
                "mana_cost": "{U}",
                "types": ["Sorcery"],
                "oracle_text": (
                    "Put a flood counter on target land. That land is an Island in "
                    "addition to its other types for as long as it has a flood "
                    "counter on it."
                ),
                "targets": [{"id": "t1", "kind": "permanent", "selector": {"types": ["Land"]}}],
                "spell_effects": [
                    {"op": "add_counters", "counter": FLOOD, "amount": 1, "objects": {"target": "t1"}},
                    effect,
                ],
            }
        )

    def test_the_counter_bound_form_loads(self):
        compile_card(self._card(becomes_an_island()))

    def test_while_counter_needs_the_kind(self):
        effect = becomes_an_island()
        del effect["counter"]
        with pytest.raises(DslError, match="'while_counter' needs 'counter'"):
            compile_card(self._card(effect))

    def test_a_near_miss_keyword_counter_is_refused(self):
        effect = {**becomes_an_island(), "counter": "Flying"}
        with pytest.raises(DslError, match="counter"):
            compile_card(self._card(effect))

    @pytest.mark.parametrize("duration", [None, "until_end_of_turn", "until_your_next_turn"])
    def test_a_counter_on_any_other_clock_is_refused(self, duration):
        """Dropped silently, it would read as counter-bound and not be."""
        effect = {**becomes_an_island()}
        if duration is None:
            del effect["duration"]
        else:
            effect["duration"] = duration
        with pytest.raises(DslError, match="means nothing on"):
            compile_card(self._card(effect))
