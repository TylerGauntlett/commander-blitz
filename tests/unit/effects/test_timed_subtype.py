"""A creature type for the turn: `add_subtype` with a `duration`.

(Bear stands in for Dragon below: `t_lord` is the test pool's "Other Bears you
control get +1/+1", so a lord can show what a static filter sees.)

"Whenever a Dragon you control enters, put a +1/+1 counter on Sarkhan. **Until
end of turn, Sarkhan becomes a Dragon in addition to its other types** and gains
flying." Sarkhan, Dragon Ascendant is the witness. Rule 611.2a: a one-shot
effect that changes characteristics creates a continuous effect, and its
duration is the one the sentence prints -- here, until the cleanup step (514.2).

Three near misses all load and all make a different card:

- **The plain op** has no clock. Sarkhan would be a Dragon for the rest of the
  game, and every later Dragon-matters card would count him.
- **`animate`** sets the *base* power and toughness. Sarkhan is a 2/2 with
  counters on him; an animation would replace the 2/2 rather than add a type.
- **A granted `add_subtype` static** is an ability (layer 6), so a later "loses
  all abilities" would strip the type, which the printed one-shot (layer 4,
  613.1d) survives.

And one thing the timed form has to keep from the untimed one: a static's
filter reads it, so a Dragon lord pumps Sarkhan for the turn he is a Dragon.
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
    add_subtypes,
    clear_until_eot,
    clear_until_next_turn,
)
from commanderblitz.engine.zones import destroy
from tests.conftest import only_oid


def a_flyer_beside_a_lord(builder):
    """Player 0 controls `t_lord` (other Bears get +1/+1) and a Bird, `t_flyer`."""
    game = builder(players=2).battlefield(0, ["t_lord", "t_flyer"]).build()
    return game, only_oid(game, "t_flyer")


def run_op(game, spec: dict, *, source: int, controller: int = 0) -> None:
    """Resolve one effect op with ``source`` as the permanent it names."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=source)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def becomes_a_bear(duration: str | None = "until_end_of_turn") -> dict:
    spec = {"op": "add_subtype", "subtypes": ["Bear"], "objects": {"self_only": True}}
    if duration is not None:
        spec["duration"] = duration
    return spec


class TestWhatItAdds:
    def test_the_subtype_is_added_for_the_turn(self, builder):
        game, bird = a_flyer_beside_a_lord(builder)
        run_op(game, becomes_a_bear(), source=bird)

        c = chars(game.state, bird)
        assert {"Bear", "Bird"} <= c.subtypes, "'in addition to its other types'"
        assert game.state.objects[bird].added_subtypes == (), "not the one-shot's field"

    def test_base_power_and_toughness_are_untouched(self, builder):
        """Unlike `animate`: the counters and the printed size both stay."""
        game, bird = a_flyer_beside_a_lord(builder)
        destroy(game.state, only_oid(game, "t_lord"))  # no Bear lord to pump it
        add_counters(game.state, bird, "+1/+1", 1)
        before = chars(game.state, bird)

        run_op(game, becomes_a_bear(), source=bird)
        after = chars(game.state, bird)
        assert (after.power, after.toughness) == (before.power, before.toughness)

    def test_a_lord_for_the_type_sees_it(self, builder):
        """A static's filter reads the timed type, as it reads the untimed one."""
        game, bird = a_flyer_beside_a_lord(builder)
        printed = chars(game.state, bird).power

        run_op(game, becomes_a_bear(), source=bird)
        assert chars(game.state, bird).power == printed + 1

    def test_it_survives_losing_all_abilities(self, builder):
        """Layer 4, not an ability -- what a granted static would get wrong."""
        game, bird = a_flyer_beside_a_lord(builder)
        run_op(game, becomes_a_bear(), source=bird)
        run_op(game, {"op": "lose_all_abilities", "objects": {"self_only": True}}, source=bird)

        assert "Bear" in chars(game.state, bird).subtypes


class TestWearingOff:
    def test_it_ends_at_cleanup(self, builder):
        game, bird = a_flyer_beside_a_lord(builder)
        printed = chars(game.state, bird).power
        run_op(game, becomes_a_bear(), source=bird)
        clear_until_eot(game.state)

        c = chars(game.state, bird)
        assert "Bear" not in c.subtypes
        assert "Bird" in c.subtypes
        assert c.power == printed, "and the lord lets go of it"

    def test_no_duration_is_the_one_shot_that_stays(self, builder):
        """The untimed op is unchanged: Captivating Vampire's line never wears off."""
        game, bird = a_flyer_beside_a_lord(builder)
        run_op(game, becomes_a_bear(None), source=bird)
        clear_until_eot(game.state)

        assert "Bear" in chars(game.state, bird).subtypes
        assert game.state.objects[bird].added_subtypes == ("Bear",)

    def test_until_your_next_turn_outlives_cleanup(self, builder):
        game, bird = a_flyer_beside_a_lord(builder)
        run_op(game, becomes_a_bear("until_your_next_turn"), source=bird)
        clear_until_eot(game.state)
        assert "Bear" in chars(game.state, bird).subtypes

        clear_until_next_turn(game.state, 0)
        assert "Bear" not in chars(game.state, bird).subtypes

    def test_a_second_grant_is_its_own_clock(self, builder):
        """Two timed grants of one type: the cleanup ends both, and an untimed
        one written beside them outlasts it."""
        game, bird = a_flyer_beside_a_lord(builder)
        add_subtypes(game.state, bird, ["Bear"], timed=True)
        add_subtypes(game.state, bird, ["Bear"], timed=True)
        add_subtypes(game.state, bird, ["Dragon"])
        clear_until_eot(game.state)

        subtypes = chars(game.state, bird).subtypes
        assert "Bear" not in subtypes
        assert "Dragon" in subtypes

    def test_leaving_the_battlefield_takes_it_back(self, builder):
        game, bird = a_flyer_beside_a_lord(builder)
        run_op(game, becomes_a_bear(), source=bird)
        destroy(game.state, bird)

        assert not game.state.objects[bird].until_eot


class TestTheLoader:
    def _card(self, effect: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_dragon_for_a_turn",
                "name": "Test Dragon For A Turn",
                "mana_cost": "{1}{R}",
                "types": ["Sorcery"],
                "oracle_text": (
                    "Until end of turn, target creature becomes a Dragon in addition "
                    "to its other types."
                ),
                "targets": [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ],
                "spell_effects": [effect],
            }
        )

    def _op(self, duration: str) -> dict:
        return {
            "op": "add_subtype",
            "subtypes": ["Dragon"],
            "objects": {"target": "t1"},
            "duration": duration,
        }

    @pytest.mark.parametrize("duration", ["until_end_of_turn", "until_your_next_turn"])
    def test_the_timed_forms_load(self, duration):
        compile_card(self._card(self._op(duration)))

    def test_a_misspelled_duration_is_refused(self):
        """Read as no clock, a Dragon for the turn would stay one for good."""
        with pytest.raises(DslError, match="unknown add_subtype duration"):
            compile_card(self._card(self._op("end_of_turn")))
