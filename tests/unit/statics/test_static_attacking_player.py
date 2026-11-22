""""Creatures attacking **your opponents** have double strike" -- the
`attacking_player` key in a static's `affects`.

    Blast-Furnace Hellkite -- "Creatures attacking your opponents have double
    strike."  Oviya, Automech Artisan -- "Each creature that's attacking one of
    your opponents has trample."

Rule 506.2 gives an attacking creature one of three things to attack: a player,
a planeswalker, or a battle. "Attacking your opponents" names the first kind
only, and names it relative to the static's controller -- so the creatures it
describes can be anybody's: at a pod, an opponent's creature swinging at
another opponent gets double strike too, and one swinging at *you* does not.

`attacking: true` is the near miss. It is a bare boolean, so written on this
static it would hand double strike to the creature attacking you and to the one
attacking a planeswalker -- a card stronger for your opponents than the printed
one. `attacking_player` reads whom, from `combat.attackers` and
`combat.attacking_permanent`: board state no layer writes, so the static stays
a pipeline input reader and cannot depend on another static's output.

Pinned below:

1. Your creature attacking an opponent has double strike, and deals damage twice.
2. Your creature attacking that opponent's planeswalker does not.
3. At a pod, an opponent's creature attacking another opponent has it; one
   attacking you does not.
4. Before attackers are declared and once combat ends, nobody has it.
5. The loader refuses `true`, a binding, and the `or_planeswalkers` widening.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import (
    _default_answer,
    keywords,
    oids_of,
    only_oid,
    pass_until,
    settle,
    static_probe,
)

LORD = "t_furnace_lord"
BEAR = "t_bear"
WALKER = "t_walker"
DOUBLE_STRIKE = "double_strike"

FACE = "face"
PW = "walker"


def position(builder, *, lord: int = 0, p1=(), p2=(), bears: int = 1):
    """Player 0 attacks with ``bears`` bears; ``lord`` is who controls the static.

    Three seats, because "your opponents" has a way to be wrong that two cannot
    show: whose creature it is and whom it attacks are separate questions.
    """
    b = builder(players=3)
    b.battlefield(0, [BEAR] * bears)
    b.battlefield(lord, [LORD])
    if p1:
        b.battlefield(1, list(p1))
    if p2:
        b.battlefield(2, list(p2))
    for pid in range(3):
        b.library(pid, ["swamp"] * 20)
    game = b.active(0).step(Step.UNTAP).max_turns(2).build()
    return game, list(oids_of(game, BEAR, 0))


def to_declare_attackers(game, limit: int = 80) -> None:
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def declare(game, bears: list[int], plan: list[tuple[int, str]]) -> None:
    """Send the bears, one per ``(seat, FACE | PW)`` entry, and stop with the
    attack still live."""
    to_declare_attackers(game)
    for oid, (seat, at) in zip(bears, plan, strict=True):
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
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
    )
    settle(game)
    assert game.state.combat is not None, "the attack has to still be live"


def life(game, pid: int) -> int:
    return game.state.players[pid].life


class TestYourAttack:
    def test_a_creature_attacking_an_opponent_has_double_strike(self, builder):
        game, (bear,) = position(builder)
        declare(game, [bear], [(1, FACE)])

        assert DOUBLE_STRIKE in keywords(game, bear)

    def test_it_deals_combat_damage_twice(self, builder):
        """The grant is the real keyword, read where first-strike damage is
        dealt: an unblocked 2/2 takes 4."""
        game, (bear,) = position(builder)
        before = life(game, 1)
        declare(game, [bear], [(1, FACE)])

        pass_until(game, lambda g: g.state.combat is None)

        assert life(game, 1) == before - 4

    def test_a_creature_attacking_a_planeswalker_does_not(self, builder):
        """506.2: the walker is not the player. `attacking: true` would grant it."""
        game, (at_face, at_walker) = position(builder, p1=(WALKER,), bears=2)
        declare(game, [at_face, at_walker], [(1, FACE), (1, PW)])

        assert DOUBLE_STRIKE in keywords(game, at_face)
        assert DOUBLE_STRIKE not in keywords(game, at_walker)


class TestAtAPod:
    def test_an_opponents_creature_attacking_another_opponent_has_it(self, builder):
        """Player 2 controls the static. Player 0 is its opponent attacking
        player 1, also its opponent: the creature is attacking one of player
        2's opponents, whoever controls it."""
        game, (bear,) = position(builder, lord=2)
        declare(game, [bear], [(1, FACE)])

        assert DOUBLE_STRIKE in keywords(game, bear)

    def test_a_creature_attacking_you_does_not(self, builder):
        game, (bear,) = position(builder, lord=2)
        before = life(game, 2)
        declare(game, [bear], [(2, FACE)])

        assert DOUBLE_STRIKE not in keywords(game, bear)
        pass_until(game, lambda g: g.state.combat is None)
        assert life(game, 2) == before - 2


class TestOutsideTheAttack:
    def test_nobody_has_it_before_attackers_are_declared(self, builder):
        game, (bear,) = position(builder)
        to_declare_attackers(game)

        assert DOUBLE_STRIKE not in keywords(game, bear)

    def test_it_wears_off_when_combat_ends(self, builder):
        game, (bear,) = position(builder)
        declare(game, [bear], [(1, FACE)])
        assert DOUBLE_STRIKE in keywords(game, bear)

        pass_until(game, lambda g: g.state.combat is None)

        assert DOUBLE_STRIKE not in keywords(game, bear)


class TestTheLoader:
    @staticmethod
    def compile(affects: dict):
        return compile_card(
            CardModel.model_validate(
                static_probe(
                    {"effect": "grant_keyword", "keywords": ["double_strike"], "affects": affects}
                )
            )
        )

    @pytest.mark.parametrize("who", ["you", "opponent", "any", "most_life"])
    def test_a_player_word_loads(self, who):
        self.compile({"types": ["Creature"], "controller": "any", "attacking_player": who})

    @pytest.mark.parametrize("bad", [True, "defender", {"binding": "defender"}])
    def test_anything_else_is_refused(self, bad):
        """`true` is how `attacking` is spelled and would name nobody; a static
        binds nothing for the binding form to read."""
        with pytest.raises(DslError, match="attacking_player"):
            self.compile({"types": ["Creature"], "attacking_player": bad})

    def test_the_planeswalker_widening_is_refused(self):
        """`or_planeswalkers` asks the walker's derived types, which inside the
        layer pipeline is the pipeline's own output."""
        with pytest.raises(DslError, match="or_planeswalkers"):
            self.compile(
                {"types": ["Creature"], "attacking_player": "opponent", "or_planeswalkers": True}
            )
