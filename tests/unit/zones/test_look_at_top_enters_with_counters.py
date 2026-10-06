"""`look_at_top` putting a card onto the battlefield **with** counters (614.1c).

Turntimber Symbiosis is the witness: "Look at the top seven cards of your
library. You may put a creature card from among them onto the battlefield. **If
that card has mana value 3 or less, it enters with three additional +1/+1
counters on it.** Put the rest on the bottom of your library in a random order."

"Enters with" is a replacement on the arrival (614.1c): the creature is never on
the battlefield without the counters, and they are put on in the **same**
placement as any it prints itself (122.6). The near miss is the shape the DSL
already had -- `look_at_top` with an `as` binding, then `add_counters` on it --
and it is a different card in two ways a player can see:

- a creature that *prints* an "enters with" gets two placements rather than
  one, so Hardened Scales adds two counters instead of one, and "whenever you
  put one or more +1/+1 counters on this creature" triggers twice;
- the creature arrives at its printed size first, which for a 0/0 is the size
  `zones._enter_battlefield`'s enters-with path exists so it is never seen at.

So ``counters`` rides `move_object`'s ``enters_with`` into that one placement,
and ``counters_if`` asks its question of the **printed** card while it is still
in the library -- "if that card has mana value 3 or less" is about the card
being put there, and there is nothing else for it to be about.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.events import EventType
from tests.conftest import pass_until

BEAR = "t_bear"  # {1}{G} 2/2, mana value 2
HYDRA = "t_cae_hydra"  # {1}{G} 0/0, enters with two +1/+1 counters, draws on its own
SCALES = "t_rc_scales"  # Hardened Scales: +1/+1 counters on a creature you control, plus one
BOUNDARY = "mossborn_hydra"  # {2}{G} 0/0 enters with a +1/+1 counter: mana value exactly 3
BIG = "serra_angel"  # {3}{W}{W}, mana value 5

SPEC = {
    "op": "look_at_top",
    "player": "you",
    "amount": {"const": 7},
    "destination": "battlefield",
    "objects": {"count": 1, "optional": True, "types": ["Creature"]},
    "counters": {"+1/+1": 3},
    "counters_if": {"mana_value": {"op": "<=", "value": {"const": 3}}},
    "rest_to_bottom": True,
}


def a_library(builder, top, mine=()):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + list(mine))
        .library(0, [*top, *(["island"] * (9 - len(top)))])
        .library(1, ["island"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    return game, list(game.state.players[0].library[: len(top)])


def dig(game, spec=SPEC, pick=lambda decision: [0]):
    """Run the op; ``pick`` answers the choice (indices into its options)."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, [spec])
    try:
        decision = next(gen)
        while True:
            decision = gen.send(pick(decision))
    except StopIteration:
        pass


def counters(game, oid) -> int:
    return game.state.objects[oid].counters.get("+1/+1", 0)


def placed(game, oid) -> list:
    return [
        e
        for e in game.state.events
        if e.type == EventType.COUNTER_PLACED and e.data.get("oid") == oid
    ]


class TestTheCountersArriveWithTheCard:
    def test_a_small_creature_enters_with_three(self, builder):
        game, (bear,) = a_library(builder, [BEAR])
        dig(game)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert counters(game, bear) == 3

    def test_one_counter_placed_event_reports_all_three(self, builder):
        """122.6: given counters as it enters is "put on" -- once."""
        game, (bear,) = a_library(builder, [BEAR])
        dig(game)
        events = placed(game, bear)
        assert [(e.data["counter"], e.data["amount"]) for e in events] == [("+1/+1", 3)]

    def test_controlled_by_the_player_who_looked(self, builder):
        game, (bear,) = a_library(builder, [BEAR])
        dig(game)
        assert game.state.objects[bear].controller == 0


class TestOnePlacementWithThePrintedCounters:
    """The near miss: `add_counters` after the move is a second placement."""

    def test_they_join_the_printed_enters_with(self, builder):
        game, (hydra,) = a_library(builder, [HYDRA])
        dig(game)
        assert counters(game, hydra) == 5
        assert [e.data["amount"] for e in placed(game, hydra)] == [5]

    def test_hardened_scales_adds_one_not_two(self, builder):
        """(2 + 3) + 1 = 6. Two placements would be (2 + 1) + (3 + 1) = 7."""
        game, (hydra,) = a_library(builder, [HYDRA], mine=[SCALES])
        dig(game)
        assert counters(game, hydra) == 6

    def test_its_own_counter_trigger_fires_once(self, builder):
        """"Whenever you put one or more +1/+1 counters on this creature, draw a
        card" -- one placement, one draw. Two placements would draw two."""
        game, (hydra,) = a_library(builder, [HYDRA])
        dig(game)
        queued = [t for t in game.state.pending_triggers if t.source_oid == hydra]
        assert len(queued) == 1

    def test_a_zero_zero_never_dies_on_the_way_in(self, builder):
        game, (hydra,) = a_library(builder, [HYDRA])
        dig(game)
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)
        assert game.state.objects[hydra].zone is Zone.BATTLEFIELD


