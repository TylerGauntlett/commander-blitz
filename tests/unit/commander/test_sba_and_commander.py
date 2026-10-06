"""State-based actions, the commander rules, and multiplayer."""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, Zone
from automtg.engine.objects import MINUS_ONE, PLUS_ONE
from automtg.engine.primitives import create_token, damage_permanent
from automtg.engine.sba import run as run_sba
from automtg.engine.zones import move_object
from tests.conftest import action_for_card, oids_of, only_oid


class TestStateBasedActions:
    def test_lethal_damage_destroys(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build(advance=False)
        bear = only_oid(game, "t_bear", 0)
        damage_permanent(game.state, bear, 2, None)
        run_sba(game.state)
        assert not oids_of(game, "t_bear", 0)

    def test_sublethal_damage_does_not_destroy(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build(advance=False)
        bear = only_oid(game, "t_bear", 0)
        damage_permanent(game.state, bear, 1, None)
        run_sba(game.state)
        assert oids_of(game, "t_bear", 0)

    def test_zero_toughness_dies_even_when_indestructible(self, builder):
        game = builder().battlefield(0, ["t_indestructible"]).build(advance=False)
        oid = only_oid(game, "t_indestructible", 0)
        game.state.objects[oid].add_counter(MINUS_ONE, 2)
        game.state.bump_chars()
        run_sba(game.state)
        assert not oids_of(game, "t_indestructible", 0)

    def test_plus_and_minus_counters_annihilate(self, builder):
        game = builder().battlefield(0, ["t_big"]).build(advance=False)
        giant = only_oid(game, "t_big", 0)
        game.state.objects[giant].add_counter(PLUS_ONE, 3)
        game.state.objects[giant].add_counter(MINUS_ONE, 1)
        game.state.bump_chars()
        run_sba(game.state)
        obj = game.state.objects[giant]
        assert obj.counter(PLUS_ONE) == 2
        assert obj.counter(MINUS_ONE) == 0
        assert chars(game.state, giant).power == 8

    def test_a_token_that_leaves_the_battlefield_ceases_to_exist(self, builder):
        game = builder().build(advance=False)
        (token,) = create_token(game.state, "vampire_1_1_bw", 0, 1)
        move_object(game.state, token, Zone.GRAVEYARD)
        run_sba(game.state)
        assert token not in game.state.objects
        assert token not in game.state.players[0].graveyard

    def test_legend_rule_keeps_the_newest_copy(self, builder):
        game = builder().battlefield(0, ["t_legend", "t_legend"]).build(advance=False)
        first, second = oids_of(game, "t_legend", 0)
        run_sba(game.state)
        survivors = oids_of(game, "t_legend", 0)
        assert survivors == [second]
        assert first in game.state.players[0].graveyard

    def test_legend_rule_is_per_player(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_legend"])
            .battlefield(1, ["t_legend"])
            .build(advance=False)
        )
        run_sba(game.state)
        assert len(oids_of(game, "t_legend")) == 2


class TestCommander:
    def test_commander_can_be_cast_from_the_command_zone(self, builder):
        game = (
            builder()
            .commander(0, ["t_commander"])
            .battlefield(0, ["forest", "forest", "island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_commander"))
        assert oids_of(game, "t_commander", 0)

    def test_commander_tax_increases_by_two_per_cast(self, builder):
        game = (
            builder()
            .commander(0, ["t_commander"])
            .battlefield(0, ["forest", "forest", "island", "island"])
            .build()
        )
        oid = game.state.players[0].command[0]
        game.apply(action_for_card(game, ActionKind.CAST, "t_commander"))
        assert game.state.players[0].commander_tax[oid] == 1

    def test_a_dead_commander_goes_to_the_command_zone(self, builder):
        game = builder().commander(0, ["t_commander"]).build(advance=False)
        oid = game.state.players[0].command[0]
        move_object(game.state, oid, Zone.BATTLEFIELD)
        assert oid in game.state.battlefield
        move_object(game.state, oid, Zone.GRAVEYARD)
        assert oid in game.state.players[0].command
        assert oid not in game.state.players[0].graveyard

    def test_exiling_a_commander_also_sends_it_to_the_command_zone(self, builder):
        game = builder().commander(0, ["t_commander"]).build(advance=False)
        oid = game.state.players[0].command[0]
        move_object(game.state, oid, Zone.BATTLEFIELD)
        move_object(game.state, oid, Zone.EXILE)
        assert oid in game.state.players[0].command

    def test_recast_commander_costs_more(self, builder):
        game = (
            builder()
            .commander(0, ["t_commander"])
            .battlefield(0, ["forest"] * 3 + ["island"] * 3)
            .build()
        )
        oid = game.state.players[0].command[0]
        game.state.players[0].commander_tax[oid] = 1
        action = action_for_card(game, ActionKind.CAST, "t_commander")
        assert "+2" in (action.label or "")


class TestMultiplayer:
    def test_four_player_turn_order(self, builder):
        game = builder(players=4).hand(0, ["forest"]).build()
        order = []
        for _ in range(40):
            if game.over or len(order) >= 5:
                break
            if game.state.active_player not in order[-1:]:
                order.append(game.state.active_player)
            decision = game.pending()
            if decision is None:
                break
            game.apply(game.legal_actions()[0])
        assert order[:4] == [0, 1, 2, 3]

    def test_all_players_start_at_forty_life(self, builder):
        game = builder(players=4).build(advance=False)
        assert [p.life for p in game.state.players] == [40] * 4

    def test_eliminating_a_player_exiles_their_permanents(self, builder):
        game = builder(players=4).battlefield(2, ["t_bear"]).build(advance=False)
        bear = only_oid(game, "t_bear", 2)
        game.state.players[2].life = 0
        run_sba(game.state)
        assert game.state.players[2].has_lost
        assert bear not in game.state.battlefield
        assert not game.over  # three players remain

    def test_the_game_ends_when_one_player_remains(self, builder):
        game = builder(players=4).build(advance=False)
        for pid in (1, 2, 3):
            game.state.players[pid].life = 0
        run_sba(game.state)
        assert game.over
        assert game.winners == [0]

    def test_turn_order_skips_eliminated_players(self, builder):
        game = builder(players=4).build(advance=False)
        game.state.players[1].life = 0
        run_sba(game.state)
        assert game.state.turn_order() == [0, 2, 3]

    def test_a_defeated_player_is_not_a_legal_attack_target(self, builder):
        from automtg.engine.combat import legal_defenders

        game = builder(players=4).build(advance=False)
        game.state.players[1].life = 0
        run_sba(game.state)
        assert legal_defenders(game.state) == [2, 3]


class TestLossConditions:
    def test_commander_damage_threshold_is_tracked_per_source(self, builder):
        game = builder(players=4).build(advance=False)
        game.state.players[0].commander_damage_taken = {1: 20, 2: 20}
        run_sba(game.state)
        assert not game.state.players[0].has_lost
        game.state.players[0].commander_damage_taken[1] = 21
        run_sba(game.state)
        assert game.state.players[0].has_lost

    def test_empty_library_only_loses_on_a_draw(self, builder):
        game = builder().library(0, []).build(advance=False)
        run_sba(game.state)
        assert not game.state.players[0].has_lost
        from automtg.engine.primitives import draw_cards

        draw_cards(game.state, 0, 1)
        run_sba(game.state)
        assert game.state.players[0].has_lost
