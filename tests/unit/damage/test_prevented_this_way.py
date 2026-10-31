""""If damage is prevented **this way**…" -- the 615.5 rider on the
`prevent_damage` op's shield, written as its ``effects``.

615.5: a prevention effect may include an additional effect that refers to the
amount of damage prevented, and that additional effect happens immediately
after the prevention. Inkshield is the witness: "Prevent all combat damage that
would be dealt to you this turn. For each 1 damage prevented this way, create a
2/1 white and black Inkling creature token with flying."

The `damage_prevented` trigger is the near miss and is wrong twice. A
`delayed_trigger` on it watches *every* prevention of damage to you, so a Fog,
a Selfless Squire's shield or protection would make Inklings too; and nothing
tied the event to the shield the spell made. So each linked shield carries a
fresh `DamageShield.link`, `damage_player` puts it on the `DAMAGE_PREVENTED` it
fires as ``shield``, and the rider is a delayed ability scoped to that link.

What is pinned below:

1. Each prevention by the shield runs the rider once, with the prevented amount
   as ``{"binding": "amount"}`` -- a real attack, and two hits adding up.
2. Only *this* shield: an unlinked shield preventing the same damage pays
   nothing, a combat-only shield letting burn through pays nothing, and two
   riders over one seat make one set of tokens (one shield prevents, 615.1).
3. A linked shield is preferred over an unlinked one, the order the protected
   player would pick (616.1).
4. Cleanup ends the shield and the rider together.
5. The loader refuses an empty rider, a target inside it, and a rider on
   `prevent_damage_permanent`, where it would never run.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_player
from commanderblitz.engine.triggers import run_armed_delays
from tests.conftest import (
    attack_with,
    count_on_battlefield,
    find_action,
    only_oid,
    pass_until,
    two_seat_board,
)

BEAR = "t_bear"
INKLING = "inkling_2_1_wb_flying"

#: Inkshield's spell effect, as the card writes it.
INKSHIELD = {
    "op": "prevent_damage",
    "player": "you",
    "duration": "this_turn",
    "combat_only": True,
    "effects": [
        {"op": "create_token", "token": INKLING, "amount": {"binding": "amount"}}
    ],
}


def position(builder):
    """A bear each, in player 0's precombat main phase. Returns ``(game, mine)``."""
    game = two_seat_board(builder, mine=[BEAR], theirs=[BEAR], advance=False)
    return game, only_oid(game, BEAR, 0)


