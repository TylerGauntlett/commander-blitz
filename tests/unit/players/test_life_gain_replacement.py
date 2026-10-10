"""Replacing a life gain: "you gain twice that much life instead".

Alhammarret's Archive -- "If you would gain life, you gain twice that much life
instead." -- is the witness. Rule 614.1a makes it a replacement effect: the gain
that would have happened does not, and a larger one happens in its place. The
near miss is a `you_gain_life` trigger that gains the same amount again, and it
is a different card three ways: the second gain goes on the stack, where it can
be responded to; it is a second `LIFE_GAINED` event, so every "whenever you gain
life" permanent on the board pays out twice; and it triggers itself, forever.

Life goes **up** in exactly one place in this engine, `primitives.gain_life`,
which the `gain_life` op and lifelink (702.15b) both reach. So unlike its loss
twin there is one call site -- and lifelink is the path worth testing
separately, because it is the gain that does not look like one on the card.

Two properties beyond the life total, each of which an implementation could get
wrong while every life-total assertion still passed:

* `LIFE_GAINED` carries the **replaced** amount. "Whenever you gain life, put
  that many +1/+1 counters" reads the event, and under an Archive the event and
  the life total must agree.
* Lifelink gains twice the damage, but the damage is not doubled: the loss on
  the other side is still what was dealt.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import life_gain_multiplier
from commanderblitz.engine.primitives import damage_player, gain_life
from commanderblitz.engine.structs import LifeLock
from tests.conftest import action_for_card, pass_until

ARCHIVE = "t_archive"
TURN_ARCHIVE = "t_turn_archive"
OPPONENT_ARCHIVE = "t_opponent_archive"
GAIN_SPELL = "t_gain_spell"
LIFELINK_BEAR = "t_lifelink_bear"


def position(builder, *doublers: str, active: int = 0, extra: str | None = None, hand=()):
    """Two players at 40, with ``doublers`` (and ``extra``) on player 0's battlefield."""
    ids = [*doublers] + ([extra] if extra else [])
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] * 4)
        .battlefield(0, ids)
        .hand(0, list(hand))
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    game.state.active_idx = active
    return game


def oid_of(game, def_id: str) -> int:
    return next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == def_id
    )


def gained_events(game, mark: int) -> list:
    return [e for e in game.state.events[mark:] if e.type == "life_gained"]


class TestTheMultiplierItself:
    """`life_gain_multiplier` is what `gain_life` reads."""

    def test_no_doubler_is_one(self, builder):
        game = position(builder)
        assert life_gain_multiplier(game.state, 0) == 1

    def test_it_reaches_its_controller(self, builder):
        game = position(builder, ARCHIVE)
        assert life_gain_multiplier(game.state, 0) == 2

    def test_it_does_not_reach_the_opponent(self, builder):
        """"If *you* would gain life" -- `affects_player` is not decoration."""
        game = position(builder, ARCHIVE)
        assert life_gain_multiplier(game.state, 1) == 1

    def test_affects_player_opponent_points_the_other_way(self, builder):
        game = position(builder, OPPONENT_ARCHIVE)
        assert life_gain_multiplier(game.state, 0) == 1
        assert life_gain_multiplier(game.state, 1) == 2

    def test_two_doublers_quadruple(self, builder):
        """614.5: each replacement applies once to the event, so x2 then x2."""
        game = position(builder, ARCHIVE, ARCHIVE)
        assert life_gain_multiplier(game.state, 0) == 4


class TestTheConditionIsRead:
    def test_on_its_controllers_turn_it_applies(self, builder):
        game = position(builder, TURN_ARCHIVE, active=0)
        assert life_gain_multiplier(game.state, 0) == 2

    def test_on_the_opponents_turn_it_does_not(self, builder):
        game = position(builder, TURN_ARCHIVE, active=1)
        assert life_gain_multiplier(game.state, 0) == 1


