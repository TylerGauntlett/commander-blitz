""""Whenever a player attacks, if one or more **players being attacked** are
poisoned, the attacking player draws a card" -- the `attacked_players` binding.

    Norn's Decree's second line.

`you_attack` fires once per declaration, which is the card's "whenever a player
attacks": one card however many poisoned players are attacked. The question is
asked of the seats the declaration attacks **directly** (506.2). A creature sent
at a planeswalker or battle makes its controller a defending player, which the
event's `defenders` records for melee, but not a player being attacked -- so a
poisoned player whose planeswalker alone is attacked draws nothing.

`creatures_attack_player` with its `defender` binding is the near miss: once per
defending seat, so two poisoned players attacked would draw two cards.
"""

from __future__ import annotations

from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import _default_answer, oids_of, only_oid, settle

DECREE = "t_ap_decree"
BEAR = "t_bear"
WALKER = "t_walker"
FACE, PW = "face", "walker"


def position(builder, *, poison: list[int], bears: int = 2, walker_for: int | None = None):
    b = builder(players=len(poison))
    b.battlefield(0, [BEAR] * bears)
    b.battlefield(1, [DECREE])
    if walker_for is not None:
        b.battlefield(walker_for, [WALKER])
    for pid in range(len(poison)):
        b.library(pid, ["swamp"] * 20)
    game = b.active(0).step(Step.UNTAP).max_turns(2).build()
    for pid, n in enumerate(poison):
        game.state.players[pid].poison = n
    return game


def declare(game, plan: list[tuple[int, str]]) -> None:
    for _ in range(80):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            break
        game.apply(_default_answer(game, decision))
    bears = list(oids_of(game, BEAR, 0))
    for seat, at in plan:
        oid = bears.pop(0)
        want = ("player", seat) if at == FACE else ("object", only_oid(game, WALKER, seat))
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.ADD_ATTACKER
                and a.source == oid
                and any((t.kind, t.id) == want for t in a.targets)
            )
        )
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle(game)


def drawn(game, before: int) -> int:
    return len(game.state.players[0].hand) - before


class TestPlayersBeingAttacked:
    def test_a_poisoned_player_attacked_draws_the_attacker_a_card(self, builder):
        game = position(builder, poison=[0, 1])
        before = len(game.state.players[0].hand)
        declare(game, [(1, FACE)])
        assert drawn(game, before) == 1

    def test_an_unpoisoned_player_attacked_draws_nothing(self, builder):
        game = position(builder, poison=[0, 0])
        before = len(game.state.players[0].hand)
        declare(game, [(1, FACE)])
        assert drawn(game, before) == 0

    def test_two_poisoned_players_attacked_is_still_one_card(self, builder):
        game = position(builder, poison=[0, 1, 2])
        before = len(game.state.players[0].hand)
        declare(game, [(1, FACE), (2, FACE)])
        assert drawn(game, before) == 1

    def test_one_poisoned_player_among_the_attacked_is_enough(self, builder):
        game = position(builder, poison=[0, 0, 4])
        before = len(game.state.players[0].hand)
        declare(game, [(1, FACE), (2, FACE)])
        assert drawn(game, before) == 1

    def test_a_poisoned_player_not_attacked_does_not_count(self, builder):
        game = position(builder, poison=[0, 0, 4], bears=1)
        before = len(game.state.players[0].hand)
        declare(game, [(1, FACE)])
        assert drawn(game, before) == 0

    def test_attacking_only_their_planeswalker_is_not_attacking_them(self, builder):
        """506.2: a defending player, not a player being attacked."""
        game = position(builder, poison=[0, 0, 4], bears=1, walker_for=2)
        before = len(game.state.players[0].hand)
        declare(game, [(2, PW)])
        assert drawn(game, before) == 0

    def test_the_event_names_only_the_seats_attacked_directly(self, builder):
        game = position(builder, poison=[0, 0, 0], walker_for=2)
        declare(game, [(1, FACE), (2, PW)])
        (event,) = [e for e in game.state.events if e.type == "attackers_declared"]
        assert event.data["attacked_players"] == [1]
        assert event.data["defenders"] == [1, 2]
