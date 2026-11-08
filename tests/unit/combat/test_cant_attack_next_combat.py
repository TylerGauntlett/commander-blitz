""""They can't attack you or planeswalkers you control that combat." -- 508.1c,
a prohibition written on named creatures, for one combat that has not begun.

Illusionist's Gambit is the witness: "Remove all attacking creatures from
combat and untap them. After this phase, there is an additional combat phase.
Each of those creatures attacks that combat if able. They can't attack you or
planeswalkers you control that combat."

"That combat" is the additional one, which no existing clock reached.
`cant_attack_player`'s `this_combat` is cleared by `combat.end_combat` at the
end of the combat the spell is cast in, before the additional one begins, so it
would prohibit nothing; `this_turn` would also bind any later combat that
turn; and the player form would stop every creature the attacking player
controls, not "those creatures". So the creature form (`objects`) takes a
second clock, `next_combat`: `must_attack`'s, written as a prohibition
`AttackMark` on each creature and spent by
`combat.discharge_attack_requirements` once its controller's next declaration
of attackers is locked in. What is pinned:

1. In the additional combat, each of those creatures must attack, and the
   caster and the caster's planeswalker are not offered -- so with another
   opponent at the table they attack that opponent.
2. With the caster the only player left to attack, the creatures cannot attack
   and the requirement owes nothing (508.1d, "if able").
3. The mark survives the end of the combat it was made in and is spent by the
   next declaration, whether or not the creature attacked; a creature that was
   not attacking gets nothing.
4. The loader holds the clock to `objects`, and refuses a `counter` on it.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import (
    action_for_card,
    attack_with,
    find_action,
    oids_of,
    only_oid,
    pass_until,
    settle,
)

GAMBIT = "t_cnc_gambit"  # Illusionist's Gambit at {0}
BEAR = "t_bear"
WALKER = "t_walker"

NEXT_COMBAT = {
    "op": "cant_attack_player",
    "objects": {"zone": "battlefield", "types": ["Creature"], "controller": "opponent"},
    "defender": "you",
    "duration": "next_combat",
    "planeswalkers": True,
}


def gambit_position(builder, *, players=3, bears=2, stay_home=0):
    """Player 1 attacks player 0 with Bears; player 0 casts the Gambit.

    Player 0 holds a planeswalker and the Gambit. ``stay_home`` of player 1's
    Bears do not attack. Returns ``(game, attackers, idle)`` with the Gambit
    resolved, still in player 1's declare blockers step.
    """
    b = (
        builder(players=players)
        .battlefield(0, [WALKER])
        .battlefield(1, [BEAR] * (bears + stay_home))
        .hand(0, [GAMBIT])
    )
    for pid in range(players):
        b.library(pid, ["forest"] * 20)
    game = b.active(1).step(Step.UNTAP).build()
    to_declare_attackers(game)
    bears_ = oids_of(game, BEAR, 1)
    attackers, idle = bears_[:bears], bears_[bears:]
    for oid in attackers:
        attack_with(game, oid, defender=0)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game,
        lambda g: g.state.step is Step.DECLARE_BLOCKERS
        and g.pending() is not None
        and g.pending().kind is DecisionKind.PRIORITY
        and g.pending().player == 0,
    )
    game.apply(action_for_card(game, ActionKind.CAST, GAMBIT))
    settle(game)
    return game, attackers, idle


def to_declare_attackers(game, limit: int = 200):
    pass_until(
        game,
        lambda g: g.pending() is not None and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        limit=limit,
    )
    assert game.pending() is not None and game.pending().kind is DecisionKind.DECLARE_ATTACKERS
    return game


def targets_offered(game, oid: int) -> tuple[list[int], list[int]]:
    actions = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
    ]
    players = sorted(t.id for a in actions for t in a.targets if t.kind == "player")
    walkers = sorted(t.id for a in actions for t in a.targets if t.kind == "object")
    return players, walkers


def can_finish(game) -> bool:
    return any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


def run_op(game, spec: dict, controller: int = 0) -> None:
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


class TestTheGambitEndToEnd:
    def test_the_attackers_are_removed_untapped_and_marked(self, builder):
        game, attackers, _ = gambit_position(builder)
        for oid in attackers:
            obj = game.state.objects[oid]
            assert not game.state.combat.attacking(oid)
            assert not obj.tapped
            assert obj.must_attack == "next_combat"
            assert [(m.defender, m.prohibition, m.planeswalkers, m.next_combat) for m in obj.attack_marks] == [
                (0, True, True, True)
            ]

    def test_in_the_additional_combat_they_must_attack_the_other_player(self, builder):
        game, attackers, _ = gambit_position(builder)
        turn = game.state.turn
        to_declare_attackers(game)
        assert game.state.turn == turn and game.state.active_player == 1
        for oid in attackers:
            assert targets_offered(game, oid) == ([2], [])
        assert not can_finish(game)
        for oid in attackers:
            attack_with(game, oid, defender=2)
        assert can_finish(game)

    def test_after_that_combat_the_restriction_is_gone(self, builder):
        game, attackers, _ = gambit_position(builder)
        to_declare_attackers(game)
        for oid in attackers:
            attack_with(game, oid, defender=2)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        for oid in attackers:
            obj = game.state.objects[oid]
            assert obj.attack_marks == []
            assert obj.must_attack is None
            assert not combat_mod.attack_target_forbidden(game.state, oid, 0)
            assert not combat_mod.attack_target_forbidden(
                game.state, oid, 0, permanent=only_oid(game, WALKER, 0)
            )

    def test_a_creature_that_was_not_attacking_is_free(self, builder):
        game, _, idle = gambit_position(builder, bears=1, stay_home=1)
        (home,) = idle
        assert game.state.objects[home].attack_marks == []
        to_declare_attackers(game)
        assert targets_offered(game, home) == ([0, 2], [only_oid(game, WALKER, 0)])


class TestWithNobodyElseToAttack:
    """Two players: the caster is the only defender, so "if able" excuses them."""

    def test_the_gambit_leaves_them_home_and_the_clock_is_spent(self, builder):
        """The additional combat is walked with nobody declared, and spends both halves."""
        game, attackers, _ = gambit_position(builder, players=2)
        assert game.state.turn == 1 and game.state.step is Step.POSTCOMBAT_MAIN
        begin_combats = [e for e in game.state.events if e.type == "begin_combat"]
        assert len(begin_combats) == 2
        assert game.state.players[0].life == game.state.players[0].starting_life
        for oid in attackers:
            obj = game.state.objects[oid]
            assert not obj.tapped
            assert obj.attack_marks == [] and obj.must_attack is None

    def test_must_attack_owes_nothing_when_the_only_seat_is_closed(self, builder):
        b = builder(players=2).battlefield(0, [WALKER]).battlefield(1, [BEAR])
        for pid in range(2):
            b.library(pid, ["forest"] * 20)
        game = b.active(1).step(Step.UNTAP).build()
        assert game.state.step < Step.BEGIN_COMBAT
        bear = only_oid(game, BEAR, 1)
        run_op(game, NEXT_COMBAT)
        run_op(game, {"op": "must_attack", "objects": NEXT_COMBAT["objects"], "duration": "next_combat"})
        assert combat_mod.legal_defenders(game.state, bear) == []
        assert combat_mod.legal_permanent_defenders(game.state, bear) == []
        assert not combat_mod.can_attack(game.state, bear)
        assert not combat_mod.attack_required(game.state, bear)
        pass_until(game, lambda g: g.state.step is Step.POSTCOMBAT_MAIN)
        obj = game.state.objects[bear]
        assert not obj.tapped
        assert obj.attack_marks == [] and obj.must_attack is None


class TestTheNextCombatClock:
    def test_it_is_spent_by_the_next_declaration_whether_or_not_it_attacked(self, builder):
        b = builder(players=3).battlefield(0, [WALKER]).battlefield(1, [BEAR])
        for pid in range(3):
            b.library(pid, ["forest"] * 20)
        game = b.active(1).step(Step.UNTAP).build()
        bear = only_oid(game, BEAR, 1)
        run_op(game, NEXT_COMBAT)
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([2], [])
        assert can_finish(game)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert game.state.objects[bear].attack_marks == []

    def test_another_players_declaration_does_not_spend_it(self, builder):
        """Player 2's declaration spends player 2's mark and leaves player 1's."""
        b = builder(players=3).battlefield(0, [WALKER]).battlefield(1, [BEAR]).battlefield(2, [BEAR])
        for pid in range(3):
            b.library(pid, ["forest"] * 20)
        game = b.active(2).step(Step.UNTAP).build()
        bear = only_oid(game, BEAR, 1)
        theirs = only_oid(game, BEAR, 2)
        run_op(game, NEXT_COMBAT)
        to_declare_attackers(game)
        assert game.state.active_player == 2
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        assert game.state.objects[theirs].attack_marks == []
        assert len(game.state.objects[bear].attack_marks) == 1

    def test_without_planeswalkers_the_walker_stays_open(self, builder):
        b = builder(players=3).battlefield(0, [WALKER]).battlefield(1, [BEAR])
        for pid in range(3):
            b.library(pid, ["forest"] * 20)
        game = b.active(1).step(Step.UNTAP).build()
        bear = only_oid(game, BEAR, 1)
        run_op(game, {k: v for k, v in NEXT_COMBAT.items() if k != "planeswalkers"})
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([2], [only_oid(game, WALKER, 0)])


def _sorcery(effect: dict) -> dict:
    return {
        "id": "t_probe",
        "name": "Probe",
        "oracle_text": "",
        "mana_cost": "{W}",
        "types": ["Sorcery"],
        "spell_effects": [effect],
    }


class TestTheLoader:
    def load(self, effect):
        compile_card(CardModel.model_validate(_sorcery(effect)))

    def test_the_printed_line_loads(self):
        self.load({**NEXT_COMBAT, "objects": {"binding": "those"}})

    def test_a_counter_on_the_combat_clock_is_refused(self):
        with pytest.raises(DslError, match="takes no 'counter'"):
            self.load({**NEXT_COMBAT, "counter": "vow"})

    def test_the_combat_clock_needs_creatures(self):
        effect = {k: v for k, v in NEXT_COMBAT.items() if k != "objects"}
        with pytest.raises(DslError, match="name them in 'objects'"):
            self.load({**effect, "attacker": "each_opponent"})

    def test_this_combat_is_not_the_creature_form(self):
        with pytest.raises(DslError, match="'next_combat'"):
            self.load({**NEXT_COMBAT, "duration": "this_combat"})
