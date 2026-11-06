""""If damage would be dealt to that creature this turn, prevent that damage
and put that many +1/+1 counters on it" -- the 615.5 rider on the
`prevent_damage_permanent` op's shield, written as its ``effects``.

615.5: a prevention effect may include an additional effect that refers to the
amount of damage prevented, and it happens immediately after the prevention.
Gatta and Luzzu is the witness. Without the rider the card is either a plain
Gideon-style shield (no counters, a weaker card) or a `damage_prevented`
delayed trigger, which watches only the *player* half of the event and every
prevention whatever made it -- so a Fog-like shield elsewhere would pay too.

So each linked `PermanentShield` carries a fresh `link`, `damage_permanent`
(and `damage_player`, for a ``by`` shield) puts it on the `DAMAGE_PREVENTED` it
fires as ``shield``, and the rider is a delayed ability scoped to that link,
with the shielded permanent bound as ``shielded``.

What is pinned below:

1. Each prevention runs the rider once, with the prevented amount, and the
   counters land on the shielded creature -- through a real combat too.
2. Only this shield: damage to another creature, a plain shield on the same
   creature, and burn through a combat-only shield pay nothing.
3. Cleanup ends the shield and the rider together; a creature that left in
   response gets neither.
4. The loader takes the rider, and refuses an empty one, a target inside it,
   and one on a shield that outlives the turn.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.triggers import run_armed_delays
from commanderblitz.engine.zones import move_object
from tests.conftest import (
    attack_with,
    find_action,
    only_oid,
    pass_until,
    two_seat_board,
)

BEAR = "t_bear"

RIDER = [
    {
        "op": "add_counters",
        "objects": {"binding": "shielded"},
        "counter": "+1/+1",
        "amount": {"binding": "amount"},
    }
]


def gatta(**extra) -> dict:
    """Gatta and Luzzu's shield, aimed at whatever `run` binds as ``aimed``."""
    return {
        "op": "prevent_damage_permanent",
        "objects": {"binding": "aimed"},
        "dealt": "to",
        "duration": "this_turn",
        "effects": RIDER,
    } | extra


def position(builder):
    """A bear each, player 0's precombat main. Returns ``(game, mine, theirs)``."""
    game = two_seat_board(builder, mine=[BEAR], theirs=[BEAR], advance=False)
    return game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)


def run(game, spec: dict, oid: int, controller: int = 0) -> None:
    """Resolve ``spec`` for ``controller`` with ``oid`` bound as ``aimed``."""
    ctx = EffectContext(
        state=game.state, controller=controller, source_oid=None, bindings={"aimed": oid}
    )
    for _ in execute_one(ctx, spec):  # pragma: no cover - it asks nothing
        raise AssertionError(f"{spec['op']} asked a decision")


def hit(game, oid: int, amount: int, dealer: int, *, is_combat: bool = False) -> int:
    dealt = damage_permanent(game.state, oid, amount, dealer, is_combat=is_combat)
    for _ in run_armed_delays(game.state):  # pragma: no cover - the rider asks nothing
        raise AssertionError("the rider asked a decision")
    return dealt


def plus(game, oid: int) -> int:
    return game.state.objects[oid].counters.get("+1/+1", 0)


