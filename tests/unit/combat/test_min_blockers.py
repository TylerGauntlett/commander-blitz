"""`min_blockers` -- "can't be blocked except by three or more creatures".

    Troll of Khazad-dûm -- "This creature can't be blocked except by three or
    more creatures."  Hexmark Destroyer prints the same sentence with six.

Rule 509.1b: a restriction on how many creatures may block an attacker is a
fact about the whole declaration. Menace (702.111b) is the one such minimum a
keyword carries, and it is fixed at two, so granting menace would let two
creatures block the Troll -- a weaker card than the printed one. `min_blockers`
is the count as a `block_restriction` form, the mirror of `max_blockers`.

Unlike the cap it is never refused per pair: a third blocker may still arrive,
so a declaration under the floor is unfinished rather than illegal, and "Done
blocking" is withheld until it is met. A declaration that can no longer reach
the floor is retracted by `drop_illegal_blocks` on finishing, as an unfinished
Tromokratis block is -- "no creature blocks it" is what the rules produce.
Menace and a static minimum on one creature are both obeyed, so the greater
wins.
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.strategy.board import blockers_for
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import blocks_valid, can_block, min_blockers
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import attack_with, find_action, pass_until

TROLL = "t_minb_troll"             # 6/5, can't be blocked except by three or more
MENACE_TROLL = "t_minb_menace_troll"  # the same, with menace too
BRUTE = "t_minb_menace"            # 3/3 menace
BEAR = "t_bear"                    # 2/2


def board(builder, attacker: str, *, defenders: int = 3):
    """``(game, attacker_oid)``: ``attacker`` attacking into ``defenders`` bears."""
    game = (
        builder(players=2)
        .battlefield(0, ["swamp"] * 4 + [attacker])
        .battlefield(1, [BEAR] * defenders)
        .build()
    )
    oid = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == attacker)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, oid


def block(game, blocker: int, attacker: int) -> None:
    game.apply(
        find_action(
            game, ActionKind.ADD_BLOCKER, source=blocker, targets=(TargetRef.obj(attacker),)
        )
    )


def bears(game) -> list[int]:
    return [o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR]


def can_finish(game) -> bool:
    return any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


class TestThreeOrMore:
    def test_no_blocker_is_legal(self, builder):
        game, _ = board(builder, TROLL)

        assert blocks_valid(game.state, 1)
        assert can_finish(game)

    @pytest.mark.parametrize("count", [1, 2])
    def test_fewer_than_three_is_not_a_finished_declaration(self, builder, count):
        game, troll = board(builder, TROLL)
        for oid in bears(game)[:count]:
            block(game, oid, troll)

        assert not blocks_valid(game.state, 1)
        assert not can_finish(game)

    def test_a_partial_block_still_offers_the_next_blocker(self, builder):
        """Never refused per pair: the third blocker is what makes it legal."""
        game, troll = board(builder, TROLL)
        first, second, third = bears(game)
        block(game, first, troll)
        block(game, second, troll)

        assert can_block(game.state, third, troll, 1)

    def test_three_blockers_are_legal(self, builder):
        game, troll = board(builder, TROLL)
        for oid in bears(game):
            block(game, oid, troll)

        assert blocks_valid(game.state, 1)
        assert can_finish(game)
        life = game.state.players[1].life
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.combat is None)
        assert game.state.players[1].life == life
        assert bears(game) == []


class TestAnUnreachableFloor:
    def test_two_blockers_with_no_third_are_retracted(self, builder):
        """Two creatures block and nothing is left to add: "Done" comes back
        and finishing retracts the block that could never be legal."""
        game, troll = board(builder, TROLL, defenders=2)
        for oid in bears(game):
            block(game, oid, troll)

        assert can_finish(game)
        life = game.state.players[1].life
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.state.combat is None)
        assert game.state.players[1].life == life - 6
        assert len(bears(game)) == 2


class TestTheGreatestMinimumWins:
    def test_no_minimum(self, builder):
        game, bear = board(builder, BEAR)

        assert min_blockers(game.state, bear) == 1

    def test_menace_is_two(self, builder):
        game, brute = board(builder, BRUTE)

        assert min_blockers(game.state, brute) == 2

    def test_menace_and_three_is_three(self, builder):
        game, troll = board(builder, MENACE_TROLL)
        first, second, _ = bears(game)
        block(game, first, troll)
        block(game, second, troll)

        assert min_blockers(game.state, troll) == 3
        assert not blocks_valid(game.state, 1)


class TestTheCpu:
    def test_two_possible_blockers_are_no_blockers(self, builder):
        game, troll = board(builder, TROLL, defenders=2)

        assert blockers_for(game.state, troll, 1) == []

    def test_three_possible_blockers_count(self, builder):
        game, troll = board(builder, TROLL)

        assert len(blockers_for(game.state, troll, 1)) == 3


class TestTheLoader:
    def _card(self, static: dict, effect: str = "block_restriction") -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_minb_probe",
                "name": "Min Blockers Probe",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {"kind": "static", "effect": effect,
                     "affects": {"self_only": True}, **static}
                ],
            }
        )

    @pytest.mark.parametrize("n", [3, 6])
    def test_a_floor_loads(self, n):
        compile_card(self._card({"min_blockers": n}))

    @pytest.mark.parametrize("n", [0, 1, 2, True])
    def test_below_three_is_refused(self, n):
        """Two is the menace keyword; one or none restricts nothing."""
        with pytest.raises(DslError, match="min_blockers"):
            compile_card(self._card({"min_blockers": n}))

    def test_two_forms_at_once_are_refused(self):
        with pytest.raises(DslError, match="exactly one of"):
            compile_card(self._card({"min_blockers": 3, "max_blockers": 4}))

    def test_it_means_nothing_on_another_static(self):
        with pytest.raises(DslError, match="min_blockers"):
            compile_card(
                self._card({"power": 1, "toughness": 1, "min_blockers": 3}, effect="buff")
            )
