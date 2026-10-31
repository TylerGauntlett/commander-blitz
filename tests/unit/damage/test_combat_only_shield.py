""""Prevent all **combat** damage that would be dealt to you this turn" -- the
one-shot shields narrowed to combat damage, `combat_only` on the
`prevent_damage` and `prevent_damage_permanent` ops.

615.1 with 510.2: a prevention effect answers the damage it names, and combat
damage is the damage combat deals in the combat damage step, nothing else. Druid's
Deliverance and Defend the Hearth print the player form; Fleeting Flight ("…to
it this turn") and Azorius Ploy ("…target creature would deal this turn") the
permanent forms. Inkshield prints the player form too, and waits only on reading
back how much was prevented.

Without the flag, the nearest shields prevent ALL damage: written with them,
each of these cards also stops burn, drain and a fight, which is a strictly
better card that loads clean. The `prevent_damage` *static* has `combat_only`
but lives on a printed permanent and has no "this turn", and
`prevent_combat_damage` is keyed to the dealer rather than to who is hit, so
it would fog the whole table's combat.

What is pinned below:

1. Combat damage to the shielded seat or permanent is prevented, and fires
   `DAMAGE_PREVENTED` like the total shield.
2. Noncombat damage is not: it lands in full.
3. The unnarrowed shields still stop both (the default is unchanged).
4. Cleanup ends it.
5. The loader takes `combat_only` only as a boolean.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import damage_permanent, damage_player
from commanderblitz.engine.temp_effects import clear_damage_shields, clear_permanent_shields
from tests.conftest import attack_with, find_action, only_oid, pass_until, two_seat_board

BEAR = "t_bear"


def position(builder):
    """A bear each, in player 0's precombat main phase. Returns ``(game, mine, theirs)``."""
    game = two_seat_board(builder, mine=[BEAR], theirs=[BEAR], advance=False)
    return game, only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)


