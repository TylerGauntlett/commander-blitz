""""As long as you're the monarch, damage doesn't cause you to lose life."

Archon of Coronation, in the Obscura Operation precon. 120.3a makes the loss of
life a *result* of damage dealt to a player, and this static removes that one
result. The card's own reminder text says why that is not a prevention: "(Damage
still causes the monarch to pass.)" The damage is dealt, so lifelink gains,
`DAMAGE_DEALT` fires and the crown can still be taken. `prevent_damage` is the
near miss and stops every one of those; `replace_life_loss` would reach a
`lose_life` too, which the printed word "damage" leaves alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import become_monarch, damage_player, lose_life
from tests.conftest import only_oid, static_probe

ARCHON = "t_coronation_archon"
LIFELINKER = "t_lifelinker"
BEAR = "t_bear"


def position(builder, *, monarch: int | None = 0):
    game = (
        builder(players=2)
        .battlefield(0, [ARCHON])
        .battlefield(1, [LIFELINKER, BEAR])
        .build(advance=False)
    )
    if monarch is not None:
        become_monarch(game.state, monarch)
    return game


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


class TestAsTheMonarchDamageCostsNoLife:
    def test_damage_leaves_your_life_where_it_was(self, builder):
        game = position(builder)
        before = life(game)
        damage_player(game.state, 0, 7, only_oid(game, BEAR, 1))
        assert life(game) == before

    def test_the_damage_is_still_dealt(self, builder):
        """Lifelink gains what was dealt, which a prevention would not allow."""
        game = position(builder)
        before = life(game, 1)
        dealt = damage_player(game.state, 0, 3, only_oid(game, LIFELINKER, 1))
        assert dealt == 3
        assert life(game, 1) == before + 3

    def test_no_life_lost_event_fires(self, builder):
        game = position(builder)
        start = len(game.state.events)
        damage_player(game.state, 0, 3, only_oid(game, BEAR, 1))
        kinds = [e.type for e in game.state.events[start:]]
        assert EventType.DAMAGE_DEALT in kinds
        assert EventType.LIFE_LOST not in kinds

    def test_a_loss_that_is_not_damage_walks_past_it(self, builder):
        game = position(builder)
        before = life(game)
        lose_life(game.state, 0, 4)
        assert life(game) == before - 4


class TestOnlyTheMonarchIsSpared:
    def test_not_the_monarch_damage_costs_life(self, builder):
        game = position(builder, monarch=None)
        before = life(game)
        damage_player(game.state, 0, 5, only_oid(game, BEAR, 1))
        assert life(game) == before - 5

    def test_losing_the_crown_loses_the_protection(self, builder):
        game = position(builder)
        become_monarch(game.state, 1)
        before = life(game)
        damage_player(game.state, 0, 5, only_oid(game, BEAR, 1))
        assert life(game) == before - 5

    def test_it_names_its_seat(self, builder):
        """The opponent is not spared, even while you hold the crown."""
        game = position(builder)
        before = life(game, 1)
        damage_player(game.state, 1, 5, None)
        assert life(game, 1) == before - 5


class TestTheLoaderRefuses:
    @pytest.mark.parametrize(
        "extra",
        [{"amount": 1}, {"affects": {"controller": "you", "types": ["Creature"]}}],
    )
    def test_a_number_or_a_permanent_filter(self, extra):
        static = {"effect": "damage_doesnt_cause_life_loss", "affects_player": "you", **extra}
        with pytest.raises(DslError, match="damage_doesnt_cause_life_loss"):
            compile_card(CardModel.model_validate(static_probe(static)))

    def test_the_printed_shape_loads(self):
        static = {
            "effect": "damage_doesnt_cause_life_loss",
            "affects_player": "you",
            "condition": {"is_monarch": "you"},
        }
        compile_card(CardModel.model_validate(static_probe(static)))
