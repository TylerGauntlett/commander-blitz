"""An intervening "if" lives on the trigger, and the loader now says so.

A triggered ability's "if" clause (603.4) is checked when the event happens and
again on resolution, and the engine reads it from exactly one place:
`TriggerSpec.condition`, which `triggers._matches` evaluates. An *ability-level*
``condition`` is compiled into `Ability.activation_condition` -- and only for an
activated ability. On a triggered ability it used to load, pass all six authoring
gates and be thrown away, because the gates never fire a trigger whose event the
sandbox does not reach.

Three shipped cards had their clause in the dead slot, each wrong in ordinary
play rather than at an edge:

- **The One Ring** -- "if you cast it, you gain protection from everything" -- also
  granted it when reanimated, blinked or put in with Sneak Attack.
- **Tiamat** -- "if you cast it, search ... for up to five Dragon cards" -- tutored
  five Dragons off a reanimation.
- **Emeritus of Woe** -- "if two or more creatures died this turn" -- fired every end
  step.

`TestTheLoaderRefusesIt` is the guard; `TestTheShippedCards` pins the three cards
to the slot the engine reads; `TestTheOneRingAsksHowItArrived` is the behaviour
the dead slot lost, read through the same `_matches` a real trigger goes through.
Found by the Angel of Destiny lane, whose first answer put its "if you have at
least 15 life more than your starting life total" in the dead slot and so made
the attacked player lose at 52 life.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine import triggers
from automtg.engine.effects.conditions import evaluate_condition
from automtg.engine.events import EventType, GameEvent

DIED_TWICE = {"cmp": ">=", "left": {"creatures_died_this_turn": "all"}, "right": {"const": 2}}


def _probe(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_trigger_condition_probe",
            "name": "Trigger Condition Probe",
            "mana_cost": "{2}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [ability],
        }
    )


def _end_step_draw(**extra) -> dict:
    ability = {
        "kind": "triggered",
        "text": "At the beginning of your end step, if two or more creatures died this turn, draw a card.",
        "trigger": {"event": "end_step", "controller": "you"},
        "effects": [{"op": "draw", "amount": {"const": 1}, "player": "you"}],
    }
    ability.update(extra)
    return ability


class TestTheLoaderRefusesIt:
    def test_a_condition_beside_the_trigger_is_refused(self):
        with pytest.raises(DslError, match=r"belongs in 'trigger\.condition'"):
            compile_card(_probe(_end_step_draw(condition=DIED_TWICE)))

    def test_the_same_clause_on_the_trigger_loads_and_is_kept(self):
        ability = _end_step_draw()
        ability["trigger"] = {**ability["trigger"], "condition": DIED_TWICE}
        card = compile_card(_probe(ability))
        assert card.abilities[0].trigger.condition == DIED_TWICE

    def test_an_activated_ability_still_takes_one(self):
        """The slot is right for "activate only if" -- the refusal is triggers only."""
        card = compile_card(
            _probe(
                {
                    "kind": "activated",
                    "text": "{T}: Draw a card. Activate only if two or more creatures died this turn.",
                    "cost": {"tap": True},
                    "condition": DIED_TWICE,
                    "effects": [{"op": "draw", "amount": {"const": 1}, "player": "you"}],
                }
            )
        )
        assert card.abilities[0].activation_condition == DIED_TWICE


class TestTheShippedCards:
    @pytest.mark.parametrize(
        ("card_id", "condition"),
        [
            ("the_one_ring", {"was_cast": True}),
            ("tiamat", {"was_cast": True}),
            ("emeritus_of_woe_demonic_tutor", DIED_TWICE),
        ],
    )
    def test_the_clause_is_where_the_trigger_reads_it(self, registry, card_id, condition):
        triggered = [a for a in registry.get(card_id).abilities if a.trigger is not None]
        assert triggered[0].trigger.condition == condition


class TestTheOneRingAsksHowItArrived:
    def test_a_ring_that_was_not_cast_does_not_trigger(self, registry, builder):
        """Placed rather than cast -- the reanimation side of "if you cast it"."""
        game = builder(players=2).battlefield(0, ["the_one_ring"]).build()
        oid = game.state.battlefield[0]
        spec = registry.get("the_one_ring").abilities[0].trigger
        entered = GameEvent(
            type=EventType.ENTERS_BATTLEFIELD,
            turn=game.state.turn,
            step=game.state.step,
            player=0,
            source=oid,
            data={"oid": oid},
        )
        assert not triggers._matches(game.state, game.state.objects[oid], spec, entered)

    def test_emeritus_with_no_deaths_does_not_qualify(self, registry, builder):
        game = builder(players=2).battlefield(0, ["emeritus_of_woe_demonic_tutor"]).build()
        oid = game.state.battlefield[0]
        spec = next(a.trigger for a in registry.get("emeritus_of_woe_demonic_tutor").abilities if a.trigger)
        assert evaluate_condition(game.state, spec.condition, controller=0, source=oid) is False
