"""A life gain that becomes a loss: "that player loses that much life instead".

Plague Drone -- "Rot Fly -- If an opponent would gain life, that player loses
that much life instead." -- is the witness, and Tainted Remedy prints the same
sentence. Rule 614.1a makes it a replacement effect of the life-gain event, the
family of Alhammarret's Archive and Angel of Vitality, so it is the third axis
of `replace_life_gain`, `lose_instead`, read at `primitives.gain_life`.

The near misses are each a different card: `cant_gain_life` stops the gain but
nobody loses life; a `you_gain_life` trigger plus `lose_life` lets the gain
happen, fires every "whenever you gain life" payoff and then uses the stack.

The claims:

* **The gain never happens**: no `LIFE_GAINED`, the life total goes down by
  exactly the gain, and the loss is one `LIFE_LOST` event.
* **Lifelink reaches it** (702.15b): the gain from lifelink damage is replaced
  too, and the damage itself is untouched.
* **616.1 against a gain doubler or addend**: the gaining player orders the
  replacements, and once this one applies the event is a loss no gain
  replacement reaches. They apply it first and lose the unmodified amount.
* **The loss is an ordinary loss**: a loss replacement (Bloodletter) applies.
* **"Can't" and a locked life total win** (101.2, 118.5): a gain that cannot
  happen is no event to replace, so nobody loses life.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import life_gain_becomes_loss
from commanderblitz.engine.primitives import damage_player, gain_life
from commanderblitz.engine.structs import LifeLock
from commanderblitz.engine.zones import move_object
from tests.conftest import action_for_card, pass_until

ROT_FLY = "t_rot_fly"
SELF_ROT_FLY = "t_self_rot_fly"
OPPONENT_ARCHIVE = "t_opponent_archive"
OPPONENT_VITALITY = "t_opponent_vitality"
BLOODLETTER = "t_always_bloodletter"
EREBOS = "t_erebos"
LIFELINK_BEAR = "t_lifelink_bear"
GAIN_SPELL = "t_gain_spell"


def position(builder, *ids: str, theirs=(), hand=()):
    """Two players at 40, ``ids`` on player 0's battlefield, ``theirs`` on player 1's."""
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .battlefield(0, list(ids))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    game.state.active_idx = 0
    return game


def oid_of(game, def_id: str) -> int:
    return next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == def_id
    )


def events_of(game, mark: int, kind: str) -> list:
    return [e for e in game.state.events[mark:] if e.type == kind]


class TestWhoItReaches:
    def test_nothing_on_the_board_replaces_nothing(self, builder):
        game = position(builder)
        assert not life_gain_becomes_loss(game.state, 1)

    def test_it_reaches_the_opponent(self, builder):
        game = position(builder, ROT_FLY)
        assert life_gain_becomes_loss(game.state, 1)

    def test_it_does_not_reach_its_controller(self, builder):
        """"If an *opponent* would gain life" -- the Drone's controller gains."""
        game = position(builder, ROT_FLY)
        assert not life_gain_becomes_loss(game.state, 0)
        assert gain_life(game.state, 0, 3) == 3
        assert game.state.players[0].life == 43

    def test_affects_player_you_points_it_home(self, builder):
        game = position(builder, SELF_ROT_FLY)
        assert life_gain_becomes_loss(game.state, 0)
        assert not life_gain_becomes_loss(game.state, 1)

    def test_a_gain_doubler_is_not_a_loss(self, builder):
        game = position(builder, OPPONENT_ARCHIVE)
        assert not life_gain_becomes_loss(game.state, 1)


class TestTheGainBecomesALoss:
    def test_three_gained_is_three_lost(self, builder):
        game = position(builder, ROT_FLY)
        assert gain_life(game.state, 1, 3) == 0
        assert game.state.players[1].life == 37

    def test_no_gain_event_and_one_loss_event(self, builder):
        game = position(builder, ROT_FLY)
        mark = len(game.state.events)
        gain_life(game.state, 1, 3)
        assert events_of(game, mark, "life_gained") == []
        assert [e.data["amount"] for e in events_of(game, mark, "life_lost")] == [3]

    def test_a_gain_of_zero_is_no_loss(self, builder):
        game = position(builder, ROT_FLY)
        mark = len(game.state.events)
        assert gain_life(game.state, 1, 0) == 0
        assert game.state.players[1].life == 40
        assert events_of(game, mark, "life_lost") == []

    def test_two_drones_lose_it_once(self, builder):
        """614.5: once replaced, the event is a loss the second Drone cannot touch."""
        game = position(builder, ROT_FLY, ROT_FLY)
        gain_life(game.state, 1, 3)
        assert game.state.players[1].life == 37

    def test_it_lifts_when_the_drone_leaves(self, builder):
        game = position(builder, ROT_FLY)
        move_object(game.state, oid_of(game, ROT_FLY), Zone.GRAVEYARD)
        assert gain_life(game.state, 1, 3) == 3
        assert game.state.players[1].life == 43


