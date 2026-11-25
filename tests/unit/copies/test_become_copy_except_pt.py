"""Cephalid Facetaker — a copy that keeps a size of its own.

    At the beginning of combat on your turn, you may have this creature become
    a copy of another target creature until end of turn, except it's 1/4 and
    has "This creature can't be blocked."

Rule 707.9b: "except it's 1/4" is part of the copiable values, so it is written
onto the copied face (`copying_power`, `copying_toughness`, read by
`GameState.card_of`), not set on top of it. The near misses are both layer-7
effects: a `set_pt` after the copy is cancelled the moment the copied creature
is pumped, and an `animate` 1/4 is a layer-7b set a copy of the Facetaker
would not see. On the face, counters and pumps start from 1/4.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute_one
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, clear_until_eot
from tests.conftest import only_oid, pt

GUARDIAN = "t_guardian"  # 1/1
LIFEGIVER = "t_lifegiver"  # 3/3

ONE_FOUR = {"power": 1, "toughness": 4}


def board(builder):
    game = builder(players=2).battlefield(0, [GUARDIAN]).battlefield(1, [LIFEGIVER]).build(
        advance=False
    )
    return game, only_oid(game, GUARDIAN), only_oid(game, LIFEGIVER)


def become_copy(game, oid: int, copying: dict, controller: int = 0, **overrides) -> None:
    spec = {
        "op": "become_copy",
        "objects": {"zone": "battlefield", "self_only": True},
        "copying": copying,
        **overrides,
    }
    ctx = EffectContext(state=game.state, controller=controller, source_oid=oid)
    for _ in execute_one(ctx, spec):
        pass


THEIRS = {"zone": "battlefield", "controller": "opponent", "types": ["Creature"]}


class TestTheSizeIsTheCopys:
    def test_the_copy_is_one_four(self, builder):
        game, mine, _ = board(builder)
        become_copy(game, mine, THEIRS, except_=ONE_FOUR)
        assert game.state.card_of(game.state.objects[mine]).name == "Test Lifegiver"
        assert pt(game, mine) == (1, 4)

    def test_without_the_exception_it_takes_the_copied_size(self, builder):
        game, mine, _ = board(builder)
        become_copy(game, mine, THEIRS)
        assert pt(game, mine) == (3, 3)

    def test_counters_start_from_the_one_four(self, builder):
        game, mine, _ = board(builder)
        become_copy(game, mine, THEIRS, except_=ONE_FOUR)
        add_counters(game.state, mine, "+1/+1", 1)
        assert pt(game, mine) == (2, 5)

    def test_it_wears_off_with_the_copy(self, builder):
        game, mine, _ = board(builder)
        become_copy(game, mine, THEIRS, except_=ONE_FOUR)
        clear_until_eot(game.state)
        assert pt(game, mine) == (1, 1)
        assert game.state.objects[mine].copying_power is None

    def test_a_new_copy_without_it_drops_the_old_size(self, builder):
        game, mine, _ = board(builder)
        become_copy(game, mine, THEIRS, except_=ONE_FOUR, duration="permanent")
        become_copy(game, mine, THEIRS, duration="permanent")
        assert pt(game, mine) == (3, 3)


class TestTheLoaderRefuses:
    def card(self, exception):
        ability = {
            "kind": "triggered",
            "text": "x",
            "trigger": {"event": "begin_combat", "controller": "you"},
            "effects": [
                {"op": "become_copy", "except_": exception,
                 "objects": {"zone": "battlefield", "self_only": True},
                 "copying": {**THEIRS, "count": 1}}
            ],
        }
        return {"id": "t_bad", "name": "Bad", "types": ["Creature"], "power": 1,
                "toughness": 1, "abilities": [ability]}

    @pytest.mark.parametrize(
        "exception",
        [{"power": 1}, {"toughness": 4}, {"power": -1, "toughness": 4},
         {"power": "1", "toughness": 4}, {"power": True, "toughness": 4}],
    )
    def test_a_half_or_malformed_size(self, exception):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(self.card(exception)))

    def test_the_whole_size_loads(self):
        compile_card(CardModel.model_validate(self.card(ONE_FOUR)))