class TestTheConditionReadsTheCardPutThere:
    def test_mana_value_three_is_included(self, builder):
        """The boundary: "3 or less" includes three. Mossborn Hydra prints one."""
        game, (hydra,) = a_library(builder, [BOUNDARY])
        dig(game)
        assert counters(game, hydra) == 1 + 3

    def test_mana_value_five_gets_none(self, builder):
        game, (angel,) = a_library(builder, [BIG])
        dig(game)
        assert game.state.objects[angel].zone is Zone.BATTLEFIELD
        assert counters(game, angel) == 0
        assert placed(game, angel) == []

    def test_the_card_chosen_is_the_one_asked_about(self, builder):
        """Two creatures in the window, the big one taken: no counters, and the
        small one that was passed over is not the one the condition read."""
        game, (bear, angel) = a_library(builder, [BEAR, BIG])
        dig(game, pick=lambda d: [1])
        assert counters(game, angel) == 0
        assert game.state.objects[bear].zone is Zone.LIBRARY

    def test_without_a_condition_every_arrival_gets_them(self, builder):
        game, (angel,) = a_library(builder, [BIG])
        dig(game, spec={k: v for k, v in SPEC.items() if k != "counters_if"})
        assert counters(game, angel) == 3


class TestNothingTakenNothingCountered:
    def test_declining_puts_nothing_anywhere(self, builder):
        game, (bear,) = a_library(builder, [BEAR])
        dig(game, pick=lambda d: [])
        assert game.state.objects[bear].zone is Zone.LIBRARY
        assert game.state.objects[bear].counters == {}

    def test_the_rest_goes_to_the_bottom(self, builder):
        game, (bear,) = a_library(builder, [BEAR])
        dig(game, pick=lambda d: [])
        library = game.state.players[0].library
        assert len(library) == 9
        assert library.index(bear) >= len(library) - 7

    def test_the_counters_wear_off_with_the_arrival(self, builder):
        """A promise about one arrival: the card coming back later is a new
        object (400.7) and enters with only what it prints."""
        from automtg.engine.zones import move_object

        game, (hydra,) = a_library(builder, [HYDRA])
        dig(game)
        move_object(game.state, hydra, Zone.HAND)
        move_object(game.state, hydra, Zone.BATTLEFIELD, to_player=0)
        assert counters(game, hydra) == 2


def card_with(**extra) -> dict:
    return {
        "id": "t_symbiosis_probe",
        "name": "Symbiosis Probe",
        "types": ["Sorcery"],
        "mana_cost": "{G}",
        "spell_effects": [{**SPEC, **extra}],
    }


class TestTheLoaderRefusesWhatWouldBeDropped:
    def test_the_witness_shape_loads(self):
        compile_card(CardModel.model_validate(card_with()))

    def test_counters_need_the_battlefield(self):
        """Counters on a card going to a hand would load and do nothing."""
        with pytest.raises(DslError, match="battlefield"):
            compile_card(CardModel.model_validate(card_with(destination="hand")))

    def test_a_condition_needs_counters(self):
        bare = {k: v for k, v in SPEC.items() if k != "counters"}
        card = card_with()
        card["spell_effects"] = [bare]
        with pytest.raises(DslError, match="counters_if"):
            compile_card(CardModel.model_validate(card))

    def test_counters_are_kinds_to_positive_amounts(self):
        with pytest.raises(DslError, match="counters"):
            compile_card(CardModel.model_validate(card_with(counters={"+1/+1": 0})))
        with pytest.raises(DslError, match="counters"):
            compile_card(CardModel.model_validate(card_with(counters=3)))

    def test_not_beside_cast_free(self):
        card = card_with(cast_free=True)
        card["spell_effects"][0].pop("destination")
        with pytest.raises(DslError, match="counters"):
            compile_card(CardModel.model_validate(card))
