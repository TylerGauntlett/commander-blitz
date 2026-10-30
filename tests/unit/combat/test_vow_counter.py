""""Each of those creatures can't attack you or planeswalkers you control for as
long as it has a vow counter on it." -- 508.1c, a prohibition written on a
creature, on a counter's clock (611.2b).

Promise of Loyalty is the witness. `cant_attack_player` named players on both
sides and lasted a turn or a combat; the `cant_attack_you` static is scoped to
the seat of the permanent printing it, so granting it to an opponent's creature
would make "you" that creature's own controller. So `cant_attack_player` takes
`objects` in place of `attacker` with the `while_counter` duration, and writes a
prohibition `AttackMark` on each creature. What is pinned:

1. The creature may not attack the caster, nor -- with `planeswalkers` -- the
   caster's planeswalkers; every other seat stays open.
2. The prohibition follows the creature, whoever controls it.
3. It ends when the last vow counter goes, and a counter put back does not
   revive it; a creature with no counter gets nothing.
4. A creature with nowhere left to attack cannot attack.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, remove_counters
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid

BEAR = "t_bear"
WALKER = "t_walker"

VOW = {
    "op": "cant_attack_player",
    "objects": {"controller": "opponent", "types": ["Creature"]},
    "defender": "you",
    "duration": "while_counter",
    "counter": "vow",
    "planeswalkers": True,
}


def position(builder, *, players=3, vowed=True):
    """Player 0 holds a walker and casts the vow; player 1's Bear is vowed.

    Built at player 1's untap step, so the Bear is the one about to attack.
    """
    b = builder(players=players).battlefield(0, [WALKER]).battlefield(1, [BEAR])
    for pid in range(players):
        b.library(pid, ["forest"] * 20)
    game = b.active(1).step(Step.UNTAP).build()
    bear = only_oid(game, BEAR, 1)
    if vowed:
        add_counters(game.state, bear, "vow", 1)
    run_op(game, VOW)
    return game, bear


def run_op(game, spec: dict, controller: int = 0) -> None:
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


def to_declare_attackers(game, limit: int = 80):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def targets_offered(game, oid: int) -> tuple[list[int], list[int]]:
    actions = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
    ]
    players = sorted(t.id for a in actions for t in a.targets if t.kind == "player")
    walkers = sorted(t.id for a in actions for t in a.targets if t.kind == "object")
    return players, walkers


class TestTheProhibition:
    def test_the_caster_and_their_walker_are_closed(self, builder):
        game, bear = position(builder)
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([2], [])

    def test_without_planeswalkers_the_walker_stays_open(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [WALKER])
            .battlefield(1, [BEAR])
            .active(1)
            .step(Step.UNTAP)
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        add_counters(game.state, bear, "vow", 1)
        run_op(game, {k: v for k, v in VOW.items() if k != "planeswalkers"})
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([2], [only_oid(game, WALKER, 0)])

    def test_a_creature_without_the_counter_gets_nothing(self, builder):
        game, bear = position(builder, vowed=False)
        assert game.state.objects[bear].attack_marks == []

    def test_it_follows_the_creature(self, builder):
        """Handed to player 2, the Bear still may not attack player 0."""
        game, bear = position(builder)
        game.state.objects[bear].controller = 2
        assert combat_mod.attack_target_forbidden(game.state, bear, 0)
        assert not combat_mod.attack_target_forbidden(game.state, bear, 1)

    def test_with_nowhere_left_it_cannot_attack(self, builder):
        game, bear = position(builder, players=2)
        assert not combat_mod.can_attack(game.state, bear)
        free, unvowed = position(builder, players=2, vowed=False)
        assert combat_mod.can_attack(free.state, unvowed)


class TestTheCounterClock:
    def test_removing_the_counter_ends_it(self, builder):
        game, bear = position(builder)
        remove_counters(game.state, bear, "vow", 1)
        assert game.state.objects[bear].attack_marks == []
        to_declare_attackers(game)
        assert targets_offered(game, bear)[0] == [0, 2]

    def test_a_counter_put_back_does_not_revive_it(self, builder):
        game, bear = position(builder)
        remove_counters(game.state, bear, "vow", 1)
        add_counters(game.state, bear, "vow", 1)
        to_declare_attackers(game)
        assert targets_offered(game, bear)[0] == [0, 2]

    def test_a_new_object_is_not_vowed(self, builder):
        game, bear = position(builder)
        move_object(game.state, bear, Zone.EXILE)
        move_object(game.state, bear, Zone.BATTLEFIELD)
        assert game.state.objects[bear].attack_marks == []


def _sorcery(effect: dict) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Probe.",
        "mana_cost": "{W}",
        "types": ["Sorcery"],
        "spell_effects": [effect],
    }


class TestTheLoader:
    def load(self, effect):
        compile_card(CardModel.model_validate(_sorcery(effect)))

    def test_the_printed_line_loads(self):
        self.load(VOW)

    def test_objects_and_attacker_together_are_refused(self):
        with pytest.raises(DslError, match="not both"):
            self.load({**VOW, "attacker": "each_opponent"})

    def test_the_creature_form_needs_the_counter_clock(self):
        with pytest.raises(DslError, match="while_counter"):
            self.load({**VOW, "duration": "this_turn"})

    def test_the_counter_kind_is_required(self):
        with pytest.raises(DslError, match="needs 'counter'"):
            self.load({k: v for k, v in VOW.items() if k != "counter"})

    def test_the_counter_clock_needs_creatures(self):
        effect = {k: v for k, v in VOW.items() if k != "objects"}
        with pytest.raises(DslError, match="name them in 'objects'"):
            self.load({**effect, "attacker": "each_opponent"})
