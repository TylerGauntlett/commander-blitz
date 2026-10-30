""""That player can't attack you or permanents you control during their next
turn." -- 508.1c, an attack restriction on the *attacker's* next turn.

Willie Lumpkin, Postman is the witness. Its trigger resolves on Willie's
controller's turn, so `cant_attack_player`'s two clocks -- `this_turn` and
`this_combat` -- have both run out before the damaged opponent ever declares
attackers, and `delay` fires on a step or on its controller's own turn, never on
a named other player's. So the restriction gains a third duration,
`attacker_next_turn`, pending until the attacker's next untap step
(`temp_effects.arm_attack_restrictions`) and gone at that turn's cleanup.
What is pinned:

1. Pending: it does not bite on the turn it was made, nor on a third player's.
2. In force for exactly the attacker's next turn, seat and -- with
   `planeswalkers` -- every permanent of the defender's.
3. Gone after that turn; and an eliminated attacker's entry goes with them.
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
from tests.conftest import only_oid, pass_until

BEAR = "t_bear"
WALKER = "t_walker"

POSTMAN = {
    "op": "cant_attack_player",
    "attacker": {"binding": "defender"},
    "defender": "you",
    "duration": "attacker_next_turn",
    "planeswalkers": True,
}


def position(builder, players: int = 3):
    """Player 0 (with a walker) restricts player 1 on player 0's own turn."""
    b = builder(players=players).battlefield(0, [WALKER])
    for pid in range(players):
        if pid:
            b.battlefield(pid, [BEAR])
        b.library(pid, ["forest"] * 30)
    game = b.active(0).step(Step.UNTAP).build()
    ctx = EffectContext(state=game.state, controller=0)
    ctx.bindings["defender"] = 1
    gen = execute(ctx, [POSTMAN])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)
    return game


def closed(game, pid: int) -> tuple[bool, bool]:
    """(seat 0 closed, walker closed) for ``pid``'s Bear, asked as if active."""
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
    pass_until(game, reached, limit=2000)


class TestTheClock:
    def test_it_is_pending_on_the_turn_it_was_made(self, builder):
        game = position(builder)
        (entry,) = game.state.attack_restrictions
        assert entry.in_force_turn is None
        assert closed(game, 1) == (False, False)

    def test_it_bites_during_the_attackers_next_turn(self, builder):
        game = position(builder)
        at_turn_of(game, 1)
        assert closed(game, 1) == (True, True), "the seat and its permanents"
        assert closed(game, 2) == (False, False), "only that player"

    def test_it_is_gone_after_that_turn(self, builder):
        game = position(builder)
        at_turn_of(game, 2)
        assert game.state.attack_restrictions == []

    def test_an_eliminated_attackers_entry_goes(self, builder):
        game = position(builder)
        game.state.players[1].life = 0
        sba.run(game.state)
        assert game.state.attack_restrictions == []


class TestThePlaneswalkersFlag:
    def test_without_it_the_walker_stays_open(self, builder):
        game = position(builder)
        game.state.attack_restrictions = [
            replace(r, planeswalkers=False)
            for r in game.state.attack_restrictions
        ]
        at_turn_of(game, 1)
        assert closed(game, 1) == (True, False)


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
        compile_card(
            CardModel.model_validate(_sorcery({**POSTMAN, "attacker": "each_opponent"}))
        )

    def test_an_unknown_duration_names_the_three(self):
        with pytest.raises(DslError, match="attacker_next_turn"):
            compile_card(
                CardModel.model_validate(
                    _sorcery({**POSTMAN, "attacker": "each_opponent", "duration": "next_turn"})
                )
            )
