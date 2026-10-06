""""Until your next turn, your life total can't change." -- 118.5

    Teferi's Protection -- "Until your next turn, **your life total can't
    change** and you gain protection from everything. All permanents you control
    phase out."

A prohibition on the *change*, in both directions, which is the thing nothing in
the engine could say. `replace_life_loss` is the near miss and misses three
ways: it is a `static_effect`, so only a permanent can carry one and an Instant's
`spell_effects` cannot install it; it multiplies a loss rather than forbidding a
change, and a multiplier of zero would still be a downward-only rewrite; and it
is wired into `lose_life` and the loss half of `damage_player` only, so
`gain_life` moves the total straight past it. The `prevent_damage` op is
player-scoped and stops damage alone.

**Four doors, tested separately, because there is no single choke point.** The
engine subtracts life in `damage_player` directly rather than routing damage
through `lose_life` -- deliberately, since only the loss is multiplied and never
the damage -- and paying life is a cost check rather than a call at all. A lock
installed in three of the four is a life total that holds still until somebody
attacks.

Two things the lock deliberately does **not** do, both of which would be a
different card:

* It does not stop the damage. Damage is still dealt and `DAMAGE_DEALT` still
  fires; only the life total holds still. Protection is the effect that stops
  damage, and Teferi's Protection prints both sentences because they differ.
* It does not make paying life free. 118.4 makes paying life a loss of life, so
  a cost that cannot be paid is refused by `can_pay` -- the difference between a
  War Room that cannot be activated and one that draws for nothing.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.costs import can_pay
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_player, gain_life, life_locked, lose_life
from automtg.engine.structs import LifeLock
from tests.conftest import _default_answer, action_for_card, oids_of

LOCK = "t_life_lock"  # instant: until your next turn, your life total can't change
BEAR = "t_bear"
VANGUARD = "adanto_vanguard"  # Pay 4 life: this creature gains indestructible


def board(builder, *, locked: int | None = 0):
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * 4)
        .battlefield(1, [BEAR])
        # A castable card in hand, so the position stops at a real decision
        # rather than auto-passing whole turns forward.
        .hand(0, ["t_bolt"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
        .build()
    )
    if locked is not None:
        game.state.life_locks.append(LifeLock(player=locked))
    return game


def run_to_next_turn(game, limit: int = 400) -> None:
    turn = game.state.turn
    for _ in range(limit):
        if game.over or game.state.turn != turn:
            return
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        preferred = (
            [a for a in actions if a.kind is ActionKind.PASS]
            or [a for a in actions if a.kind is ActionKind.FINISH_DECLARATION]
            or [a for a in actions if a.kind is ActionKind.NO]
            or actions
        )
        game.apply(preferred[0])


def settle(game, limit: int = 100) -> None:
    for _ in range(limit):
        decision = game.pending()
        if decision is None or not game.state.stack:
            return
        game.apply(_default_answer(game, decision))


class TestTheFourDoors:
    def test_life_gain_moves_nothing(self, builder):
        game = board(builder)
        life = game.state.players[0].life
        assert gain_life(game.state, 0, 5) == 0
        assert game.state.players[0].life == life

    def test_life_loss_moves_nothing(self, builder):
        game = board(builder)
        life = game.state.players[0].life
        assert lose_life(game.state, 0, 5) == 0
        assert game.state.players[0].life == life

    def test_damage_moves_nothing(self, builder):
        """The door `lose_life` alone would have missed."""
        game = board(builder)
        life = game.state.players[0].life
        damage_player(game.state, 0, 4, oids_of(game, BEAR)[0])
        assert game.state.players[0].life == life

    def test_life_cannot_be_paid_as_a_cost(self, builder):
        """118.4: paying life is losing it, so the cost cannot be paid at all."""
        game = (
            builder(players=2)
            .battlefield(0, [VANGUARD])
            .hand(0, ["t_bolt"])
            .library(0, ["forest"] * 20)
            .active(0)
            .build()
        )
        vanguard = oids_of(game, VANGUARD)[0]
        # Its second ability is the one with a price; the first is the attack
        # trigger, which has no cost at all.
        cost = next(
            a.cost
            for a in game.state.card(vanguard).abilities
            if a.cost is not None and a.cost.pay_life
        )
        assert can_pay(game.state, 0, cost, vanguard), "payable before the lock"

        game.state.life_locks.append(LifeLock(player=0))

        assert not can_pay(game.state, 0, cost, vanguard)


class TestWhatItDoesNotStop:
    def test_the_damage_is_still_dealt(self, builder):
        """Only the life total holds still. Protection is the other sentence."""
        game = board(builder)
        mark = len(game.state.events)
        damage_player(game.state, 0, 4, oids_of(game, BEAR)[0])
        kinds = [e.type for e in game.state.events[mark:]]
        assert "damage_dealt" in kinds

    def test_no_life_lost_event_is_fired(self, builder):
        """Bloodthirsty Conqueror must not pay out for a loss that did not happen."""
        game = board(builder)
        mark = len(game.state.events)
        damage_player(game.state, 0, 4, oids_of(game, BEAR)[0])
        assert "life_lost" not in [e.type for e in game.state.events[mark:]]

    def test_no_life_gained_event_is_fired(self, builder):
        game = board(builder)
        mark = len(game.state.events)
        gain_life(game.state, 0, 4)
        assert "life_gained" not in [e.type for e in game.state.events[mark:]]

    def test_the_other_seat_is_untouched(self, builder):
        game = board(builder)
        life = game.state.players[1].life
        assert lose_life(game.state, 1, 3) == 3
        assert game.state.players[1].life == life - 3


class TestTheWearingOff:
    def test_it_survives_the_cleanup_step(self, builder):
        game = board(builder)
        run_to_next_turn(game)
        assert game.state.active_idx == 1
        assert life_locked(game.state, 0)

    def test_it_ends_in_the_locked_players_untap_step(self, builder):
        game = board(builder)
        run_to_next_turn(game)  # the opponent's turn
        run_to_next_turn(game)  # back to ours
        assert game.state.active_idx == 0
        assert not life_locked(game.state, 0)
        assert lose_life(game.state, 0, 3) == 3


class TestCastingTheSpell:
    def test_resolving_it_installs_the_lock(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 4)
            .hand(0, [LOCK])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(0)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, LOCK))
        settle(game)
        assert life_locked(game.state, 0)
        assert not life_locked(game.state, 1)


class TestTheLoaderRefusesNonsense:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_lock",
                "name": "Bad Lock",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "types": ["Instant"],
                "colors": ["W"],
                "color_identity": ["W"],
                "spell_effects": [effect],
            }
        )

    def test_an_unknown_duration(self):
        with pytest.raises(DslError, match="unknown lock_life_total duration"):
            compile_card(
                self._card({"op": "lock_life_total", "player": "you", "duration": "forever"})
            )

    def test_an_amount_is_refused(self):
        """A number here would read as a shield of that size and be ignored."""
        with pytest.raises(DslError, match="no 'amount'"):
            compile_card(
                self._card({"op": "lock_life_total", "player": "you", "amount": 3})
            )
