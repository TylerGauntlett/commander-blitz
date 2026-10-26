"""State triggers: "When there are four or more page counters on this artifact, …"

Rule 603.8: a state-triggered ability triggers as soon as the game state
matches its condition, and "doesn't trigger again until the ability has
resolved, has been countered, or has otherwise left the stack. Then, if the
object with the ability is still in the same zone and the game state still
matches its trigger condition, the ability will trigger again." Mazemind Tome is
the witness: its fourth page counter exiles it for 4 life.

What would be wrong without each half:

- **Triggering on the state, not an event.** `counter_placed` with a count
  condition fires again on the fifth counter while the fourth's trigger is
  still on the stack -- two exiles, and two life gains if the second resolves
  first. It also misses a count reached without a placement.
- **Not retriggering while it waits.** The check runs on every state-based-action
  pass, and the trigger spends one of those passes queued and many on the
  stack; without the wait check each pass would add another.
- **Not re-checked on resolution.** The state is the trigger, not an
  intervening "if" (603.4): removing the counters in response does not save
  the Tome.
- **Triggering again once it has left the stack**, if the state still holds.
- "Exile it. **If you do**": a Tome that left the battlefield in response is
  not exiled, and its controller gains nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import sba
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import activations, only_oid, settle

TOME = "t_st_tome"


def tome_board(builder):
    game = (
        builder(players=2)
        .battlefield(0, [TOME])
        .hand(0, ["forest"])
        .library(0, ["forest"] * 10)
        .active(0)
        .build()
    )
    return game, only_oid(game, TOME)


def turn_a_page(game, tome: int) -> None:
    game.apply(activations(game, tome, 0)[0])


def state_triggers(game, tome: int) -> int:
    """How many of the tome's state triggers are queued or on the stack."""
    waiting = (*game.state.pending_triggers, *game.state.stack)
    return sum(1 for i in waiting if i.source_oid == tome and i.ability_index == 1)


class TestTriggersOnTheState:
    def test_three_pages_is_not_enough(self, builder):
        game, tome = tome_board(builder)
        for _ in range(3):
            turn_a_page(game, tome)
        assert game.state.objects[tome].counter("page") == 3
        assert state_triggers(game, tome) == 0

    def test_the_fourth_page_triggers_it(self, builder):
        game, tome = tome_board(builder)
        for _ in range(4):
            turn_a_page(game, tome)
        assert state_triggers(game, tome) == 1

    def test_a_count_reached_without_a_placement_event(self, builder):
        game, tome = tome_board(builder)
        game.state.objects[tome].add_counter("page", 4)
        sba.check(game.state)
        assert state_triggers(game, tome) == 1

    def test_it_resolves_exile_and_life(self, builder):
        game, tome = tome_board(builder)
        life = game.state.players[0].life
        for _ in range(4):
            turn_a_page(game, tome)
        settle(game)
        assert game.state.objects[tome].zone is Zone.EXILE
        assert game.state.players[0].life == life + 4 + 10


class TestDoesNotRetriggerWhileWaiting:
    def test_more_passes_do_not_queue_more(self, builder):
        game, tome = tome_board(builder)
        game.state.objects[tome].add_counter("page", 4)
        for _ in range(3):
            sba.check(game.state)
        assert state_triggers(game, tome) == 1

    def test_a_fifth_page_in_response_does_not_trigger_again(self, builder):
        game, tome = tome_board(builder)
        life = game.state.players[0].life
        for _ in range(4):
            turn_a_page(game, tome)
        turn_a_page(game, tome)
        assert game.state.objects[tome].counter("page") == 5
        assert state_triggers(game, tome) == 1
        settle(game)
        assert game.state.players[0].life == life + 5 + 10, "one exile, one 10"


class TestLeavingTheStack:
    def test_countered_it_triggers_again_while_the_state_holds(self, builder):
        game, tome = tome_board(builder)
        for _ in range(4):
            turn_a_page(game, tome)
        (item,) = [i for i in game.state.stack if i.source_oid == tome and i.ability_index == 1]
        game.state.stack.remove(item)  # countered: it ceases to exist
        sba.check(game.state)
        assert state_triggers(game, tome) == 1

    def test_not_rechecked_on_resolution(self, builder):
        game, tome = tome_board(builder)
        life = game.state.players[0].life
        for _ in range(4):
            turn_a_page(game, tome)
        game.state.objects[tome].remove_counter("page", 4)
        settle(game)
        assert game.state.objects[tome].zone is Zone.EXILE
        assert game.state.players[0].life == life + 4 + 10


class TestIfYouDo:
    def test_gone_in_response_means_no_exile_and_no_life(self, builder):
        game, tome = tome_board(builder)
        life = game.state.players[0].life
        for _ in range(4):
            turn_a_page(game, tome)
        destroy(game.state, tome)
        settle(game)
        assert game.state.objects[tome].zone is Zone.GRAVEYARD
        assert game.state.players[0].life == life + 4


def probe(trigger: dict, **extra) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "Probe.",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "Probe.",
                    "trigger": trigger,
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                    **extra,
                }
            ],
        }
    )


FOUR = {
    "cmp": ">=",
    "left": {"counters_on": {"counter": "page", "objects": {"self_only": True}}},
    "right": {"const": 4},
}


class TestTheLoader:
    def test_the_state_compiles_onto_its_own_field(self):
        card = compile_card(probe({"event": "state", "state": FOUR}))
        spec = card.abilities[0].trigger
        assert spec.state == FOUR
        assert spec.condition is None

    def test_a_state_trigger_needs_its_state(self):
        with pytest.raises(DslError, match="needs the 'state'"):
            compile_card(probe({"event": "state"}))

    def test_state_on_another_event_is_refused(self):
        with pytest.raises(DslError, match="means nothing"):
            compile_card(probe({"event": "upkeep", "state": FOUR}))

    @pytest.mark.parametrize(
        "extra",
        [{"source": "self"}, {"condition": FOUR}, {"filter": {"types": ["Artifact"]}}],
    )
    def test_event_narrowing_keys_are_refused(self, extra):
        with pytest.raises(DslError, match="no event"):
            compile_card(probe({"event": "state", "state": FOUR, **extra}))

    def test_only_on_the_battlefield(self):
        with pytest.raises(DslError, match="battlefield only"):
            compile_card(
                probe({"event": "state", "state": FOUR}, active_zones=["graveyard"])
            )

    def test_a_delayed_state_trigger_is_refused(self):
        model = CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Probe.",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [
                    {
                        "op": "delayed_trigger",
                        "trigger": {"event": "state"},
                        "duration": "this_turn",
                        "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="cannot be delayed"):
            compile_card(model)