def run(game, spec: dict, controller: int = 1, **bindings) -> None:
    """Resolve ``spec`` for ``controller``; neither op asks anything."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    ctx.bindings.update(bindings)
    for _ in execute_one(ctx, spec):  # pragma: no cover - it asks nothing
        raise AssertionError(f"{spec['op']} asked a decision")


def fog_player(game, pid: int = 1, *, combat_only: bool = True) -> None:
    spec = {"op": "prevent_damage", "player": "you", "duration": "this_turn"}
    if combat_only:
        spec["combat_only"] = True
    run(game, spec, controller=pid)


def fog_permanent(game, oid: int, dealt: str = "to", *, combat_only: bool = True) -> None:
    spec = {"op": "prevent_damage_permanent", "objects": {"binding": "shielded"},
            "dealt": dealt, "duration": "this_turn"}
    if combat_only:
        spec["combat_only"] = True
    run(game, spec, shielded=[oid])


def prevented(game) -> list:
    return [e for e in game.state.events if e.type == "damage_prevented"]


class TestThePlayerShieldStopsCombatDamage:
    def test_combat_damage_to_the_shielded_seat_is_prevented(self, builder):
        game, mine, _ = position(builder)
        fog_player(game)
        life = game.state.players[1].life

        assert damage_player(game.state, 1, 2, mine, is_combat=True) == 0
        assert game.state.players[1].life == life

    def test_it_fires_damage_prevented(self, builder):
        game, mine, _ = position(builder)
        fog_player(game)

        damage_player(game.state, 1, 2, mine, is_combat=True)

        assert [(e.data.get("amount"), e.data.get("to")) for e in prevented(game)] == [
            (2, "player")
        ]

    def test_a_real_attack_deals_nothing(self, builder):
        game = builder().battlefield(0, [BEAR]).build()
        mine = only_oid(game, BEAR, 0)
        fog_player(game)
        life = game.state.players[1].life
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        attack_with(game, mine)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: int(g.state.step) > int(Step.COMBAT_DAMAGE))

        assert game.state.players[1].life == life

    def test_the_other_seat_is_not_shielded(self, builder):
        game, _, theirs = position(builder)
        fog_player(game)
        life = game.state.players[0].life

        damage_player(game.state, 0, 2, theirs, is_combat=True)

        assert game.state.players[0].life == life - 2


class TestThePlayerShieldLetsNoncombatDamageThrough:
    def test_burn_lands(self, builder):
        game, mine, _ = position(builder)
        fog_player(game)
        life = game.state.players[1].life

        damage_player(game.state, 1, 3, mine, is_combat=False)

        assert game.state.players[1].life == life - 3
        assert prevented(game) == []

    def test_the_total_shield_still_stops_burn(self, builder):
        game, mine, _ = position(builder)
        fog_player(game, combat_only=False)
        life = game.state.players[1].life

        damage_player(game.state, 1, 3, mine, is_combat=False)

        assert game.state.players[1].life == life

    def test_both_shields_are_kept_side_by_side(self, builder):
        game, _, _ = position(builder)
        fog_player(game)
        fog_player(game, combat_only=False)

        assert sorted(s.combat_only for s in game.state.damage_shields) == [False, True]


class TestThePermanentShield:
    def test_combat_damage_to_it_is_prevented(self, builder):
        game, mine, theirs = position(builder)
        fog_permanent(game, theirs)

        damage_permanent(game.state, theirs, 2, mine, is_combat=True)

        assert game.state.objects[theirs].damage == 0

    def test_noncombat_damage_to_it_lands(self, builder):
        game, mine, theirs = position(builder)
        fog_permanent(game, theirs)

        damage_permanent(game.state, theirs, 1, mine, is_combat=False)

        assert game.state.objects[theirs].damage == 1

    def test_by_stops_the_combat_damage_it_deals(self, builder):
        game, mine, theirs = position(builder)
        fog_permanent(game, theirs, dealt="by")
        life = game.state.players[0].life

        damage_player(game.state, 0, 2, theirs, is_combat=True)
        damage_permanent(game.state, mine, 2, theirs, is_combat=True)

        assert game.state.players[0].life == life
        assert game.state.objects[mine].damage == 0

    def test_by_lets_its_noncombat_damage_through(self, builder):
        game, mine, theirs = position(builder)
        fog_permanent(game, theirs, dealt="by")

        damage_permanent(game.state, mine, 1, theirs, is_combat=False)

        assert game.state.objects[mine].damage == 1

    def test_the_total_shield_still_stops_noncombat_damage(self, builder):
        game, mine, theirs = position(builder)
        fog_permanent(game, theirs, combat_only=False)

        damage_permanent(game.state, theirs, 1, mine, is_combat=False)

        assert game.state.objects[theirs].damage == 0


class TestItWearsOff:
    def test_cleanup_ends_the_player_shield(self, builder):
        game, mine, _ = position(builder)
        fog_player(game)
        clear_damage_shields(game.state, "this_turn")
        life = game.state.players[1].life

        damage_player(game.state, 1, 2, mine, is_combat=True)

        assert game.state.players[1].life == life - 2

    def test_cleanup_ends_the_permanent_shield(self, builder):
        game, mine, theirs = position(builder)
        fog_permanent(game, theirs)
        clear_permanent_shields(game.state, "this_turn")

        damage_permanent(game.state, theirs, 1, mine, is_combat=True)

        assert game.state.objects[theirs].damage == 1


class TestTheLoader:
    def _card(self, effect: dict, targets: dict | None = None) -> CardModel:
        data = {"id": "t_combat_fog_probe", "name": "Combat Fog Probe", "mana_cost": "{G}",
                "types": ["Instant"], "spell_effects": [effect]}
        if targets:
            data["targets"] = targets
        return CardModel.model_validate(data)

    def test_the_player_form_loads(self):
        compile_card(self._card({"op": "prevent_damage", "player": "you",
                                 "duration": "this_turn", "combat_only": True}))

    def test_the_permanent_form_loads(self):
        compile_card(self._card({"op": "prevent_damage_permanent", "objects": {"self_only": True},
                                 "dealt": "to", "duration": "this_turn", "combat_only": True}))

    @pytest.mark.parametrize("op", ["prevent_damage", "prevent_damage_permanent"])
    def test_a_non_boolean_is_refused(self, op):
        effect = {"op": op, "duration": "this_turn", "combat_only": "false"}
        if op == "prevent_damage_permanent":
            effect |= {"objects": {"self_only": True}, "dealt": "to"}
        with pytest.raises(DslError, match="combat_only"):
            compile_card(self._card(effect))
