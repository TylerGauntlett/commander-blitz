"""State triggers: "When there are four or more page counters on this artifact…".

Rule 603.8: a state-triggered ability triggers when a game state is true, not
when an event happens. The game checks whenever a player would receive
priority, the ability goes on the stack like any trigger, and "it doesn't
trigger again until the ability has resolved, has been countered, or has
otherwise left the stack" -- after which a state that still holds triggers it
once more.

Mazemind Tome is the witness. Its third line watches its own page count, and
the near miss -- a `counter_placed` trigger with a `counters_on >= 4`
condition -- is wrong three ways that this file pins down: it needs an event, so
a permanent that simply *has* four counters never fires; it fires again on the
fifth counter while the first ability is still waiting; and its condition is an
intervening "if" (603.4), re-asked on resolution, so a page removed in response
would cancel an ability the printed card still resolves. `t_st_tome` is that
card with plainer activations; `t_st_fuse` clears its own counters two at a
time, which is what shows the re-trigger after resolution.

Ascend's city's blessing is checked in the same pass but is a different thing:
it is not a triggered ability and never uses the stack.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import activations, only_oid, settle

TOME = "t_st_tome"  # {1}+page: gain 1; remove a page: gain 1; 4+ pages: exile it, gain 4
FUSE = "t_st_fuse"  # {1}+fuse: draw; 2+ fuse: remove two, gain 3

PUT, REMOVE = 0, 1  # the tome's activated abilities, by index
STATE_INDEX = {TOME: 2, FUSE: 1}


def position(builder, card_id: str, *, counters: dict[str, int] | None = None, lands: int = 6):
    """``card_id`` and Forests for player 0, in a main phase.

    The opponent holds a Lightning Bolt beside a Mountain and never casts it,
    so the engine stops to ask them rather than auto-passing everything
    through to resolution -- the stack can be looked at in between.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .battlefield(0, [card_id], counters=counters)
        .battlefield(1, ["mountain"])
        .hand(1, ["lightning_bolt"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game, only_oid(game, card_id, 0)


def activate(game, oid: int, index: int) -> None:
    game.apply(activations(game, oid, index)[0])


def waiting(game, oid: int, card_id: str) -> int:
    """How many copies of the state trigger are pending or on the stack."""
    index = STATE_INDEX[card_id]
    return sum(
        1
        for item in (*game.state.stack, *game.state.pending_triggers)
        if item.source_oid == oid and item.ability_index == index
    )


def counters(game, oid: int, kind: str) -> int:
    return game.state.objects[oid].counter(kind)


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


class TestItTriggersOnTheState:
    def test_below_the_threshold_nothing_triggers(self, builder):
        game, oid = position(builder, TOME, counters={"page": 3})
        assert waiting(game, oid, TOME) == 0

    def test_a_permanent_that_already_has_four_triggers_with_no_event(self, builder):
        """Placed, not put: no counter_placed ever fired. The near miss
        listening for one would sit there for ever."""
        game, oid = position(builder, TOME, counters={"page": 4})
        assert waiting(game, oid, TOME) == 1

    def test_the_fourth_counter_paid_as_a_cost_triggers_it(self, builder):
        game, oid = position(builder, TOME, counters={"page": 3})
        activate(game, oid, PUT)
        assert waiting(game, oid, TOME) == 1

    def test_it_resolves_exile_it_and_if_you_do_gain_four(self, builder):
        game, oid = position(builder, TOME, counters={"page": 3})
        before = life(game)
        activate(game, oid, PUT)
        settle(game)
        assert game.state.objects[oid].zone is Zone.EXILE
        assert life(game) == before + 1 + 4

    def test_it_uses_the_stack(self, builder):
        """A real triggered ability, unlike Ascend: there is a moment with it on
        the stack and the Tome still on the battlefield."""
        game, oid = position(builder, TOME, counters={"page": 4})
        assert [i.source_oid for i in game.state.stack] == [oid]
        assert oid in game.state.battlefield


class TestItDoesNotRetriggerWhileWaiting:
    def test_a_fifth_counter_in_response_adds_no_second_trigger(self, builder):
        game, oid = position(builder, TOME, counters={"page": 3})
        activate(game, oid, PUT)
        assert waiting(game, oid, TOME) == 1
        activate(game, oid, PUT)
        assert counters(game, oid, "page") == 5
        assert waiting(game, oid, TOME) == 1

    def test_one_exile_and_one_life_gain(self, builder):
        game, oid = position(builder, TOME, counters={"page": 3})
        before = life(game)
        activate(game, oid, PUT)
        activate(game, oid, PUT)
        settle(game)
        # two activations (1 each) and one trigger (4), never two
        assert life(game) == before + 2 + 4

    def test_it_triggers_again_once_it_has_left_the_stack(self, builder):
        """The other half of 603.8: four fuse counters, one trigger; it removes
        two, the state still holds, and it fires a second time."""
        game, oid = position(builder, FUSE, counters={"fuse": 4})
        before = life(game)
        assert waiting(game, oid, FUSE) == 1
        settle(game)
        assert counters(game, oid, "fuse") == 0
        assert life(game) == before + 6

    def test_and_stops_once_the_state_is_false(self, builder):
        game, oid = position(builder, FUSE, counters={"fuse": 3})
        before = life(game)
        settle(game)
        assert counters(game, oid, "fuse") == 1
        assert life(game) == before + 3
        assert waiting(game, oid, FUSE) == 0


class TestTheStateIsNotReaskedOnResolution:
    def test_a_page_removed_in_response_does_not_stop_it(self, builder):
        """603.4 re-checks an intervening "if"; a state trigger has none. At
        three pages when it resolves, the Tome is exiled anyway."""
        game, oid = position(builder, TOME, counters={"page": 4})
        assert waiting(game, oid, TOME) == 1
        before = life(game)
        activate(game, oid, REMOVE)
        assert counters(game, oid, "page") == 3
        settle(game)
        assert game.state.objects[oid].zone is Zone.EXILE
        assert life(game) == before + 1 + 4

    def test_if_you_do_reads_whether_it_was_exiled(self, builder):
        """The Tome is gone before its trigger resolves: nothing is exiled, so
        no life is gained."""
        from commanderblitz.engine.zones import destroy

        game, oid = position(builder, TOME, counters={"page": 4})
        assert waiting(game, oid, TOME) == 1
        destroy(game.state, oid)
        before = life(game)
        settle(game)
        assert life(game) == before


def _probe(trigger: dict, **ability) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "Probe.",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "Probe.",
                    "trigger": trigger,
                    "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
                    **ability,
                }
            ],
        }
    )


