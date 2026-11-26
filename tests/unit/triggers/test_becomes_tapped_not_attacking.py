""""Whenever a creature an opponent controls becomes tapped, **if it isn't being
declared as an attacker**, …" -- Verity Circle, Rhoda, Geist Avenger.

Rule 508.1f makes tapping a non-vigilant attacker part of declaring it, and that
tap goes through `primitives.tap_permanent` like every other, so a bare
`becomes_tapped` trigger cannot tell it from a tapper's tap, a tap cost or a
mana ability. Written without the clause, Verity Circle draws whenever an
opponent attacks, which is a much larger card than the printed one.

`combat` is the only caller that passes ``attack_declaration=True``, every
TAPPED event carries the flag, and `TriggerSpec.attack_declaration` compares
against it. An intervening-if on the step is the other near miss: a creature
tapped by an ability during the declare attackers step is not being declared as
an attacker, and must still fire the trigger.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import tap_permanent
from tests.conftest import attack_with, find_action, pass_until

WATCHER = "t_vc_watcher"  # attack_declaration: false
WIDE = "t_vc_wide_watcher"  # the near miss: no clause
ONLY_ATTACK = "t_vc_only_attack_watcher"  # attack_declaration: true
BEAR = "t_bear"  # 2/2
VIGILANT = "t_vigilant"  # 2/2 vigilance


def draws(game, watcher: str) -> int:
    """How many times the watcher's ability resolved, counted off the log."""
    return sum(
        1
        for e in game.state.events
        if e.type is EventType.ABILITY_RESOLVED and e.data.get("card") == watcher
    )


def position(builder, watcher: str, attackers=(BEAR,)):
    """Player 0, active, has ``attackers``; player 1 has the watcher.

    Returns ``(game, oids)``, ``oids`` being player 0's creatures in order.
    """
    game = (
        builder(players=2)
        .battlefield(0, list(attackers))
        .battlefield(1, [watcher])
        .library(0, ["mountain"] * 10)
        .library(1, ["island"] * 10)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    mine = sorted(o.oid for o in game.state.battlefield_objects(0))
    return game, mine


def declare(game, *attackers: int) -> None:
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid in attackers:
        attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def settled_in_declare_attackers(game) -> None:
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and g.state.step >= Step.DECLARE_ATTACKERS,
    )


class TestTheDeclarationsTapIsNotOne:
    def test_an_attacker_tapping_draws_nothing(self, builder):
        game, (bear,) = position(builder, WATCHER)
        declare(game, bear)
        settled_in_declare_attackers(game)
        assert game.state.objects[bear].tapped
        assert draws(game, WATCHER) == 0

    def test_the_near_miss_draws_off_the_attack(self, builder):
        """Without the clause the trigger hears the declaration -- the reason
        the clause exists."""
        game, (bear,) = position(builder, WIDE)
        declare(game, bear)
        settled_in_declare_attackers(game)
        assert draws(game, WIDE) == 1

    def test_true_keeps_the_declarations_tap_alone(self, builder):
        game, (bear,) = position(builder, ONLY_ATTACK)
        declare(game, bear)
        settled_in_declare_attackers(game)
        assert draws(game, ONLY_ATTACK) == 1

    def test_a_vigilant_attacker_never_taps(self, builder):
        game, (vigilant,) = position(builder, ONLY_ATTACK, attackers=(VIGILANT,))
        declare(game, vigilant)
        settled_in_declare_attackers(game)
        assert draws(game, ONLY_ATTACK) == 0


class TestEveryOtherTapIsOne:
    def test_a_tap_in_the_main_phase_draws(self, builder):
        game, (bear,) = position(builder, WATCHER)
        tap_permanent(game.state, bear)
        game._advance()
        settled_in_declare_attackers(game)
        assert draws(game, WATCHER) == 1

    def test_a_tap_during_the_declare_attackers_step_still_draws(self, builder):
        """The boundary `step_is` would get wrong: a creature tapped by
        something else while attackers are being declared is not being declared
        as an attacker. The other Bear is tapped while the declaration is
        open, and the attacking one by the declaration itself: one draw."""
        game, (bear, other) = position(builder, WATCHER, attackers=(BEAR, BEAR))
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        assert game.state.step is Step.DECLARE_ATTACKERS
        tap_permanent(game.state, other)
        attack_with(game, bear)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        settled_in_declare_attackers(game)
        assert game.state.objects[bear].tapped
        assert draws(game, WATCHER) == 1

    def test_true_ignores_it(self, builder):
        game, (bear,) = position(builder, ONLY_ATTACK)
        tap_permanent(game.state, bear)
        game._advance()
        settled_in_declare_attackers(game)
        assert draws(game, ONLY_ATTACK) == 0


class TestTheEventSaysWhichTap:
    def test_every_tapped_event_carries_the_flag(self, builder):
        game, (bear, other) = position(builder, WATCHER, attackers=(BEAR, BEAR))
        tap_permanent(game.state, other)
        declare(game, bear)
        flags = {
            e.data["oid"]: e.data["attack_declaration"]
            for e in game.state.events
            if e.type is EventType.TAPPED
        }
        assert flags == {other: False, bear: True}


class TestTheLoader:
    @staticmethod
    def card(trigger: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "oracle_text": "",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "x",
                        "trigger": trigger,
                        "effects": [{"op": "draw", "amount": {"const": 1}}],
                    }
                ],
            }
        )

    def test_it_is_refused_off_becomes_tapped(self):
        with pytest.raises(DslError, match="attack_declaration"):
            compile_card(self.card({"event": "attacks", "attack_declaration": False}))

    def test_it_loads_on_becomes_tapped(self):
        card = compile_card(self.card({"event": "becomes_tapped", "attack_declaration": False}))
        assert card.abilities[0].trigger.attack_declaration is False

    def test_it_reaches_the_watcher(self, registry):
        assert registry.get(WATCHER).abilities[0].trigger.attack_declaration is False
