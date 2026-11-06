"""Damage dealt to a permanent as one simultaneous event, and summed.

    "Whenever Hercules is dealt damage **for the first time each turn**, put
    **that many** +1/+1 counters on him. (He must survive the damage to get
    the counters.)"                         -- Hercules, Olympian Hero

`dealt_damage` fires one `DAMAGE_DEALT` per source and recipient, so with
`max_per_turn: 1` alone a Hercules blocked by two creatures keeps only the
first blocker's event and "that many" reads one blocker's damage. 510.2 says
otherwise: every creature's combat damage in a step is dealt at once, so
Hercules is dealt damage once, for all of it. ``batched`` on `dealt_damage`
groups by the ``batch`` `primitives.damage_permanent` now puts on the event --
the combat damage step (`combat.deal_combat_damage`), or the effect op -- and
every later event of the group adds its damage to the queued firing's
``amount`` (`triggers._joins_batched_damage`).

What each reading rests on, and each has a test class:

- **One step, one event, the total.** Blocked by two 2/2s, Hercules triggers
  once and gets four counters. The near miss without ``batched`` gets two.
- **First strike is its own step** (510.4). A first-striking blocker's damage
  is the first time this turn; the regular step's damage that follows is a
  second event and fires nothing. Uncapped, the same line fires once per step.
- **He must survive.** Lethal damage still triggers it (the event happened),
  but state-based actions put him in the graveyard first, and the trigger
  resolving finds nothing on the battlefield to put counters on; the card in
  the graveyard is a new object (400.7) and gets none.
- **Noncombat damage counts.** A bolt is one damage event from one op, and is
  the first time as much as a combat step is. A second bolt the same turn is a
  second event and does not trigger; the next turn it does again.
- **The loader** accepts ``batched`` on `dealt_damage` and still refuses it on
  a damage event that carries no batch.

Hercules, Olympian Hero is the witness; `t_ddb_hero` in
`tests/data/dealt_damage_batched.cards.json` is his second ability on a {G}
2/5, `t_ddb_grower` the same line without the cap, and `t_ddb_near_miss` the
same line without ``batched``.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from tests.conftest import attack_with, find_action, only_oid, pass_until, plus_one_counters

HERO = "t_ddb_hero"  # 2/5: first time each turn it's dealt damage, that many +1/+1
GROWER = "t_ddb_grower"  # 2/5: the same line with no per-turn cap
NEAR_MISS = "t_ddb_near_miss"  # t_ddb_hero without `batched`
BEAR = "t_bear"  # 2/2
FIRST_STRIKER = "t_first_striker"  # 2/2 first strike
BOLT = "t_bolt"  # {R} instant, 3 damage to any target


def triggered(game, oid: int) -> int:
    """How many times ``oid``'s abilities have triggered this game."""
    return sum(
        1
        for e in game.state.events
        if e.type == EventType.ABILITY_TRIGGERED and e.source == oid
    )


