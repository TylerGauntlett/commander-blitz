"""Galactus, Devourer of Worlds and Silver Surfer, Galactus's Herald, past what
the behaviour gate can see.

    Galactus: "Insatiable Hunger — Galactus attacks an opponent with the most
    life among your opponents each combat if able unless you control a creature
    named Silver Surfer, Galactus's Herald."
    Silver Surfer: "Whenever Silver Surfer deals combat damage to a player,
    until the end of your next turn, target creature attacks that player each
    combat if able."

The gate casts each card and stops, so neither attack requirement is ever
declared against there. Asserted here: Galactus is offered only the opponent on
the most life, and is free beside the Surfer; the Surfer's hit marks its target
for the player it hit, not for any opponent.
"""

from __future__ import annotations

from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, attack_with, only_oid, pass_until

GALACTUS = "galactus_devourer_of_worlds"
SURFER = "silver_surfer_galactus_s_herald"
BEAR = "t_bear"


def to_declare_attackers(game, limit: int = 80):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def players_offered(game, oid: int) -> list[int]:
    return sorted(
        t.id
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
        for t in a.targets
        if t.kind == "player"
    )


def board(builder, mine, *, lives=(40, 20, 30)):
    b = builder(players=3).battlefield(0, list(mine)).battlefield(1, [BEAR])
    for pid in range(3):
        b.library(pid, ["forest"] * 20)
    game = b.active(0).step(Step.UNTAP).build()
    for pid, life in enumerate(lives):
        game.state.players[pid].life = life
    return game


class TestInsatiableHunger:
    def test_galactus_must_attack_the_opponent_on_the_most_life(self, builder):
        game = board(builder, [GALACTUS])
        galactus = only_oid(game, GALACTUS, 0)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [galactus]
        assert players_offered(game, galactus) == [2]

    def test_the_herald_switches_it_off(self, builder):
        game = board(builder, [GALACTUS, SURFER])
        galactus = only_oid(game, GALACTUS, 0)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert players_offered(game, galactus) == [1, 2]


class TestTheHeraldsHit:
    def test_the_target_must_attack_the_player_it_hit(self, builder):
        game = board(builder, [SURFER])
        surfer = only_oid(game, SURFER, 0)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        attack_with(game, surfer, 1)
        pass_until(
            game,
            lambda g: any(g.state.objects[o].attack_marks for o in g.state.battlefield),
        )
        marked = [o for o in game.state.battlefield if game.state.objects[o].attack_marks]
        assert marked in ([surfer], [bear])
        (mark,) = game.state.objects[marked[0]].attack_marks
        assert (mark.defender, mark.until_end_of_turn_of) == (1, 0)
