"""Goad's two requirements without the goad: `goad` with ``goaded: false``.

    Kardur, Doomscourge -- "When Kardur enters, until your next turn, creatures
    your opponents control attack each combat if able and attack a player other
    than you if able. Whenever an attacking creature dies, each opponent loses 1
    life and you gain 1 life."

The first sentence is 701.38a's two requirements, word for word, on goad's clock
-- and Kardur's ruling is that it does **not** goad the creatures. That is
observable: a ``goaded`` filter (Vengeful Ancestor, Puppet Master's Treasure
payoff) counts goaded creatures, and `ungoad` ("no longer goaded") ends goads.
A plain `goad` would feed both, a stronger card beside every goad payoff at the
table. None of the near misses is the sentence either: `must_attack` compels one
combat and restricts no defender, `cant_attack_player` forbids where this only
steers "if able", and an `attacks_if_able` static on Kardur would end when
Kardur leaves, which the effect outlives.

So the mark goes into `GameObject.goad_requirements_by`, which combat reads
beside the goad through `player_statics.attack_goaders`, and which nothing that
asks "is it goaded" sees. What is pinned below:

1. Both requirements bite and are not spent by a declaration.
2. It is not goaded: `goaders`, the ``goaded`` selector and the goaded-damage
   payoff all ignore it, and `ungoad` leaves it in force.
3. Goad's clock: the controller's untap step ends it, nobody else's does, and
   the controller leaving the game ends it (800.4a); the creature leaving the
   battlefield ends it (400.7). The creatures are the ones matched at
   resolution (611.2c).
4. The loader refuses a non-boolean ``goaded`` and ``goaded: false`` with a
   ``duration``.
5. Kardur's second sentence needs nothing new: a ``leaves_battlefield``
   trigger to the graveyard, gated on the ``was_attacking`` binding.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine import sba
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import resolve_pool
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import attack_goaders, goaders
from commanderblitz.engine.primitives import untap_permanent
from commanderblitz.engine.state import new_object
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.temp_effects import end_goad, goad_creature
from commanderblitz.engine.turn import grant_extra_phases
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, only_oid, pass_until
from tests.unit.combat.test_goad import (
    BEAR,
    attack_actions,
    can_finish,
    cast,
    defenders_offered,
    position,
    probe,
    to_declare_attackers,
)

TAUNT = "t_kgw_taunt"
KARDUR = "t_kgw_kardur"
PAYOFF = "t_gdf_payoff"  # "Whenever one or more goaded creatures deal combat damage…"


def taunted(builder, **kw):
    """Player 0 casts the taunt on their own turn over player 1's bear."""
    game = position(builder, active=0, hand=(TAUNT,), **kw)
    cast(game, TAUNT)
    return game, only_oid(game, BEAR, 1)


def finish(game) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


class TestTheRequirements:
    def test_it_is_recorded_as_a_requirement_not_a_goad(self, builder):
        game, bear = taunted(builder)
        obj = game.state.objects[bear]
        assert obj.goad_requirements_by == {0}
        assert obj.goaded_by == set()

    def test_it_must_attack_and_not_the_controller(self, builder):
        game, bear = taunted(builder)
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert not can_finish(game), '"Done attacking" is withheld'
        assert defenders_offered(game, bear) == [2], "a player other than you, if able"

    def test_with_only_the_controller_left_it_attacks_the_controller(self, builder):
        game, bear = taunted(builder, players=2)
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [0], "if able: nobody else to attack"
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]

    def test_it_is_not_spent_by_a_declaration(self, builder):
        """Each combat, not one: an extra combat is compelled again."""
        game, bear = taunted(builder)
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        game.apply(next(a for a in attack_actions(game, bear)))
        finish(game)
        assert game.state.objects[bear].goad_requirements_by == {0}
        assert grant_extra_phases(game.state, ["combat"]) == ["combat"]
        untap_permanent(game.state, bear)
        pass_until(
            game,
            lambda g: g.state.extra_phases_taken >= 1 and g.state.step is Step.DECLARE_ATTACKERS,
        )
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]

    def test_your_own_creatures_are_untouched(self, builder):
        game, _ = taunted(builder, mine=(BEAR,))
        mine = only_oid(game, BEAR, 0)
        assert game.state.objects[mine].goad_requirements_by == set()
        assert not goad_creature(game.state, mine, 0, goaded=False), (
            "a creature cannot attack its own controller, so the restriction is vacuous"
        )


