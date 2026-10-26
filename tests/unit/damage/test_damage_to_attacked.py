"""Damage to "the player or planeswalker it's attacking" -- ``to_attacked``.

    "Whenever this creature attacks, you may tap X untapped Myr you control. If
    you do, this creature gets +X/+0 until end of turn and deals X damage to
    **the player or planeswalker it's attacking**."   -- Myr Battlesphere

506.2: a creature attacks a player, a planeswalker or a battle, and attacking
somebody's planeswalker is not attacking them. ``{"binding": "defender"}`` on
``player`` was the only spelling, and the ``attacks`` event's ``defender`` is
the defending player even when the walker is what was attacked -- so it burned
the controller and left the walker untouched. ``to_attacked`` reads the event's
``attacked_permanent`` beside it.

The answer is last-known information, read off the trigger's event rather than
``state.combat``: Battlesphere's ruling has it deal its X damage "to the
appropriate player or planeswalker" even after it has left the battlefield. A
walker that has itself left takes nothing, and the damage does not move to its
controller.

The tap half needs no new op and is pinned here because the gap record could
not confirm it: ``choose_permanents`` with ``count: "any"`` is the
resolution-time "tap X untapped Myr", X is the size of its binding, and the
whole sentence is choose, tap, pump, damage. Myr Battlesphere is the witness.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, oids_of, only_oid, pass_until, pt

SPHERE = "t_ta_sphere"  # 4/7 Myr; attack trigger taps X Myr for +X/+0 and X damage
RIDER = "t_ta_rider"  # Hellrider: each attacker deals 1 to what it attacks
MYR = "myr_1_1_c"
BEAR = "t_bear"
WALKER = "t_walker"  # 4 loyalty
BATTLE = "t_battle_wall"  # defense 3


def board(builder, mine=(), theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    return game


def attack(game, oid: int, at: TargetRef) -> None:
    game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(at,)))


def done(game) -> None:
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def to_the_pick(game):
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.CHOOSE_OBJECTS)
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
    return decision


def tap_myr(game, oids) -> None:
    """Answer the trigger's pick with exactly these Myr."""
    decision = to_the_pick(game)
    wanted = set(oids)
    for index, option in enumerate(decision.options):
        if option.ref is not None and option.ref.id in wanted:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
    if game.pending() is decision:
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def life(game, pid: int = 1) -> int:
    return game.state.players[pid].life


def loyalty(game, oid: int) -> int:
    return game.state.objects[oid].counter("loyalty")


class TestTappingXMyr:
    def test_the_pick_is_any_number_of_untapped_myr_you_control(self, builder):
        game = board(builder, mine=[SPHERE, MYR, MYR, MYR, BEAR], theirs=[MYR])
        sphere = only_oid(game, SPHERE)
        attack(game, sphere, TargetRef.player(1))
        done(game)
        decision = to_the_pick(game)
        offered = {o.ref.id for o in decision.options if o.ref is not None}
        assert offered == set(oids_of(game, MYR, 0))
        assert (decision.min_count, decision.max_count) == (0, 3)

    def test_the_attacking_sphere_is_tapped_and_so_not_offered(self, builder):
        """It is a Myr, but attacking tapped it (no vigilance)."""
        game = board(builder, mine=[SPHERE, MYR])
        sphere = only_oid(game, SPHERE)
        attack(game, sphere, TargetRef.player(1))
        done(game)
        offered = {o.ref.id for o in to_the_pick(game).options if o.ref is not None}
        assert sphere not in offered

    def test_x_taps_pumps_and_burns(self, builder):
        game = board(builder, mine=[SPHERE, MYR, MYR, MYR])
        sphere = only_oid(game, SPHERE)
        myr = oids_of(game, MYR, 0)
        before = life(game)
        attack(game, sphere, TargetRef.player(1))
        done(game)
        tap_myr(game, myr[:2])
        resolve(game)
        assert [game.state.objects[m].tapped for m in myr] == [True, True, False]
        assert pt(game, sphere) == (6, 7)
        assert life(game) == before - 2

    def test_tapping_none_does_nothing(self, builder):
        game = board(builder, mine=[SPHERE, MYR, MYR])
        sphere = only_oid(game, SPHERE)
        before = life(game)
        attack(game, sphere, TargetRef.player(1))
        done(game)
        tap_myr(game, [])
        resolve(game)
        assert pt(game, sphere) == (4, 7)
        assert life(game) == before
        assert not any(game.state.objects[m].tapped for m in oids_of(game, MYR, 0))

    def test_the_damage_lands_even_after_the_sphere_has_left(self, builder):
        """The ruling: no +X/+0 for a creature that is gone, but the X damage
        still reaches the player it was attacking."""
        game = board(builder, mine=[SPHERE, MYR, MYR])
        sphere = only_oid(game, SPHERE)
        before = life(game)
        attack(game, sphere, TargetRef.player(1))
        done(game)
        to_the_pick(game)
        move_object(game.state, sphere, Zone.GRAVEYARD)
        tap_myr(game, oids_of(game, MYR, 0))
        resolve(game)
        assert life(game) == before - 2


