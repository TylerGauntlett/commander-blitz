""""You may tap X untapped Myr you control. If you do, this creature gets +X/+0
until end of turn and deals X damage to the player or planeswalker it's
attacking." -- Myr Battlesphere.

Two halves, and only the second needed anything new.

**Tapping X at resolution** composes: `choose_permanents` with `count: "any"`
over untapped Myr you control is the optional choice of any number (zero is
declining, and +0/+0 and 0 damage are nothing, so "if you do" adds no branch),
its `as` binding is what `tap` taps, and `{"count": {"binding": …}}` is X for
`pump` and `damage`. X is read off the binding, so it is the number chosen --
not the number of Myr on the board.

**"The player or planeswalker it's attacking"** is `damage`'s `defender_of`, a
selector naming the attacker, read off the combat at resolution (506.2): the
planeswalker in `attacking_permanent` when it is attacking one, the player in
`attackers` otherwise. Without it the reach is `"player": {"binding":
"defender"}` off the attack trigger, which names the walker's controller when the
attack is at a walker -- the card hits the walker -- and is fixed as the trigger
fires, so an attack reselected in between would not be followed. A creature no
longer attacking attacks nothing and deals nothing; a battle is neither a player
nor a planeswalker.

The witness is Myr Battlesphere.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, oids_of, only_oid, pass_until, pt

SPHERE = "t_myr_sphere"
MYR = "myr_1_1_c"
WALKER = "t_walker"
DEFENDER_OF_SELF = {"zone": "battlefield", "self_only": True}


def position(builder, *, myr=3, theirs=()):
    """Player 0's sphere and ``myr`` Myr tokens facing player 1. ``(game, sphere)``."""
    b = builder(players=2).battlefield(0, [SPHERE] + [MYR] * myr)
    if theirs:
        b.battlefield(1, list(theirs))
    game = b.active(0).step(Step.UNTAP).build()
    return game, only_oid(game, SPHERE, 0)


def attack(game, sphere, *, at=None):
    """Declare the sphere at player 1, or at the permanent ``at``."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    target = TargetRef.player(1) if at is None else TargetRef.obj(at)
    game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=sphere, targets=(target,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def tap_myr(game, count: int) -> None:
    """Answer the trigger's choice with ``count`` Myr, then let it resolve."""
    for _ in range(100):
        decision = game.pending()
        if decision is None:
            return
        if (
            decision.kind is DecisionKind.CHOOSE_OBJECTS
            and decision.context.get("purpose") == "choose_permanents"
        ):
            for index in range(count):
                game.apply(
                    next(
                        a
                        for a in game.legal_actions()
                        if a.kind is ActionKind.CHOOSE and a.choice == index
                    )
                )
            if game.pending() is decision:
                game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the trigger never finished")


def tapped_myr(game) -> int:
    return sum(1 for oid in oids_of(game, MYR, 0) if game.state.objects[oid].tapped)


class TestTappingX:
    def test_x_is_the_number_tapped(self, builder):
        game, sphere = position(builder, myr=3)
        attack(game, sphere)
        tap_myr(game, 2)
        assert game.state.step < Step.FIRST_STRIKE_DAMAGE, "measured before combat damage"
        assert tapped_myr(game) == 2, "one Myr was left untapped by choice"
        assert pt(game, sphere) == (6, 7)
        assert game.state.players[1].life == 38

    def test_tapping_none_does_nothing(self, builder):
        game, sphere = position(builder, myr=3)
        attack(game, sphere)
        tap_myr(game, 0)
        assert tapped_myr(game) == 0
        assert pt(game, sphere) == (4, 7)
        assert game.state.players[1].life == 40

    def test_a_tapped_myr_cannot_be_tapped_again(self, builder):
        game, sphere = position(builder, myr=2)
        game.state.objects[oids_of(game, MYR, 0)[0]].tapped = True
        attack(game, sphere)
        decision = None
        for _ in range(50):
            decision = game.pending()
            if decision.context.get("purpose") == "choose_permanents":
                break
            game.apply(_default_answer(game, decision))
        assert len(decision.options) == 1, "only the untapped Myr is offered"


class TestWhatItIsAttacking:
    def test_a_planeswalker_takes_it_and_its_controller_does_not(self, builder):
        game, sphere = position(builder, myr=2, theirs=(WALKER,))
        walker = only_oid(game, WALKER, 1)
        loyalty = game.state.objects[walker].counters.get("loyalty", 0)
        attack(game, sphere, at=walker)
        tap_myr(game, 2)
        assert game.state.objects[walker].counters.get("loyalty", 0) == loyalty - 2
        assert game.state.players[1].life == 40

    def test_it_reads_the_attack_as_it_resolves(self, builder):
        """An attack moved after the trigger fired is followed, not the old one."""
        game = builder(players=3).battlefield(0, [SPHERE]).active(0).step(Step.UNTAP).build()
        sphere = only_oid(game, SPHERE, 0)
        attack(game, sphere)
        game.state.combat.attackers[sphere] = 2
        ctx = EffectContext(state=game.state, controller=0, source_oid=sphere)
        list(execute(ctx, [{"op": "damage", "amount": 3, "defender_of": DEFENDER_OF_SELF}]))
        assert game.state.players[1].life == 40
        assert game.state.players[2].life == 37

    def test_a_creature_no_longer_attacking_deals_nothing(self, builder):
        game, sphere = position(builder, myr=0)
        attack(game, sphere)
        game.state.combat.removed.add(sphere)
        ctx = EffectContext(state=game.state, controller=0, source_oid=sphere)
        list(execute(ctx, [{"op": "damage", "amount": 3, "defender_of": DEFENDER_OF_SELF}]))
        assert game.state.players[1].life == 40

    def test_outside_combat_it_deals_nothing(self, builder):
        game, sphere = position(builder, myr=0)
        ctx = EffectContext(state=game.state, controller=0, source_oid=sphere)
        list(execute(ctx, [{"op": "damage", "amount": 3, "defender_of": DEFENDER_OF_SELF}]))
        assert game.state.players[1].life == 40


def probe(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "probe",
                "name": "Probe",
                "oracle_text": "x",
                "mana_cost": "{R}",
                "types": ["Instant"],
                "spell_effects": [effect],
            }
        )
    )


class TestLoadTime:
    @pytest.mark.parametrize("bad", ["self", True, 1])
    def test_it_takes_a_selector(self, bad):
        with pytest.raises(DslError, match="defender_of"):
            probe({"op": "damage", "amount": 1, "defender_of": bad})

    def test_a_selector_loads(self):
        probe({"op": "damage", "amount": 1, "defender_of": DEFENDER_OF_SELF})
