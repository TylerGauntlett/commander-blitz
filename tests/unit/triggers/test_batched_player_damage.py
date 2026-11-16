""""Whenever **one or more** Pirates you control deal damage to your opponents" --
Breeches, Brazen Plunderer; Malcolm, Keen-Eyed Navigator; Francisco, Fowl
Marauder.

Rule 603.2c: an ability that triggers on "one or more" of something triggers
once for an event that does several of them at once, and 510.2 makes a combat
damage step one simultaneous damage event however many creatures connect. The
sentence is about **any** damage (120.1), so the combat-only
`creatures_deal_combat_damage` is a narrower card -- a Pirate's ping would be
missed -- and the per-source `deals_damage_to_player` is a wider one: two
Pirates hitting one opponent would fire twice and exile two of that player's
cards, or make two Treasures.

`deals_damage_to_player` is in `triggers.BATCHED_EVENTS`, grouped by the
``batch`` `primitives.damage_player` stamps, and every later hit of the batch is
folded into the first firing (`triggers._joins_batched_player_damage`): the
seat joins ``damaged_players`` once, so "each of those opponents" is
``{"binding": "damaged_players"}`` and "for each opponent dealt damage" is its
``player_count``. What that has to mean, each a different card if wrong:

- **One combat damage step is one trigger**, however many Pirates connect and
  however many opponents they hit.
- **Noncombat damage counts**, and one effect op hitting every opponent is one
  trigger naming all of them.
- **The filter and `defending` are asked per hit**: a non-Pirate beside the
  Pirates is not one of them, and a Pirate hitting you is not "your opponents".
- **A later, separate event triggers again.**

`t_bpd_greedy_tally` is the same trigger without `batched`, so each claim is
measured against the card that lacks it.
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

TALLY = "t_bpd_tally"  # one or more Pirates -> your opponents: counters per seat, drain each
GREEDY = "t_bpd_greedy_tally"  # the same trigger without `batched`
PIRATE = "t_bpd_pirate"  # 2/2 Pirate
PINGER = "t_bpd_pinger"  # Pirate: "{T}: 1 damage to each opponent"
SELF_PINGER = "t_bpd_self_pinger"  # Pirate: "{T}: 1 damage to you"
BEAR = "t_bear"  # 2/2, not a Pirate
START = 40  # the sandbox's starting life


def charges(game, oid: int) -> int:
    return game.state.objects[oid].counter("charge")


def settle(game) -> None:
    game._advance()
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def board(builder, watcher: str, creatures: list[str], *, players: int = 4):
    """``watcher`` and ``creatures`` on player 0's side, frozen in a main phase."""
    game = (
        builder(players=players)
        .battlefield(0, [watcher, *creatures])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    return game, only_oid(game, watcher, 0)


def ping(game, source: int, *specs) -> None:
    """Run ``specs`` as an effect of ``source``'s, the way its ability resolves."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    for _ in execute(ctx, list(specs)):
        raise AssertionError("these effects ask nothing")


def damage(player) -> dict:
    return {"op": "damage", "player": player, "amount": {"const": 1}}


def swing(builder, watcher: str, attackers: list[tuple[str, int]], *, players: int = 4):
    """Player 0 attacks with each ``(card, defending seat)``; nobody blocks."""
    game = (
        builder(players=players)
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
    def test_two_pirates_on_one_opponent_trigger_once(self, builder):
        game, oid = swing(builder, TALLY, [(PIRATE, 1), (PIRATE, 1)])
        assert charges(game, oid) == 1
        assert game.state.players[1].life == START - 4 - 1

    def test_without_batched_the_same_swing_triggers_twice(self, builder):
        game, oid = swing(builder, GREEDY, [(PIRATE, 1), (PIRATE, 1)])
        assert charges(game, oid) == 2

    def test_each_damaged_opponent_is_named_once(self, builder):
        """Three Pirates across two opponents: one firing, two seats."""
        game, oid = swing(builder, TALLY, [(PIRATE, 1), (PIRATE, 1), (PIRATE, 2)])
        assert charges(game, oid) == 2
        assert game.state.players[1].life == START - 4 - 1
        assert game.state.players[2].life == START - 2 - 1
        assert game.state.players[3].life == START

    def test_a_non_pirate_beside_them_is_not_one_of_them(self, builder):
        """The bear's opponent was dealt damage, but not by a Pirate."""
        game, oid = swing(builder, TALLY, [(PIRATE, 1), (BEAR, 2)])
        assert charges(game, oid) == 1
        assert game.state.players[2].life == START - 2


class TestNoncombatDamageCounts:
    def test_one_op_hitting_every_opponent_triggers_once_naming_all(self, builder):
        game, oid = board(builder, TALLY, [PINGER])
        ping(game, only_oid(game, PINGER, 0), damage("each_opponent"))
        assert len(game.state.pending_triggers) == 1
        assert game.state.pending_triggers[0].bindings["damaged_players"] == [1, 2, 3]
        settle(game)
        assert charges(game, oid) == 3
        assert all(p.life == START - 2 for p in game.state.players[1:])

    def test_without_batched_it_triggers_per_opponent(self, builder):
        game, oid = board(builder, GREEDY, [PINGER])
        ping(game, only_oid(game, PINGER, 0), damage("each_opponent"))
        settle(game)
        assert charges(game, oid) == 3

    def test_two_separate_pings_trigger_twice(self, builder):
        game, oid = board(builder, TALLY, [PINGER])
        pinger = only_oid(game, PINGER, 0)
        ping(game, pinger, damage(1), damage(1))
        settle(game)
        assert charges(game, oid) == 2

    def test_a_non_pirate_source_fires_nothing(self, builder):
        game, oid = board(builder, TALLY, [BEAR])
        ping(game, only_oid(game, BEAR, 0), damage("each_opponent"))
        settle(game)
        assert charges(game, oid) == 0


class TestWhoWasHit:
    def test_a_pirate_hitting_you_is_not_your_opponents(self, builder):
        game, oid = board(builder, TALLY, [SELF_PINGER])
        ping(game, only_oid(game, SELF_PINGER, 0), damage("you"))
        settle(game)
        assert charges(game, oid) == 0

    def test_your_hit_beside_theirs_does_not_spend_the_batch(self, builder):
        """"Each player": seat 0 is hit first and is not an opponent."""
        game, oid = board(builder, TALLY, [PINGER])
        ping(game, only_oid(game, PINGER, 0), damage("each_player"))
        settle(game)
        assert charges(game, oid) == 3
        assert game.state.players[0].life == START - 1


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
    def test_batched_loads_on_deals_damage_to_player(self):
        card = compile_card(
            _model(
                {
                    "event": "deals_damage_to_player",
                    "controller": "you",
                    "filter": {"subtypes": ["Pirate"]},
                    "batched": True,
                }
            )
        )
        assert card.abilities[0].trigger.batched

    def test_batched_is_still_refused_on_deals_combat_damage_to_player(self):
        with pytest.raises(DslError, match="batched"):
            compile_card(_model({"event": "deals_combat_damage_to_player", "batched": True}))
