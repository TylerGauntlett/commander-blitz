""""Whenever **one or more** opponents lose life" -- Emet-Selch of the Third Seat.

Rule 603.2c: an ability that triggers on "one or more" of something triggers
once for an event that does several of them at once. "Each opponent loses 2
life" is one life-loss event however many seats it reaches, and one combat
damage step is one damage event however many players it hits (510.2). But
`LIFE_LOST` fires once per player, so without a batch on the event Emet-Selch's
trigger fired once per opponent -- and since its "do this only once each turn"
limits the cast rather than the trigger, every extra firing was an extra chance
to cast from the graveyard that the printed card does not give.

`primitives.lose_life` and `primitives.damage_player` now put a ``batch`` on
`LIFE_LOST` -- the effect op or cost payment (`state.event_batch`), or the
combat damage step `combat.deal_combat_damage` hands down -- and `life_lost` is
in `triggers.BATCHED_EVENTS`. What that has to mean, each a different card if
it is wrong:

- **A drain across the table is one trigger**, by `lose_life` or by `damage`.
- **One combat damage step is one trigger**, two opponents hit or one; a
  first-strike step is a step of its own (510.4) and triggers again.
- **After the controller check.** Your own loss beside an opponent's cannot
  spend the batch, and your loss alone fires nothing.
- **Not once a turn.** A later, separate loss triggers again.

`t_bll_greedy_tally` is the counterfactual, the same trigger without
`batched`, so each claim is measured against the card that lacks it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import attack_with, find_action, only_oid, pass_until

TALLY = "t_bll_tally"  # one or more opponents lose life: a charge counter
GREEDY = "t_bll_greedy_tally"  # the same trigger without `batched`
BEAR = "t_bear"  # 2/2
FIRST_STRIKER = "t_first_striker"  # 2/2 first strike
START = 40  # the sandbox's starting life


def board(builder, watcher: str, *, players: int = 4):
    """``watcher`` on player 0's side, at main phase, nothing else in play."""
    game = (
        builder(players=players)
        .battlefield(0, [watcher])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, only_oid(game, watcher, 0)


def resolve(game, *specs) -> None:
    """Run ``specs`` the way a resolving spell of player 0's runs them."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    for _ in execute(ctx, list(specs)):
        raise AssertionError("these effects ask nothing")


def settle(game) -> None:
    game._advance()
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def charges(game, oid: int) -> int:
    return game.state.objects[oid].counter("charge")


def drain(player, amount: int = 2) -> dict:
    return {"op": "lose_life", "player": player, "amount": {"const": amount}}


class TestOneLossEventIsOneTrigger:
    def test_each_opponent_losing_life_triggers_once(self, builder):
        game, oid = board(builder, TALLY)
        resolve(game, drain("each_opponent"))
        assert len(game.state.pending_triggers) == 1
        settle(game)
        assert charges(game, oid) == 1
        assert all(p.life == START - 2 for p in game.state.players[1:])

    def test_without_batched_the_same_drain_triggers_per_opponent(self, builder):
        game, oid = board(builder, GREEDY)
        resolve(game, drain("each_opponent"))
        settle(game)
        assert charges(game, oid) == 3

    def test_damage_to_each_opponent_triggers_once(self, builder):
        """Damage causes loss of life, and one `damage` op is one event."""
        game, oid = board(builder, TALLY)
        resolve(game, {"op": "damage", "player": "each_opponent", "amount": {"const": 1}})
        settle(game)
        assert charges(game, oid) == 1

    def test_two_separate_losses_trigger_twice(self, builder):
        """Not `max_per_turn: 1`: two instructions are two events, even in one
        resolution, because they are not simultaneous."""
        game, oid = board(builder, TALLY)
        resolve(game, drain("each_opponent"), drain("each_opponent"))
        settle(game)
        assert charges(game, oid) == 2


class TestWhoseLifeItWas:
    def test_your_loss_beside_the_opponents_does_not_spend_the_batch(self, builder):
        """"Each player loses 2 life" -- seat 0 goes first and is not an
        opponent; the opponents' losses after it still fire the ability."""
        game, oid = board(builder, TALLY)
        resolve(game, drain("each_player"))
        settle(game)
        assert charges(game, oid) == 1
        assert game.state.players[0].life == START - 2

    def test_your_loss_alone_fires_nothing(self, builder):
        game, oid = board(builder, TALLY)
        resolve(game, drain("you"))
        settle(game)
        assert charges(game, oid) == 0


def swing(builder, watcher: str, attackers: list[tuple[str, int]]):
    """Player 0 attacks with each ``(card, defending seat)``; nobody blocks.

    Returns ``(game, watcher oid)`` with combat over and every trigger resolved.
    """
    game = (
        builder(players=3)
        .battlefield(0, [watcher, *(card for card, _ in attackers)])
        .active(0)
        .build()
    )
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    sent: set[int] = set()
    for card, seat in attackers:
        oid = next(
            o.oid
            for o in game.state.battlefield_objects(0)
            if o.def_id == card and o.oid not in sent
        )
        attack_with(game, oid, seat)
        sent.add(oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game,
        lambda g: g.state.step >= Step.END_OF_COMBAT
        and not g.state.stack
        and not g.state.pending_triggers,
    )
    return game, only_oid(game, watcher, 0)


class TestOneCombatDamageStepIsOneTrigger:
    def test_two_opponents_hit_in_one_step_trigger_once(self, builder):
        game, oid = swing(builder, TALLY, [(BEAR, 1), (BEAR, 2)])
        assert game.state.players[1].life == START - 2
        assert game.state.players[2].life == START - 2
        assert charges(game, oid) == 1

    def test_without_batched_the_same_swing_triggers_twice(self, builder):
        game, oid = swing(builder, GREEDY, [(BEAR, 1), (BEAR, 2)])
        assert charges(game, oid) == 2

    def test_a_first_strike_step_is_an_event_of_its_own(self, builder):
        """510.4: the first striker's hit and the bear's are two damage steps."""
        game, oid = swing(builder, TALLY, [(FIRST_STRIKER, 1), (BEAR, 2)])
        assert game.state.players[1].life == START - 2
        assert game.state.players[2].life == START - 2
        assert charges(game, oid) == 2


def _model(trigger: dict) -> CardModel:
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
                }
            ],
        }
    )


class TestTheLoader:
    def test_batched_loads_on_life_lost(self):
        card = compile_card(
            _model({"event": "life_lost", "controller": "opponent", "batched": True})
        )
        assert card.abilities[0].trigger.batched

    def test_batched_is_still_refused_on_life_gained(self):
        """Its event carries no batch, so the flag would count every gain."""
        with pytest.raises(DslError, match="batched"):
            compile_card(_model({"event": "you_gain_life", "batched": True}))
