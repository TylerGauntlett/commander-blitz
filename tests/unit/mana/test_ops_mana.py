"""The three mana ops, called directly.

``ops_mana.py`` was the least-covered module in the rules engine, and the reason
is structural: a real mana ability never reaches it -- ``costs.activate_mana_ability``
pays the folded tuple out itself -- so the module only runs for a *triggered*
ability or a spell that adds mana, which the shipped pool rarely does. These call
the ops the way ``execute_one`` would, with a real board underneath, so every
branch is exercised at least once (TECH_DEBT CG-06).
"""

from __future__ import annotations

from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.ops_mana import (
    mana_string,
    op_add_mana,
    op_add_mana_per,
    op_extra_land_drop,
)
from tests.conftest import oids_of

GREEN = 4  # index of {G} in the six-tuple
RED = 3


def pool(game, pid: int = 0) -> tuple[int, ...]:
    return tuple(game.state.players[pid].mana_pool.amounts)


def ctx(game, source_oid: int | None = None) -> EffectContext:
    return EffectContext(state=game.state, controller=0, source_oid=source_oid)


class TestAddMana:
    def test_adds_the_printed_symbols_to_the_controller(self, builder):
        game = builder(players=2).build()
        assert sum(pool(game)) == 0
        op_add_mana(ctx(game), {"op": "add_mana", "mana": "{G}{G}", "player": "you"})
        assert pool(game)[GREEN] == 2
        assert sum(pool(game)) == 2
        assert sum(pool(game, 1)) == 0

    def test_an_empty_production_adds_nothing_and_says_nothing(self, builder):
        game = builder(players=2).build()
        before = len(game.state.events)
        op_add_mana(ctx(game), {"op": "add_mana", "mana": "", "player": "you"})
        assert sum(pool(game)) == 0
        assert len(game.state.events) == before

    def test_each_selected_player_gets_their_own(self, builder):
        game = builder(players=2).build()
        op_add_mana(ctx(game), {"op": "add_mana", "mana": "{G}", "player": "each_player"})
        assert pool(game, 0)[GREEN] == 1
        assert pool(game, 1)[GREEN] == 1


class TestManaString:
    def test_a_literal_is_returned_as_printed(self, builder):
        game = builder(players=2).build()
        assert mana_string(ctx(game), {"mana": "{G}{U}"}) == "{G}{U}"

    def test_the_chosen_colour_of_the_source_is_substituted(self, builder):
        game = builder(players=2).battlefield(0, ["t_bear"]).build()
        bear = oids_of(game, "t_bear")[0]
        game.state.objects[bear].chosen_color = "R"
        produced = mana_string(ctx(game, bear), {"mana": {"chosen_color_of": "self"}})
        assert "R" in produced
        op_add_mana(ctx(game, bear), {"op": "add_mana", "mana": {"chosen_color_of": "self"}})
        assert pool(game)[RED] == 1

    def test_a_source_that_chose_nothing_produces_nothing(self, builder):
        # No decision is asked here, which is what keeps `add_mana` legal inside
        # a mana ability (605.1a): the ability simply makes nothing.
        game = builder(players=2).battlefield(0, ["t_bear"]).build()
        bear = oids_of(game, "t_bear")[0]
        assert mana_string(ctx(game, bear), {"mana": {"chosen_color_of": "self"}}) == ""
        op_add_mana(ctx(game, bear), {"op": "add_mana", "mana": {"chosen_color_of": "self"}})
        assert sum(pool(game)) == 0


class TestAddManaPer:
    def test_one_unit_per_matching_permanent(self, builder):
        game = builder(players=2).battlefield(0, ["forest", "forest", "forest"]).build()
        op_add_mana_per(
            ctx(game),
            {
                "op": "add_mana_per",
                "mana": "{G}",
                "player": "you",
                "per": {"zone": "battlefield", "controller": "you", "subtypes": ["Forest"]},
            },
        )
        assert pool(game)[GREEN] == 3

    def test_nothing_matching_adds_nothing(self, builder):
        game = builder(players=2).battlefield(0, ["forest"]).build()
        before = len(game.state.events)
        op_add_mana_per(
            ctx(game),
            {
                "op": "add_mana_per",
                "mana": "{G}",
                "player": "you",
                "per": {"zone": "battlefield", "controller": "you", "subtypes": ["Island"]},
            },
        )
        assert sum(pool(game)) == 0
        assert len(game.state.events) == before


class TestExtraLandDrop:
    def test_defaults_to_one_more_land_this_turn(self, builder):
        game = builder(players=2).build()
        before = game.state.players[0].extra_land_drops
        op_extra_land_drop(ctx(game), {"op": "extra_land_drop", "player": "you"})
        assert game.state.players[0].extra_land_drops == before + 1

    def test_takes_an_amount(self, builder):
        game = builder(players=2).build()
        before = game.state.players[0].extra_land_drops
        op_extra_land_drop(
            ctx(game), {"op": "extra_land_drop", "player": "you", "amount": {"const": 2}}
        )
        assert game.state.players[0].extra_land_drops == before + 2
        assert game.state.players[1].extra_land_drops == 0