class TestThePlaneswalkerItIsAttacking:
    def test_the_walker_takes_it_and_its_controller_does_not(self, builder):
        """The near miss, `{"binding": "defender"}`, would burn seat 1 here."""
        game = board(builder, mine=[SPHERE, MYR, MYR], theirs=[WALKER])
        sphere, walker = only_oid(game, SPHERE), only_oid(game, WALKER)
        before = life(game)
        attack(game, sphere, TargetRef.obj(walker))
        done(game)
        tap_myr(game, oids_of(game, MYR, 0))
        resolve(game)
        assert loyalty(game, walker) == 2
        assert life(game) == before

    def test_a_walker_that_has_left_takes_nothing_and_nothing_moves(self, builder):
        game = board(builder, mine=[SPHERE, MYR, MYR], theirs=[WALKER])
        sphere, walker = only_oid(game, SPHERE), only_oid(game, WALKER)
        before = life(game)
        attack(game, sphere, TargetRef.obj(walker))
        done(game)
        to_the_pick(game)
        move_object(game.state, walker, Zone.GRAVEYARD)
        tap_myr(game, oids_of(game, MYR, 0))
        resolve(game)
        assert life(game) == before

    def test_a_battle_is_neither_a_player_nor_a_planeswalker(self, builder):
        game = board(builder, mine=[SPHERE, MYR, MYR], theirs=[BATTLE])
        sphere, battle = only_oid(game, SPHERE), only_oid(game, BATTLE)
        before = life(game)
        attack(game, sphere, TargetRef.obj(battle))
        done(game)
        tap_myr(game, oids_of(game, MYR, 0))
        resolve(game)
        assert game.state.objects[battle].counter("defense") == 3
        assert life(game) == before


class TestItIsTheTriggeringAttacker:
    def test_each_attacker_hits_what_it_attacks(self, builder):
        """Hellrider: "it" is the creature that attacked, not the source."""
        game = board(builder, mine=[RIDER, BEAR], theirs=[WALKER])
        rider, bear, walker = only_oid(game, RIDER), only_oid(game, BEAR), only_oid(game, WALKER)
        before = life(game)
        attack(game, rider, TargetRef.player(1))
        attack(game, bear, TargetRef.obj(walker))
        done(game)
        resolve(game)
        assert life(game) == before - 1
        assert loyalty(game, walker) == 3


class TestTheLoader:
    def card(self, trigger, **damage):
        return {
            "id": "t_probe_rider",
            "name": "Probe Rider",
            "mana_cost": "{3}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "probe",
                    "trigger": trigger,
                    "effects": [{"op": "damage", "amount": {"const": 1}, **damage}],
                }
            ],
        }

    def test_an_attacks_trigger_loads(self):
        compile_card(
            CardModel.model_validate(self.card({"event": "attacks"}, to_attacked=True))
        )

    def test_any_other_trigger_is_refused(self):
        """No other event says whom "it" attacked; the damage would hit nobody."""
        with pytest.raises(DslError, match="'attacks' trigger"):
            compile_card(
                CardModel.model_validate(
                    self.card({"event": "self_enters", "source": "self"}, to_attacked=True)
                )
            )

    def test_only_true_says_anything(self):
        with pytest.raises(DslError, match="to_attacked"):
            compile_card(
                CardModel.model_validate(self.card({"event": "attacks"}, to_attacked=False))
            )

    def test_it_is_a_damage_key(self):
        card = self.card({"event": "attacks"})
        card["abilities"][0]["effects"] = [
            {"op": "lose_life", "player": "opponent", "amount": {"const": 1}, "to_attacked": True}
        ]
        with pytest.raises(DslError, match="damage recipient"):
            compile_card(CardModel.model_validate(card))