class TestItIsNotGoaded:
    def test_goaders_does_not_see_it_and_combat_does(self, builder):
        game, bear = taunted(builder)
        assert goaders(game.state, bear) == set()
        assert attack_goaders(game.state, bear) == {0}

    def test_the_goaded_selector_does_not_match_it(self, builder):
        game, bear = taunted(builder)
        ctx = EffectContext(game.state, controller=0)
        goaded = resolve_pool(ctx, {"zone": "battlefield", "types": ["Creature"], "goaded": True})
        ungoaded = resolve_pool(ctx, {"zone": "battlefield", "types": ["Creature"], "goaded": False})
        assert bear not in goaded
        assert bear in ungoaded

    def test_the_goaded_damage_payoff_pays_nothing(self, builder):
        """Puppet Master's Treasure trigger: an opponent's creature hitting an
        opponent pays only if it is goaded, and Kardur's creatures are not."""
        game, bear = taunted(builder, mine=(PAYOFF,))
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=bear, targets=(TargetRef.player(2),))
        )
        finish(game)
        mark = (game.state.turn, Step.POSTCOMBAT_MAIN)
        pass_until(game, lambda g: (g.state.turn, g.state.step) >= mark)
        assert game.state.players[2].life < 40, "it connected"
        assert not any(
            game.state.objects[o].def_id == "treasure_token" for o in game.state.battlefield
        )

    def test_ungoad_leaves_it_in_force(self, builder):
        """"…is no longer goaded" ends goads; this never was one."""
        game, bear = taunted(builder)
        goad_creature(game.state, bear, 2)
        assert end_goad(game.state, bear)
        assert game.state.objects[bear].goaded_by == set()
        assert attack_goaders(game.state, bear) == {0}
        assert combat_mod.attack_required(game.state, bear) is False, "player 0's turn"

    def test_beside_a_real_goad_both_are_attacked_around(self, builder):
        """Goaded by player 2 and required around player 0: four seats, so
        player 3 is the one obedient attack."""
        game = position(builder, players=4, active=0, hand=(TAUNT,))
        cast(game, TAUNT)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 2)
        pass_until(game, lambda g: g.state.active_player == 1)
        to_declare_attackers(game)
        assert defenders_offered(game, bear) == [3]


class TestTheClock:
    def test_it_ends_in_the_controllers_untap_step(self, builder):
        game, bear = taunted(builder)
        pass_until(game, lambda g: g.state.active_player == 2)
        assert game.state.objects[bear].goad_requirements_by == {0}, "nobody else's untap ends it"
        pass_until(game, lambda g: g.state.active_player == 0 and g.state.turn >= 4)
        assert game.state.objects[bear].goad_requirements_by == set()
        assert not attack_goaders(game.state, bear)

    def test_the_controller_leaving_ends_it(self, builder):
        game, bear = taunted(builder)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.objects[bear].goad_requirements_by == set()

    def test_leaving_the_battlefield_ends_it(self, builder):
        game, bear = taunted(builder)
        move_object(game.state, bear, Zone.HAND)
        assert game.state.objects[bear].goad_requirements_by == set()

    def test_the_set_is_fixed_when_it_resolves(self, builder):
        """611.2c: "creatures your opponents control" is the set at resolution."""
        game, _ = taunted(builder)
        latecomer = new_object(game.state, BEAR, owner=1, zone=Zone.BATTLEFIELD)
        game.state.battlefield.append(latecomer.oid)
        assert latecomer.goad_requirements_by == set()


class TestTheLoaderGuardsIt:
    def test_a_non_boolean_is_refused(self):
        with pytest.raises(DslError, match="'goaded' is true or false"):
            probe({"op": "goad", "objects": {"zone": "battlefield"}, "goaded": "no"})

    def test_a_duration_beside_it_is_refused(self):
        with pytest.raises(DslError, match="takes no 'duration'"):
            probe(
                {
                    "op": "goad",
                    "objects": {"zone": "battlefield"},
                    "goaded": False,
                    "duration": "permanent",
                }
            )

    def test_the_witness_shape_compiles(self, registry):
        assert registry.get(TAUNT) is not None
        assert registry.get(KARDUR) is not None


def kardur_table(builder):
    """Kardur already on player 0's battlefield; player 1 swings a bear into
    player 0's big blocker, so the bear dies attacking."""
    b = builder(players=3)
    b.battlefield(0, [KARDUR, "t_big"]).battlefield(1, [BEAR])
    for pid in range(3):
        b.library(pid, ["swamp"] * 20)
    return b.active(1).step(Step.PRECOMBAT_MAIN).build()


class TestKardurWhole:
    def test_its_enters_trigger_lays_the_requirements(self, builder):
        b = builder(players=3)
        b.battlefield(1, [BEAR]).hand(0, [KARDUR])
        game = b.active(0).step(Step.PRECOMBAT_MAIN).build()
        (kardur,) = game.state.players[0].hand
        move_object(game.state, kardur, Zone.BATTLEFIELD)
        bear = only_oid(game, BEAR, 1)
        pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)
        assert game.state.objects[bear].goad_requirements_by == {0}
        assert game.state.objects[bear].goaded_by == set()

    def test_an_attacking_creature_dying_drains(self, builder):
        game = kardur_table(builder)
        bear = only_oid(game, BEAR, 1)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        game.apply(
            find_action(game, ActionKind.ADD_ATTACKER, source=bear, targets=(TargetRef.player(0),))
        )
        finish(game)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        game.apply(
            find_action(
                game,
                ActionKind.ADD_BLOCKER,
                source=only_oid(game, "t_big", 0),
                targets=(TargetRef.obj(bear),),
            )
        )
        finish(game)
        pass_until(game, lambda g: int(g.state.step) > int(Step.COMBAT_DAMAGE) or g.over)
        assert bear not in game.state.battlefield
        assert game.state.players[1].life == 40 - 1
        assert game.state.players[2].life == 40 - 1
        assert game.state.players[0].life == 40 + 1

    def test_a_creature_dying_outside_combat_does_not(self, builder):
        game = kardur_table(builder)
        bear = only_oid(game, BEAR, 1)
        move_object(game.state, bear, Zone.GRAVEYARD, cause="destroyed")
        pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)
        assert [p.life for p in game.state.players] == [40, 40, 40]
