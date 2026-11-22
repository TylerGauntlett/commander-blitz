""""Counter target spell, activated ability, or triggered ability. **Its
controller** loses life equal to the number of creatures you control."

Deny the Witch. `{"controller_of_target": "t1"}` on a `spell_or_ability` (or
`ability_on_stack`) target names whoever controls the countered object.

The rules this rests on:

* 113.8 -- an ability on the stack has a controller, just as a spell does, so
  "its controller" means something for either half of the target. The loader
  used to refuse the key for both stack-ability kinds, which left the card
  inexpressible.
* 608.2h -- an effect that reads an object which has left its zone uses its
  last known information. The sentence is printed *after* the counter, and by
  then the item is off the stack: a countered ability ceases to exist and
  leaves no card anywhere to ask. `EffectContext.stack_controllers` records the
  seat as the resolution starts, and `select_players` falls back to it only for
  an item that is gone.

Without the fallback the card would load and bill nobody -- a counterspell
missing its second sentence, with nothing on the board to say so.

Witness: Deny the Witch (`data/authoring/gaps/deny_the_witch.json`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import select_players
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import push_triggered_ability
from commanderblitz.engine.structs import TargetRef, TriggerInstance
from tests.conftest import (
    action_for_card,
    activations,
    only_oid,
    pass_until,
    settle_to_priority,
)

DENY = "t_deny_the_witch"
TAX = "t_ability_tax"  # the `ability_on_stack` sibling
GAINER = "t_gainer"  # {T}: you gain 2 life
TRIGGERER = "t_upkeep_gainer"  # at the beginning of your upkeep, gain 2
BAIT = "t_plain_instant"  # {W}: you gain 1 life
BEAR = "t_bear"


def position(builder, bears: int = 2):
    """Seat 0 holds the counters and `bears` creatures; both seats can make an
    ability. Returns ``(game, theirs)``: the opponent's activated ability, on
    the stack with seat 0 to act."""
    game = (
        builder(players=2)
        .battlefield(0, ["island"] * 2 + [BEAR] * bears + [TRIGGERER])
        .battlefield(1, ["plains"] * 2 + [GAINER])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [DENY, TAX])
        .build(advance=False)
    )
    game._advance()
    pass_until(game, lambda g: bool(activations(g, only_oid(g, GAINER, 1))))
    game.apply(activations(game, only_oid(game, GAINER, 1))[0])
    theirs = game.state.stack[-1]
    pass_until(game, can_cast(DENY))
    return game, theirs


def can_cast(card_id: str):
    return lambda g: any(
        a.kind is ActionKind.CAST and g.state.objects[a.source].def_id == card_id
        for a in g.legal_actions()
    )


def cast(game, card_id: str, sid: int) -> None:
    action = action_for_card(game, ActionKind.CAST, card_id)
    assert [(r.kind, r.id) for r in action.targets] == [("stack", sid)]
    game.apply(action)
    settle_to_priority(game)


def life(game, seat: int) -> int:
    return game.state.players[seat].life


class TestItBillsTheAbilitysController:
    def test_an_opponents_activated_ability(self, builder):
        game, theirs = position(builder)
        before = life(game, 1)
        cast(game, DENY, theirs.sid)
        assert game.state.stack == []
        # Countered (no +2) and billed one per creature seat 0 controls.
        assert life(game, 1) == before - 2

    def test_your_own_triggered_ability_bills_you(self, builder):
        """"Its controller", not "an opponent": countering your own trigger
        is a legal line, and the bill comes back to you."""
        game, _ = position(builder)
        game.state.stack = []
        trig = TriggerInstance(
            source_oid=only_oid(game, TRIGGERER, 0), ability_index=0, controller=0
        )
        for _ in push_triggered_ability(game.state, trig):
            raise AssertionError("this trigger chooses nothing")
        mine = game.state.stack[-1]
        before = life(game, 0), life(game, 1)
        cast(game, DENY, mine.sid)
        assert (life(game, 0), life(game, 1)) == (before[0] - 2, before[1])

    def test_the_amount_is_read_on_resolution(self, builder):
        """No creatures, no life lost -- the counter still happens."""
        game, theirs = position(builder, bears=0)
        before = life(game, 1)
        cast(game, DENY, theirs.sid)
        assert game.state.stack == []
        assert life(game, 1) == before

    def test_ability_on_stack_says_it_too(self, builder):
        game, theirs = position(builder)
        before = life(game, 1)
        cast(game, TAX, theirs.sid)
        assert life(game, 1) == before - 2


class TestItBillsTheSpellsController:
    def test_a_countered_spell(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 2 + [BEAR] * 3)
            .battlefield(1, ["plains"] * 2)
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .hand(0, [DENY])
            .hand(1, [BAIT])
            .build(advance=False)
        )
        game._advance()
        pass_until(game, can_cast(BAIT))
        game.apply(action_for_card(game, ActionKind.CAST, BAIT))
        pass_until(game, can_cast(DENY))
        spell = game.state.stack[-1]
        before = life(game, 1)
        cast(game, DENY, spell.sid)
        assert life(game, 1) == before - 3


class TestTheLastKnownController:
    def test_a_live_item_answers_for_itself(self, builder):
        game, theirs = position(builder)
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": (TargetRef.stack(theirs.sid),)}
        )
        theirs.controller = 0  # control changed while it waited
        assert select_players(ctx, {"controller_of_target": "t1"}) == [0]

    def test_a_gone_item_answers_from_the_context(self, builder):
        game, theirs = position(builder)
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": (TargetRef.stack(theirs.sid),)}
        )
        assert ctx.stack_controllers == {theirs.sid: 1}
        game.state.stack = []
        assert select_players(ctx, {"controller_of_target": "t1"}) == [1]

    def test_a_context_built_after_it_left_knows_nothing(self, builder):
        """The record is taken as the resolution starts, never invented: an
        item already gone then was an illegal target, and 608.2b bills it
        nothing."""
        game, theirs = position(builder)
        game.state.stack = []
        ctx = EffectContext(
            state=game.state, controller=0, targets={"t1": (TargetRef.stack(theirs.sid),)}
        )
        assert select_players(ctx, {"controller_of_target": "t1"}) == []


class TestTheLoader:
    def _card(self, kind: str, player) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_deny_probe",
                "name": "Deny Probe",
                "oracle_text": "Counter target spell or ability. Its controller loses 1 life.",
                "mana_cost": "{U}",
                "types": ["Instant"],
                "targets": [{"id": "t1", "kind": kind}],
                "spell_effects": [
                    {"op": "counter", "target": "t1"},
                    {"op": "lose_life", "player": player, "amount": {"const": 1}},
                ],
            }
        )

    @pytest.mark.parametrize("kind", ["spell_or_ability", "ability_on_stack", "spell"])
    def test_controller_of_target_loads(self, kind):
        compile_card(self._card(kind, {"controller_of_target": "t1"}))

    @pytest.mark.parametrize("kind", ["spell_or_ability", "ability_on_stack"])
    def test_the_near_miss_is_refused_by_name(self, kind):
        """`{"target": "t1"}` would keep only player refs and bill nobody."""
        with pytest.raises(DslError, match="controller_of_target"):
            compile_card(self._card(kind, {"target": "t1"}))
