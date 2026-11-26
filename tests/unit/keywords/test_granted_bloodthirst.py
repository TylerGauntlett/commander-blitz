"""``grant_bloodthirst`` — a spell gains bloodthirst, judged as it enters.

    Bloodlord of Vaasgoth — "Whenever you cast a Vampire creature spell, it
    gains bloodthirst 3."

702.54a: bloodthirst N means "if an opponent was dealt damage this turn, this
permanent enters with N +1/+1 counters on it". It is a replacement on the
arrival (614.1c), so the question is asked **as the permanent enters**, not when
the Bloodlord's trigger resolves. `spell_enters_with_counters` is the near miss
and is wrong exactly there: it evaluates its amount when the trigger resolves
and takes no condition, so damage dealt to an opponent with the Vampire still
on the stack would be missed, and an unconditional promise would give the
counters on a turn nobody was hurt.

The op stages the amount on the spell's object (`GameObject.cast_bloodthirst`),
`move_object` carries it only to the battlefield, and
`zones._enter_battlefield` judges it on the one placement (122.6), so Hardened
Scales adds one to the total. Instances add (702.54c).

Witness: Bloodlord of Vaasgoth (`bloodlord_of_vaasgoth` in `data/cards/auto/`).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.objects import PLUS_ONE
from commanderblitz.engine.primitives import damage_player
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, pass_until, settle

LORD = "t_thirst_lord"  # Whenever you cast a Vampire creature spell, it gains bloodthirst 3.
FLEDGLING = "t_thirst_fledgling"  # vanilla 2/2 Vampire for {2}
SPRINTER = "t_glory_sprinter"  # vanilla 2/2 Soldier for {2}
SCALES = "hardened_scales"
BOLT = "lightning_bolt"  # 3 damage to any target, {R}


def position(builder, hand=(FLEDGLING,), lords=1, extra=()):
    return (
        builder(players=2)
        .hand(0, list(hand))
        .battlefield(0, [LORD] * lords + ["forest"] * 4 + list(extra))
        .library(0, ["island"] * 20)
        .build()
    )


def hurt_opponent(game, amount: int = 1) -> None:
    damage_player(game.state, 1, amount, None)


def cast(game, card_id: str) -> int:
    action = action_for_card(game, ActionKind.CAST, card_id)
    game.apply(action)
    return action.source


def trigger_resolved(game, oid: int) -> None:
    """Pass until the Bloodlord's trigger has resolved and the Vampire is the
    only thing on the stack."""
    pass_until(
        game,
        lambda g: [i.oid for i in g.state.stack] == [oid]
        and not g.state.pending_triggers
        and g.state.objects[oid].cast_bloodthirst > 0,
    )


def cast_at_opponent(game) -> None:
    """Lightning Bolt at player 1."""
    game.apply(next(a for a in game.legal_actions() if str(a) == "Action(Cast Lightning Bolt -> P1)"))


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(PLUS_ONE, 0)


class TestItIsJudgedAsThePermanentEnters:
    def test_a_hurt_opponent_gives_three_counters(self, builder):
        game = position(builder)
        hurt_opponent(game)
        oid = cast(game, FLEDGLING)
        settle(game)
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert counters(game, oid) == 3

    def test_no_damage_this_turn_gives_none(self, builder):
        game = position(builder)
        oid = cast(game, FLEDGLING)
        settle(game)
        assert counters(game, oid) == 0

    def test_damage_after_the_trigger_resolved_still_counts(self, builder):
        """The whole point of judging on arrival: the opponent is bolted with
        the Vampire still on the stack, after the Bloodlord's trigger is gone."""
        game = position(builder, hand=(FLEDGLING, BOLT), extra=("mountain",))
        oid = cast(game, FLEDGLING)
        trigger_resolved(game, oid)
        assert game.state.objects[oid].zone is Zone.STACK
        assert game.state.objects[oid].cast_bloodthirst == 3
        assert not game.state.turn_ledger.damage_taken.get(1)
        cast_at_opponent(game)
        settle(game)
        assert game.state.players[1].life == 37
        assert counters(game, oid) == 3

    def test_your_own_damage_does_not_count(self, builder):
        game = position(builder)
        damage_player(game.state, 0, 2, None)
        oid = cast(game, FLEDGLING)
        settle(game)
        assert counters(game, oid) == 0


class TestWhichSpellsGainIt:
    def test_a_non_vampire_gains_nothing(self, builder):
        game = position(builder, hand=(SPRINTER,))
        hurt_opponent(game)
        oid = cast(game, SPRINTER)
        settle(game)
        assert counters(game, oid) == 0

    def test_two_instances_add(self, builder):
        """702.54c: each instance applies separately."""
        game = position(builder, lords=2)
        hurt_opponent(game)
        oid = cast(game, FLEDGLING)
        settle(game)
        assert counters(game, oid) == 6


class TestOnePlacement:
    def test_hardened_scales_adds_one_to_the_total(self, builder):
        game = position(builder, extra=(SCALES,))
        hurt_opponent(game)
        oid = cast(game, FLEDGLING)
        settle(game)
        assert counters(game, oid) == 4

    def test_a_spell_that_never_arrives_keeps_nothing(self, builder):
        game = position(builder)
        oid = cast(game, FLEDGLING)
        trigger_resolved(game, oid)
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert game.state.objects[oid].cast_bloodthirst == 0


def _model(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_bad_lord",
            "name": "Bad Lord",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "Whenever you cast a creature spell, it gains bloodthirst.",
                    "trigger": {"event": "spell_cast", "controller": "you"},
                    "effects": [effect],
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_op_loads(self):
        compile_card(_model({"op": "grant_bloodthirst", "amount": 3}))

    @pytest.mark.parametrize("amount", [None, 0, -1, True])
    def test_an_amount_that_is_not_a_positive_integer_is_refused(self, amount):
        effect = {"op": "grant_bloodthirst"}
        if amount is not None:
            effect["amount"] = amount
        with pytest.raises(DslError, match="grant_bloodthirst"):
            compile_card(_model(effect))
