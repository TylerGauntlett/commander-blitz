""""Creatures that player controls can't attack you or planeswalkers you control
until your next turn." -- 508.1c, an attack restriction on the *controller's*
clock (611.2a: a one-shot effect's continuous effect lasts as long as it says).

Orzhov Advokist is the witness. Its upkeep trigger locks every player who took
the counters, and the lock has to hold through every turn until the Advokist's
controller's next turn begins. `attacker_next_turn` is the near miss and is
wrong twice over: it is keyed on the *attacker's* next turn, so it is pending
when it should already bite and gone after one turn of theirs -- an opponent
who takes an extra turn gets their ordinary turn free. So the restriction gains
`until_your_next_turn`, keyed to the effect's controller
(`structs.AttackRestriction.player`) and cleared in that player's untap step,
detain's clock. What is pinned:

1. It bites at once, and through every other player's turn.
2. It ends when the controller's next turn begins -- an extra turn of theirs
   included -- and an extra turn taken by the locked player does not end it.
3. With `planeswalkers` it closes the controller's walkers as well as the seat.
4. An eliminated controller's entry goes, since that untap step never comes.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.temp_effects import restrict_attack
from tests.conftest import only_oid, pass_until

BEAR = "t_bear"
WALKER = "t_walker"

ADVOKIST = {
    "op": "cant_attack_player",
    "attacker": "each_opponent",
    "defender": "you",
    "duration": "until_your_next_turn",
    "planeswalkers": True,
}


def position(builder, players: int = 3):
    """Player 0 (with a walker) locks every opponent in their own upkeep."""
    b = builder(players=players).battlefield(0, [WALKER])
    for pid in range(players):
        if pid:
            b.battlefield(pid, [BEAR])
        b.library(pid, ["forest"] * 30)
    game = b.active(0).step(Step.UPKEEP).build()
    ctx = EffectContext(state=game.state, controller=0)
    gen = execute(ctx, [ADVOKIST])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)
    return game


def closed(game, pid: int) -> tuple[bool, bool]:
    """(seat 0 closed, walker closed) for ``pid``'s Bear."""
    bear = only_oid(game, BEAR, pid)
    walker = only_oid(game, WALKER, 0)
    return (
        combat_mod._attack_prohibited(game.state, bear, 0),
        combat_mod._attack_prohibited(game.state, bear, 0, permanent=walker),
    )


def at_turn_of(game, pid: int, nth: int = 1) -> None:
    """Advance to the main phase of ``pid``'s ``nth`` turn from now."""
    seen = 0
    last = game.state.turn

    def reached(g):
        nonlocal seen, last
        if g.state.turn != last:
            last = g.state.turn
            if g.state.active_player == pid:
                seen += 1
        return seen == nth and g.state.step >= Step.PRECOMBAT_MAIN

    pass_until(game, reached, limit=3000)


class TestTheClock:
    def test_it_bites_at_once(self, builder):
        game = position(builder)
        assert len(game.state.attack_restrictions) == 2, "one per opponent"
        assert all(r.player == 0 for r in game.state.attack_restrictions)
        assert closed(game, 1) == (True, True)
        assert closed(game, 2) == (True, True)

    def test_it_holds_through_each_opponents_turn(self, builder):
        game = position(builder)
        at_turn_of(game, 1)
        assert closed(game, 1) == (True, True)
        at_turn_of(game, 2)
        assert closed(game, 2) == (True, True)
        assert closed(game, 1) == (True, True)

    def test_it_ends_when_the_controllers_next_turn_begins(self, builder):
        game = position(builder)
        at_turn_of(game, 0)
        assert game.state.attack_restrictions == []
        assert closed(game, 1) == (False, False)


class TestExtraTurns:
    def test_the_locked_players_extra_turn_does_not_end_it(self, builder):
        game = position(builder)
        game.state.extra_turns.append(1)
        at_turn_of(game, 1)
        assert closed(game, 1) == (True, True), "the extra turn"
        at_turn_of(game, 1)
        assert closed(game, 1) == (True, True), "their ordinary turn after it"
        at_turn_of(game, 0)
        assert game.state.attack_restrictions == []

    def test_the_controllers_extra_turn_ends_it(self, builder):
        game = position(builder)
        game.state.extra_turns.append(0)
        at_turn_of(game, 0)
        assert game.state.active_player == 0
        assert game.state.attack_restrictions == []


class TestThePlaneswalkersFlag:
    def test_without_it_the_walker_stays_open(self, builder):
        game = position(builder)
        game.state.attack_restrictions = [
            replace(r, planeswalkers=False) for r in game.state.attack_restrictions
        ]
        assert closed(game, 1) == (True, False)


class TestElimination:
    def test_an_eliminated_controllers_entries_go(self, builder):
        game = position(builder)
        game.state.players[0].life = 0
        sba.run(game.state)
        assert game.state.attack_restrictions == []

    def test_no_clock_is_no_restriction(self, builder):
        game = position(builder)
        game.state.attack_restrictions = []
        assert not restrict_attack(game.state, 1, 0, "until_your_next_turn")
        assert game.state.attack_restrictions == []


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
    def test_the_duration_loads(self):
        compile_card(CardModel.model_validate(_sorcery(ADVOKIST)))

    def test_an_unknown_duration_names_it(self):
        with pytest.raises(DslError, match="until_your_next_turn"):
            compile_card(
                CardModel.model_validate(_sorcery({**ADVOKIST, "duration": "next_turn"}))
            )