def blocked_by(builder, card: str, blockers: list[str]):
    """``card`` attacks player 1, who blocks it with every one of ``blockers``.

    Returns ``(game, oid)`` with combat over and every trigger resolved.
    """
    game = (
        builder(players=2)
        .battlefield(0, [card])
        .battlefield(1, list(blockers))
        .active(0)
        .build()
    )
    oid = only_oid(game, card, 0)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    for blocker in game.state.battlefield_objects(1):
        game.apply(
            find_action(
                game, ActionKind.ADD_BLOCKER, source=blocker.oid, targets=(TargetRef.obj(oid),)
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    past_combat(game)
    return game, oid


def past_combat(game) -> None:
    pass_until(
        game,
        lambda g: g.state.step >= Step.END_OF_COMBAT
        and not g.state.stack
        and not g.state.pending_triggers,
    )


def burn_position(builder, card: str = HERO, *, bolts: int = 2):
    """``card`` on player 0's side; player 1 holds ``bolts`` and the mana."""
    game = (
        builder(players=2)
        .battlefield(0, [card])
        .battlefield(1, ["mountain"] * bolts)
        .hand(1, [BOLT] * bolts)
        .active(0)
        .build()
    )
    return game, only_oid(game, card, 0)


def bolt(game, oid: int) -> None:
    """Player 1 bolts ``oid`` at the first chance, and it resolves."""

    def offer(g):
        return next(
            (
                a
                for a in g.legal_actions()
                if a.kind is ActionKind.CAST
                and g.state.objects[a.source].def_id == BOLT
                and any(ref.id == oid for ref in a.targets)
            ),
            None,
        )

    pass_until(game, lambda g: offer(g) is not None)
    game.apply(offer(game))
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


class TestOneCombatDamageStepIsOneEvent:
    def test_two_blockers_trigger_it_once_for_the_total(self, builder):
        game, oid = blocked_by(builder, HERO, [BEAR, BEAR])
        assert triggered(game, oid) == 1, "510.2: one step's damage is one event"
        assert plus_one_counters(game, oid) == 4, "that many: both blockers' damage"

    def test_one_blocker_is_its_damage(self, builder):
        game, oid = blocked_by(builder, HERO, [BEAR])
        assert plus_one_counters(game, oid) == 2

    def test_without_batched_it_reads_one_source(self, builder):
        """The near miss: `max_per_turn: 1` keeps the first blocker's event and
        throws the second away, so it is a different (weaker) card."""
        game, oid = blocked_by(builder, NEAR_MISS, [BEAR, BEAR])
        assert plus_one_counters(game, oid) == 2


class TestFirstStrikeIsItsOwnStep:
    def test_the_first_strike_step_is_the_first_time(self, builder):
        """510.4: the first-strike step deals its damage, then the regular step
        deals the rest as a second event. Only the first is "the first time"."""
        game, oid = blocked_by(builder, HERO, [FIRST_STRIKER, BEAR])
        assert triggered(game, oid) == 1
        assert plus_one_counters(game, oid) == 2, "the first striker's two, not four"

    def test_uncapped_it_fires_once_per_step(self, builder):
        game, oid = blocked_by(builder, GROWER, [FIRST_STRIKER, BEAR])
        assert triggered(game, oid) == 2
        assert plus_one_counters(game, oid) == 4


class TestHeMustSurvive:
    def test_lethal_damage_triggers_but_puts_no_counters(self, builder):
        """Three 2/2s deal six to a 2/5. The trigger fires (the damage was dealt)
        and resolves with him already in the graveyard: no counters anywhere."""
        game, oid = blocked_by(builder, HERO, [BEAR, BEAR, BEAR])
        assert triggered(game, oid) == 1
        assert oid not in game.state.battlefield
        (card,) = [
            game.state.objects[o]
            for o in game.state.players[0].graveyard
            if game.state.objects[o].def_id == HERO
        ]
        assert card.zone is Zone.GRAVEYARD
        assert card.counter("+1/+1") == 0


class TestNoncombatDamage:
    def test_a_bolt_is_the_first_time(self, builder):
        game, oid = burn_position(builder, bolts=1)
        bolt(game, oid)
        assert plus_one_counters(game, oid) == 3

    def test_a_second_damage_event_the_same_turn_does_not_trigger(self, builder):
        game, oid = burn_position(builder)
        bolt(game, oid)
        bolt(game, oid)
        assert triggered(game, oid) == 1
        assert plus_one_counters(game, oid) == 3

    def test_two_bolts_are_two_events_uncapped(self, builder):
        """Two spells are two damage events, not one batch: each is its own op."""
        game, oid = burn_position(builder, GROWER)
        bolt(game, oid)
        bolt(game, oid)
        assert triggered(game, oid) == 2
        assert plus_one_counters(game, oid) == 6

    def test_the_next_turn_is_a_first_time_again(self, builder):
        game, oid = burn_position(builder)
        bolt(game, oid)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)
        bolt(game, oid)
        assert triggered(game, oid) == 2
        assert plus_one_counters(game, oid) == 6


def _card(trigger: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": trigger,
                    "effects": [{"op": "noop"}],
                }
            ],
        }
    )


class TestTheLoader:
    def test_batched_dealt_damage_loads(self, registry):
        (ability,) = [a for a in registry.get(HERO).abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.batched and ability.trigger.max_per_turn == 1

    def test_batched_is_still_refused_on_player_damage(self):
        with pytest.raises(DslError, match="batched"):
            compile_card(
                _card({"event": "deals_damage_to_player", "source": "self", "batched": True})
            )