class TestTheRiderPaysPerPrevention:
    def test_the_prevented_damage_becomes_counters(self, builder):
        game, mine, theirs = position(builder)
        run(game, gatta(), mine)

        assert hit(game, mine, 3, theirs) == 0
        assert game.state.objects[mine].damage == 0
        assert plus(game, mine) == 3

    def test_each_prevention_runs_it_again(self, builder):
        game, mine, theirs = position(builder)
        run(game, gatta(), mine)

        hit(game, mine, 2, theirs)
        hit(game, mine, 1, theirs)

        assert plus(game, mine) == 3

    def test_the_event_names_the_shield(self, builder):
        game, mine, theirs = position(builder)
        run(game, gatta(), mine)

        hit(game, mine, 2, theirs)

        (shield,) = game.state.objects[mine].damage_shields
        events = [e for e in game.state.events if e.type == "damage_prevented"]
        assert [e.data.get("shield") for e in events] == [shield.link]

    def test_a_blocked_attacker_grows_from_the_block(self, builder):
        game = builder().battlefield(0, [BEAR]).battlefield(1, [BEAR]).build()
        mine, theirs = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        run(game, gatta(), mine)
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        attack_with(game, mine)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)
        game.apply(
            find_action(game, ActionKind.ADD_BLOCKER, source=theirs, targets=(TargetRef.obj(mine),))
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: int(g.state.step) > int(Step.COMBAT_DAMAGE))

        assert game.state.objects[mine].on_battlefield
        assert plus(game, mine) == 2


class TestOnlyThisShield:
    def test_damage_to_another_creature_pays_nothing(self, builder):
        game, mine, theirs = position(builder)
        run(game, gatta(), mine)

        hit(game, theirs, 1, mine)

        assert plus(game, mine) == 0
        assert plus(game, theirs) == 0

    def test_a_plain_shield_pays_nothing(self, builder):
        game, mine, theirs = position(builder)
        plain = gatta()
        del plain["effects"]
        run(game, plain, mine)

        hit(game, mine, 2, theirs)

        assert plus(game, mine) == 0

    def test_the_linked_shield_prevents_ahead_of_a_plain_one(self, builder):
        game, mine, theirs = position(builder)
        plain = gatta()
        del plain["effects"]
        run(game, plain, mine)
        run(game, gatta(), mine)

        hit(game, mine, 2, theirs)

        assert plus(game, mine) == 2

    def test_burn_through_a_combat_only_shield_pays_nothing(self, builder):
        game, mine, theirs = position(builder)
        run(game, gatta(combat_only=True), mine)

        hit(game, mine, 1, theirs, is_combat=False)

        assert game.state.objects[mine].damage == 1
        assert plus(game, mine) == 0


class TestItWearsOff:
    def test_cleanup_ends_the_shield_and_the_rider(self, builder):
        game = builder().battlefield(0, [BEAR]).build()
        mine = only_oid(game, BEAR, 0)
        run(game, gatta(), mine)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        assert game.state.objects[mine].damage_shields == []
        assert [d for d in game.state.delayed_triggers if d.shield is not None] == []

    def test_a_creature_that_left_gets_no_rider(self, builder):
        game, mine, _ = position(builder)
        move_object(game.state, mine, Zone.GRAVEYARD)
        run(game, gatta(), mine)

        assert [d for d in game.state.delayed_triggers if d.shield is not None] == []


class TestTheLoader:
    def _card(self, effect: dict, targets: list | None = None) -> CardModel:
        data = {"id": "t_this_way_permanent_probe", "name": "This Way Permanent Probe",
                "mana_cost": "{W}", "types": ["Instant"], "spell_effects": [effect],
                "targets": targets or [
                    {"id": "t1", "kind": "permanent", "selector": {"types": ["Creature"]}}
                ]}
        return CardModel.model_validate(data)

    def _effect(self, **extra) -> dict:
        return {"op": "prevent_damage_permanent", "objects": {"target": "t1"},
                "dealt": "to", "duration": "this_turn", "effects": RIDER} | extra

    def test_the_rider_loads(self):
        compile_card(self._card(self._effect()))

    def test_an_empty_rider_is_refused(self):
        with pytest.raises(DslError, match="non-empty"):
            compile_card(self._card(self._effect(effects=[])))

    def test_a_target_inside_the_rider_is_refused(self):
        rider = [RIDER[0] | {"objects": {"target": "t1"}}]
        with pytest.raises(DslError, match="inside a delay"):
            compile_card(self._card(self._effect(effects=rider)))

    def test_a_rider_on_a_longer_shield_is_refused(self):
        with pytest.raises(DslError, match="this_turn"):
            compile_card(self._card(self._effect(duration="until_your_next_turn")))