class TestAPlainLifeGain:
    def test_the_gain_is_doubled(self, builder):
        game = position(builder, ARCHIVE)
        gain_life(game.state, 0, 3)
        assert game.state.players[0].life == 46

    def test_it_returns_what_was_actually_gained(self, builder):
        game = position(builder, ARCHIVE)
        assert gain_life(game.state, 0, 3) == 6

    def test_the_event_carries_the_replaced_amount(self, builder):
        """One event, of 6 -- not a 3 and then another 3, and not a 3 at all."""
        game = position(builder, ARCHIVE)
        mark = len(game.state.events)
        gain_life(game.state, 0, 3)
        events = gained_events(game, mark)
        assert len(events) == 1
        assert events[0].data["amount"] == 6

    def test_undoubled_without_the_static(self, builder):
        game = position(builder)
        assert gain_life(game.state, 0, 3) == 3
        assert game.state.players[0].life == 43

    def test_zero_stays_zero(self, builder):
        game = position(builder, ARCHIVE)
        mark = len(game.state.events)
        assert gain_life(game.state, 0, 0) == 0
        assert game.state.players[0].life == 40
        assert gained_events(game, mark) == []

    def test_a_locked_life_total_is_still_locked(self, builder):
        """118.5 wins: twice a gain that cannot happen is still no gain."""
        game = position(builder, ARCHIVE)
        game.state.life_locks.append(LifeLock(player=0))
        assert gain_life(game.state, 0, 3) == 0
        assert game.state.players[0].life == 40

    def test_it_stops_applying_when_the_archive_leaves(self, builder):
        from commanderblitz.engine.enums import Zone
        from commanderblitz.engine.zones import move_object

        game = position(builder, ARCHIVE)
        move_object(game.state, oid_of(game, ARCHIVE), Zone.GRAVEYARD)
        assert gain_life(game.state, 0, 3) == 3


class TestLifelink:
    """702.15b -- the gain nobody writes as a `gain_life`."""

    def test_lifelink_gains_twice_the_damage(self, builder):
        game = position(builder, ARCHIVE, extra=LIFELINK_BEAR)
        damage_player(game.state, 1, 3, oid_of(game, LIFELINK_BEAR))
        assert game.state.players[0].life == 46

    def test_the_damage_itself_is_not_doubled(self, builder):
        game = position(builder, ARCHIVE, extra=LIFELINK_BEAR)
        assert damage_player(game.state, 1, 3, oid_of(game, LIFELINK_BEAR)) == 3
        assert game.state.players[1].life == 37


class TestItReachesRealPlay:
    def test_a_gain_spell_gains_double(self, builder):
        game = position(builder, ARCHIVE, hand=(GAIN_SPELL,))
        game.apply(action_for_card(game, ActionKind.CAST, GAIN_SPELL))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.players[0].life == 46


class TestTheLoaderRefusesWhatIsNotACard:
    @pytest.mark.parametrize("bad", [0, 1, -2])
    def test_multiplier_below_two_is_refused(self, bad):
        with pytest.raises(DslError, match="gain_multiplier"):
            compile_card(CardModel.model_validate(_card(gain_multiplier=bad)))

    def test_multiplier_is_required(self):
        with pytest.raises(DslError, match="gain_multiplier"):
            compile_card(CardModel.model_validate(_card()))

    def test_affects_player_is_required(self):
        card = _card(gain_multiplier=2)
        card["abilities"][0].pop("affects_player")
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(card))

    def test_the_multiplier_is_refused_on_another_effect(self):
        card = _card(gain_multiplier=2)
        card["abilities"][0]["effect"] = "replace_life_loss"
        card["abilities"][0]["loss_multiplier"] = 2
        with pytest.raises(DslError, match="gain_multiplier"):
            compile_card(CardModel.model_validate(card))

    def test_the_printed_shape_loads(self):
        compile_card(CardModel.model_validate(_card(gain_multiplier=2)))


def _card(**fields) -> dict:
    ability = {
        "kind": "static",
        "text": "If you would gain life, you gain twice that much life instead.",
        "effect": "replace_life_gain",
        "affects_player": "you",
        **fields,
    }
    return {
        "id": "t_bad_archive",
        "name": "Test Bad Archive",
        "oracle_text": "If you would gain life, you gain twice that much life instead.",
        "mana_cost": "{5}",
        "types": ["Artifact"],
        "abilities": [ability],
    }