class TestLifelink:
    def test_lifelink_damage_becomes_a_loss_for_its_controller(self, builder):
        game = position(builder, ROT_FLY, theirs=(LIFELINK_BEAR,))
        dealt = damage_player(game.state, 0, 2, oid_of(game, LIFELINK_BEAR))
        assert dealt == 2
        assert game.state.players[0].life == 38
        assert game.state.players[1].life == 38


class TestAgainstOtherReplacements:
    @pytest.mark.parametrize(
        "arrival", [(ROT_FLY, OPPONENT_ARCHIVE), (OPPONENT_ARCHIVE, ROT_FLY)],
        ids=["drone-first", "archive-first"],
    )
    def test_a_gain_doubler_does_not_double_the_loss(self, builder, arrival):
        """616.1: the gaining player applies the Drone first and loses 3, not 6."""
        game = position(builder, *arrival)
        gain_life(game.state, 1, 3)
        assert game.state.players[1].life == 37

    def test_a_gain_addend_does_not_add_to_the_loss(self, builder):
        game = position(builder, OPPONENT_VITALITY, ROT_FLY)
        gain_life(game.state, 1, 3)
        assert game.state.players[1].life == 37

    def test_a_loss_doubler_doubles_the_loss(self, builder):
        """The replaced event is a life loss, and Bloodletter replaces that."""
        game = position(builder, ROT_FLY, BLOODLETTER)
        gain_life(game.state, 1, 3)
        assert game.state.players[1].life == 34

    def test_cant_gain_life_means_nothing_to_replace(self, builder):
        game = position(builder, ROT_FLY, EREBOS)
        assert gain_life(game.state, 1, 3) == 0
        assert game.state.players[1].life == 40

    def test_a_locked_life_total_stays_locked(self, builder):
        game = position(builder, ROT_FLY)
        game.state.life_locks.append(LifeLock(player=1))
        assert gain_life(game.state, 1, 3) == 0
        assert game.state.players[1].life == 40


class TestItReachesRealPlay:
    def test_a_gain_spell_loses_life(self, builder):
        game = position(builder, SELF_ROT_FLY, hand=(GAIN_SPELL,))
        game.apply(action_for_card(game, ActionKind.CAST, GAIN_SPELL))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[0].life == 37


class TestTheLoaderRefusesWhatIsNotACard:
    def test_the_printed_shape_loads(self):
        static = compile_card(CardModel.model_validate(_card(lose_instead=True))).abilities[0]
        assert static.static["lose_instead"] is True

    def test_false_is_refused(self):
        with pytest.raises(DslError, match="lose_instead"):
            compile_card(CardModel.model_validate(_card(lose_instead=False)))

    @pytest.mark.parametrize("other", [{"gain_multiplier": 2}, {"gain_addend": 1}])
    def test_it_is_exclusive_with_the_other_axes(self, other):
        with pytest.raises(DslError, match="not both"):
            compile_card(CardModel.model_validate(_card(lose_instead=True, **other)))

    def test_it_is_refused_on_another_effect(self):
        card = _card(lose_instead=True)
        card["abilities"][0]["effect"] = "replace_life_loss"
        card["abilities"][0]["loss_multiplier"] = 2
        with pytest.raises(DslError, match="lose_instead"):
            compile_card(CardModel.model_validate(card))


def _card(**fields) -> dict:
    text = "If an opponent would gain life, that player loses that much life instead."
    return {
        "id": "t_bad_rot_fly",
        "name": "Test Bad Rot Fly",
        "oracle_text": text,
        "mana_cost": "{3}",
        "types": ["Artifact"],
        "abilities": [
            {
                "kind": "static",
                "text": text,
                "effect": "replace_life_gain",
                "affects_player": "opponent",
                **fields,
            }
        ],
    }
