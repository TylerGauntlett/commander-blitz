""""Can't attack a player it has already attacked this turn" -- Port Razer.

Port Razer hands itself extra combats ("untap each creature you control. After
this phase, there is an additional combat phase") and its last line is what
keeps that from being one opponent hit over and over: in each later combat it
must swing at somebody new. Rule 508.1c makes a declaration that disobeys the
restriction illegal, so the defenders it is *offered* are the claim.

Read off the turn ledger's per-creature `players_attacked_by`, so:

- **506.2**: attacking a planeswalker is not attacking its controller -- a
  walker of a player Razer already hit stays attackable, and an earlier attack
  on a walker closes nobody.
- **400.7**: a creature that left and came back is a new object that attacked
  nobody.
- With nobody left to attack, the creature is not a legal attacker at all,
  which `combat.can_attack`'s cheap guard has to know about.

The near miss is the `cant_attack_player` op from an `attacks` trigger, which
is a trigger emulating a static. The witness is `t_razer`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import can_attack
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.turn import grant_extra_phases
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, find_action, only_oid, static_probe

RAZER = "t_razer"
BEAR = "t_bear"
WALKER = "t_walker"


def until(game, predicate, limit: int = 400) -> None:
    for _ in range(limit):
        if predicate(game):
            return
        decision = game.pending()
        assert decision is not None, "nothing left to pass with"
        game.apply(_default_answer(game, decision))
    raise AssertionError("did not reach the condition")


def at_declaration(game) -> bool:
    d = game.pending()
    return d is not None and d.kind is DecisionKind.DECLARE_ATTACKERS


def position(builder, *, players: int = 3, mine=None, walker_for: int | None = None):
    if mine is None:
        mine = (RAZER,) if players > 2 else (RAZER, BEAR)
    b = builder(players=players).battlefield(0, ["mountain"] * 4 + list(mine))
    for pid in range(players):
        b.library(pid, ["mountain"] * 10)
    if walker_for is not None:
        b.battlefield(walker_for, [WALKER])
    game = b.active(0).step(Step.PRECOMBAT_MAIN).build()
    until(game, at_declaration)
    return game, only_oid(game, RAZER, 0)


def declare(game, oid: int, ref: TargetRef) -> None:
    game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=oid, targets=(ref,)))
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    # "After this phase, there is an additional combat phase" -- what Port
    # Razer's own trigger grants, queued from inside this combat.
    grant_extra_phases(game.state, ["combat"])
    # "…untap each creature you control", which the card does on damage.
    game.state.objects[oid].tapped = False


def to_second_combat(game) -> None:
    """Finish the first combat and stop at the next declaration.

    A 2-player position carries a Bear beside Razer, so the second declaration
    is posed even when Razer itself has nobody left to attack.
    """
    turn = game.state.turn
    until(game, at_declaration)
    assert game.state.turn == turn, "the second combat is this turn's"


def offered(game, oid: int) -> list[tuple[str, int]]:
    return sorted(
        (t.kind, t.id)
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
        for t in a.targets
    )


class TestTheSecondCombat:
    def test_every_opponent_is_open_in_the_first(self, builder):
        game, razer = position(builder)
        assert offered(game, razer) == [("player", 1), ("player", 2)]

    def test_the_player_already_attacked_is_closed(self, builder):
        game, razer = position(builder)
        declare(game, razer, TargetRef.player(1))
        to_second_combat(game)
        assert offered(game, razer) == [("player", 2)]

    def test_another_creature_is_not_restricted(self, builder):
        """The record is the creature's own: a Bear that hit seat 1 may again."""
        game, _ = position(builder, mine=(RAZER, BEAR))
        bear = only_oid(game, BEAR, 0)
        declare(game, bear, TargetRef.player(1))
        to_second_combat(game)
        assert ("player", 1) in offered(game, bear)

    def test_with_nobody_left_it_is_not_an_attacker(self, builder):
        game, razer = position(builder, players=2)
        declare(game, razer, TargetRef.player(1))
        to_second_combat(game)
        assert not can_attack(game.state, razer)
        assert offered(game, razer) == []


class TestPlaneswalkers:
    """506.2: a walker is not its controller."""

    def test_the_attacked_players_walker_stays_open(self, builder):
        game, razer = position(builder, players=2, walker_for=1)
        walker = only_oid(game, WALKER, 1)
        declare(game, razer, TargetRef.player(1))
        to_second_combat(game)
        assert offered(game, razer) == [("object", walker)]

    def test_attacking_a_walker_closes_nobody(self, builder):
        game, razer = position(builder, players=2, walker_for=1)
        walker = only_oid(game, WALKER, 1)
        declare(game, razer, TargetRef.obj(walker))
        to_second_combat(game)
        assert ("player", 1) in offered(game, razer)


class TestWearingOff:
    def test_a_new_object_attacked_nobody(self, builder):
        """400.7: blinked, Razer comes back with a clean record."""
        game, razer = position(builder, players=2)
        declare(game, razer, TargetRef.player(1))
        until(game, lambda g: g.state.combat is None and not at_declaration(g))
        move_object(game.state, razer, Zone.EXILE)
        move_object(game.state, razer, Zone.BATTLEFIELD)
        assert game.state.turn_ledger.players_attacked_by.get(razer) is None
        until(game, at_declaration)
        assert ("player", 1) in offered(game, razer)


class TestLoading:
    def test_affects_is_required(self):
        with pytest.raises(DslError, match="cant_attack_attacked_players needs an 'affects'"):
            compile_card(
                CardModel.model_validate(static_probe({"effect": "cant_attack_attacked_players"}))
            )