def run(game, spec: dict, controller: int = 1) -> None:
    """Resolve ``spec`` for ``controller``; the op asks nothing."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    for _ in execute_one(ctx, spec):  # pragma: no cover - it asks nothing
        raise AssertionError(f"{spec['op']} asked a decision")


def hit(game, amount: int, dealer: int, *, pid: int = 1, is_combat: bool = True) -> int:
    """Deal damage to ``pid`` and resolve whatever delayed ability it armed."""
    dealt = damage_player(game.state, pid, amount, dealer, is_combat=is_combat)
    for _ in run_armed_delays(game.state):  # pragma: no cover - the rider asks nothing
        raise AssertionError("the rider asked a decision")
    return dealt


def inklings(game, pid: int = 1) -> int:
    return count_on_battlefield(game, INKLING, pid)


class TestTheRiderPaysPerPrevention:
    def test_the_prevented_amount_reaches_the_rider(self, builder):
        game, mine = position(builder)
        run(game, INKSHIELD)

        assert hit(game, 3, mine) == 0
        assert inklings(game) == 3

    def test_each_prevention_runs_it_again(self, builder):
        game, mine = position(builder)
        run(game, INKSHIELD)

        hit(game, 2, mine)
        hit(game, 1, mine)

        assert inklings(game) == 3

    def test_a_real_attack_makes_inklings_for_the_defender(self, builder):
        game = builder().battlefield(0, [BEAR]).build()
        mine = only_oid(game, BEAR, 0)
        run(game, INKSHIELD)
        life = game.state.players[1].life
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        attack_with(game, mine)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: int(g.state.step) > int(Step.COMBAT_DAMAGE))

        assert game.state.players[1].life == life
        assert inklings(game, 1) == 2
        assert inklings(game, 0) == 0

    def test_the_event_names_the_shield(self, builder):
        game, mine = position(builder)
        run(game, INKSHIELD)

        hit(game, 2, mine)

        (shield,) = game.state.damage_shields
        events = [e for e in game.state.events if e.type == "damage_prevented"]
        assert [e.data.get("shield") for e in events] == [shield.link]


class TestOnlyThisShield:
    def test_another_prevention_pays_nothing(self, builder):
        game, mine = position(builder)
        run(game, {"op": "prevent_damage", "player": "you", "duration": "this_turn"})
        run(game, {"op": "delayed_trigger", "trigger": {"event": "damage_prevented"},
                   "effects": [{"op": "gain_life", "player": "you", "amount": 1}]},
            controller=0)

        hit(game, 2, mine)

        assert inklings(game) == 0

    def test_burn_through_a_combat_only_shield_pays_nothing(self, builder):
        game, mine = position(builder)
        run(game, INKSHIELD)
        life = game.state.players[1].life

        hit(game, 2, mine, is_combat=False)

        assert game.state.players[1].life == life - 2
        assert inklings(game) == 0

    def test_the_other_seat_pays_nothing(self, builder):
        game, _ = position(builder)
        theirs = only_oid(game, BEAR, 1)
        run(game, INKSHIELD)

        hit(game, 2, theirs, pid=0)

        assert inklings(game, 0) == 0
        assert inklings(game, 1) == 0

    def test_two_riders_over_one_seat_pay_once(self, builder):
        game, mine = position(builder)
        run(game, INKSHIELD)
        run(game, INKSHIELD)

        hit(game, 2, mine)

        assert len(game.state.damage_shields) == 2
        assert inklings(game) == 2


class TestTheLinkedShieldPreventsFirst:
    def test_a_plain_shield_installed_earlier_does_not_swallow_it(self, builder):
        game, mine = position(builder)
        run(game, {"op": "prevent_damage", "player": "you", "duration": "this_turn"})
        run(game, INKSHIELD)

        hit(game, 2, mine)

        assert inklings(game) == 2


class TestItWearsOff:
    def test_cleanup_ends_the_shield_and_the_rider(self, builder):
        game = builder().battlefield(0, [BEAR]).build()
        run(game, INKSHIELD)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert game.state.damage_shields == []
        assert [d for d in game.state.delayed_triggers if d.shield is not None] == []


class TestTheLoader:
    def _card(self, effect: dict, targets: list | None = None) -> CardModel:
        data = {"id": "t_this_way_probe", "name": "This Way Probe", "mana_cost": "{W}",
                "types": ["Instant"], "spell_effects": [effect]}
        if targets:
            data["targets"] = targets
        return CardModel.model_validate(data)

    def test_the_rider_loads(self):
        compile_card(self._card(INKSHIELD))

    def test_an_empty_rider_is_refused(self):
        with pytest.raises(DslError, match="non-empty"):
            compile_card(self._card(INKSHIELD | {"effects": []}))

    def test_a_target_inside_the_rider_is_refused(self):
        effect = INKSHIELD | {"effects": [
            {"op": "damage", "amount": {"binding": "amount"}, "objects": {"target": "t1"}}
        ]}
        with pytest.raises(DslError, match="inside a delay"):
            compile_card(self._card(effect, [{"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}]))

    def test_a_rider_on_the_permanent_shield_is_refused(self):
        effect = {"op": "prevent_damage_permanent", "objects": {"self_only": True},
                  "dealt": "to", "duration": "this_turn",
                  "effects": INKSHIELD["effects"]}
        with pytest.raises(DslError, match="player shield only"):
            compile_card(self._card(effect))