FOUR_PAGES = {
    "cmp": ">=",
    "left": {"counters_on": {"counter": "page", "objects": {"self_only": True}}},
    "right": {"const": 4},
}


class TestLoaderRefusals:
    def test_it_compiles(self):
        card = compile_card(_probe({"event": "state", "state": FOUR_PAGES}))
        assert card.abilities[0].trigger.state == FOUR_PAGES

    def test_a_state_trigger_needs_its_state(self):
        with pytest.raises(DslError, match="needs the 'state' condition"):
            compile_card(_probe({"event": "state"}))

    def test_state_on_another_event_is_refused(self):
        with pytest.raises(DslError, match="means nothing on 'counter_placed'"):
            compile_card(_probe({"event": "counter_placed", "state": FOUR_PAGES}))

    @pytest.mark.parametrize(
        "extra",
        [
            {"condition": FOUR_PAGES},
            {"filter": {"types": ["Artifact"]}},
            {"source": "self"},
            {"max_per_turn": 1},
        ],
    )
    def test_event_keys_are_refused(self, extra):
        with pytest.raises(DslError, match="has no event"):
            compile_card(_probe({"event": "state", "state": FOUR_PAGES, **extra}))

    def test_an_unknown_condition_head_is_refused(self):
        with pytest.raises(DslError):
            compile_card(_probe({"event": "state", "state": {"no_such_head": True}}))

    def test_off_the_battlefield_is_refused(self):
        with pytest.raises(DslError, match="battlefield only"):
            compile_card(
                _probe({"event": "state", "state": FOUR_PAGES}, active_zones=["graveyard"])
            )

    def test_a_delayed_trigger_cannot_watch_it(self):
        with pytest.raises(DslError, match="delayed_trigger"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "probe",
                        "name": "Probe",
                        "oracle_text": "Probe.",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [
                            {
                                "op": "delayed_trigger",
                                "trigger": {"event": "state"},
                                "duration": "this_turn",
                                "effects": [
                                    {"op": "gain_life", "player": "you", "amount": {"const": 1}}
                                ],
                            }
                        ],
                    }
                )
            )
