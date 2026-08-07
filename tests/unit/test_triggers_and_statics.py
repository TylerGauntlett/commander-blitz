"""Triggered abilities, static abilities and derived characteristics."""

from __future__ import annotations

from automtg.engine.characteristics import chars
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.objects import PLUS_ONE
from tests.conftest import action_for_card, find_action, oids_of, only_oid, pass_until


class TestTriggers:
    def test_enters_the_battlefield_trigger(self, builder):
        game = (
            builder()
            .hand(0, ["t_etb_draw"])
            .battlefield(0, ["island", "island", "island"])
            .library(0, ["forest", "forest", "forest"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_etb_draw"))
        assert len(game.state.players[0].hand) == 1

    def test_dies_trigger(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_dies_gain"])
            .hand(1, ["t_bolt"])
            .battlefield(1, ["mountain"])
            .build()
        )
        pass_until(game, lambda g: g.pending() and g.pending().player == 1, limit=800)
        bolt = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.targets and a.targets[0].kind == "object"
        )
        game.apply(bolt)
        assert not oids_of(game, "t_dies_gain", 0)
        assert game.state.players[0].life == 42

    def test_upkeep_trigger(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_upkeep_draw"])
            .library(0, ["forest", "forest", "forest", "forest"])
            .build()
        )
        before = len(game.state.players[0].hand)
        pass_until(game, lambda g: g.state.turn == 3, limit=800)
        assert len(game.state.players[0].hand) > before

    def test_landfall_trigger_adds_a_counter(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_landfall"])
            .hand(0, ["forest"])
            .build()
        )
        landfaller = only_oid(game, "t_landfall", 0)
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert game.state.objects[landfaller].counter(PLUS_ONE) == 1
        assert chars(game.state, landfaller).power == 2

    def test_play_a_land_trigger_draws(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_land_draw"])
            .hand(0, ["forest"])
            .library(0, ["island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert len(game.state.players[0].hand) == 1

    def test_eminence_style_trigger_works_from_the_command_zone(self, builder):
        game = (
            builder()
            .commander(0, ["t_cast_trigger"])
            .hand(0, ["t_bear"])
            .battlefield(0, ["forest", "forest"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        assert oids_of(game, "vampire_1_1_bw", 0)

    def test_a_trigger_only_fires_for_its_controller(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_land_draw"])
            .hand(1, ["forest"])
            .build()
        )
        pass_until(
            game,
            lambda g: g.state.active_player == 1
            and any(a.kind is ActionKind.PLAY_LAND for a in g.legal_actions()),
            limit=800,
        )
        watcher = only_oid(game, "t_land_draw", 0)
        events = game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        # Assert on the event log: apply() runs on to player 0's next turn, where
        # their draw step would muddy a hand-size comparison.
        assert not [
            e for e in events if e.type == "ability_triggered" and e.source == watcher
        ]

    def test_enters_with_x_counters(self, builder):
        game = (
            builder()
            .hand(0, ["t_x_spell"])
            .battlefield(0, ["forest", "forest", "forest", "forest"])
            .build()
        )
        cast = action_for_card(game, ActionKind.CAST, "t_x_spell")
        assert cast.x == 3
        game.apply(cast)
        hydra = only_oid(game, "t_x_spell", 0)
        assert game.state.objects[hydra].counter(PLUS_ONE) == 3
        assert chars(game.state, hydra).power == 3


class TestStaticAbilities:
    def test_anthem_pumps_your_creatures_only(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_anthem", "t_bear"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        mine = oids_of(game, "t_bear", 0)[0]
        theirs = oids_of(game, "t_bear", 1)[0]
        assert chars(game.state, mine).power == 3
        assert chars(game.state, theirs).power == 2

    def test_lord_excludes_itself(self, builder):
        game = builder().battlefield(0, ["t_lord", "t_bear"]).build()
        lord = only_oid(game, "t_lord", 0)
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, lord).power == 2
        assert chars(game.state, bear).power == 3

    def test_two_lords_stack(self, builder):
        game = builder().battlefield(0, ["t_lord", "t_lord", "t_bear"]).build()
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, bear).power == 4

    def test_keyword_grant(self, builder):
        game = builder().battlefield(0, ["t_flying_granter", "t_bear"]).build()
        bear = only_oid(game, "t_bear", 0)
        assert "flying" in chars(game.state, bear).keywords

    def test_static_stops_applying_when_its_source_leaves(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_anthem", "t_bear"])
            .hand(1, ["t_bolt"])
            .battlefield(1, ["mountain"])
            .build()
        )
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, bear).power == 3
        anthem = only_oid(game, "t_anthem", 0)
        from automtg.engine.zones import move_object

        move_object(game.state, anthem, Zone.GRAVEYARD)
        assert chars(game.state, bear).power == 2

    def test_counters_and_anthems_combine(self, builder):
        game = builder().battlefield(0, ["t_anthem", "t_bear"], counters={PLUS_ONE: 2}).build()
        bear = only_oid(game, "t_bear", 0)
        # 2/2 base, +1/+1 from the anthem, +2/+2 from counters.
        assert (chars(game.state, bear).power, chars(game.state, bear).toughness) == (5, 5)

    def test_characteristic_cache_invalidates(self, builder):
        game = builder().battlefield(0, ["t_bear"]).build()
        bear = only_oid(game, "t_bear", 0)
        assert chars(game.state, bear).power == 2
        from automtg.engine.primitives import add_counters

        add_counters(game.state, bear, PLUS_ONE, 3)
        assert chars(game.state, bear).power == 5


class TestUntilEndOfTurn:
    def test_pump_wears_off_at_cleanup(self, builder):
        game = (
            builder()
            .hand(0, ["t_pump_spell"])
            .battlefield(0, ["forest", "t_bear"])
            .build()
        )
        bear = only_oid(game, "t_bear", 0)
        game.apply(action_for_card(game, ActionKind.CAST, "t_pump_spell"))
        assert chars(game.state, bear).power == 5
        pass_until(game, lambda g: g.state.turn == 2, limit=800)
        assert chars(game.state, bear).power == 2

    def test_damage_clears_at_cleanup(self, builder):
        game = builder().battlefield(0, ["t_big"]).build()
        giant = only_oid(game, "t_big", 0)
        from automtg.engine.primitives import damage_permanent

        damage_permanent(game.state, giant, 3, None)
        assert game.state.objects[giant].damage == 3
        pass_until(game, lambda g: g.state.turn == 2, limit=800)
        assert game.state.objects[giant].damage == 0


class TestActivatedAbilities:
    def test_sacrifice_cost_asks_which_creature(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_sac_outlet", "t_bear", "t_flyer"])
            .build()
        )
        activate = find_action(game, ActionKind.ACTIVATE)
        game.apply(activate)
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        game.apply(find_action(game, ActionKind.CHOOSE, choice=0))
        pass_until(game, lambda g: g.state.players[0].life != 40, limit=50)
        assert game.state.players[0].life == 41
        assert len(game.state.creatures(0)) == 1

    def test_mana_abilities_are_not_offered_as_actions(self, builder):
        game = builder().battlefield(0, ["forest"]).hand(0, ["t_bear"]).build()
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE]

    def test_summoning_sick_creature_cannot_tap_for_mana(self, builder):
        from automtg.engine.costs import mana_sources

        game = builder().battlefield(0, ["t_dork"], sick=True).build(advance=False)
        assert mana_sources(game.state, 0) == []

    def test_a_settled_mana_dork_can_tap(self, builder):
        from automtg.engine.costs import mana_sources

        game = builder().battlefield(0, ["t_dork"]).build(advance=False)
        assert len(mana_sources(game.state, 0)) == 1
