"""Playing lands, casting spells, the stack, and priority."""

from __future__ import annotations

import pytest

from automtg.engine.actions import Action
from automtg.engine.costs import land_drops_available
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import IllegalActionError
from tests.conftest import action_for_card, find_action, only_oid, pass_until


class TestLandDrops:
    def test_play_a_land(self, builder):
        game = builder().hand(0, ["forest"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert only_oid(game, "forest", 0)
        assert game.state.players[0].lands_played == 1

    def test_only_one_land_per_turn(self, builder):
        game = builder().hand(0, ["forest", "island"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        # The turn has already rolled over (nothing else was possible), so assert
        # on the land-drop budget rather than on the offered actions.
        assert land_drops_available(game.state, 0) == 0

    def test_a_static_ability_grants_an_extra_land_drop(self, builder):
        game = (
            builder()
            .hand(0, ["forest", "island"])
            .battlefield(0, ["t_extra_land"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]

    def test_lands_do_not_use_the_stack(self, builder):
        game = builder().hand(0, ["forest"]).build()
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert game.state.stack == []

    def test_cannot_play_a_land_on_an_opponents_turn(self, builder):
        """Give player 1 a reason to hold priority during player 0's turn."""
        game = (
            builder()
            .hand(0, ["t_bear"])
            .battlefield(0, ["forest", "forest"])
            .hand(1, ["forest", "t_counterspell"])
            .battlefield(1, ["island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        assert game.pending().player == 1
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]


class TestCasting:
    def test_creature_resolves_onto_the_battlefield(self, builder):
        game = (
            builder()
            .hand(0, ["t_bear"])
            .battlefield(0, ["forest", "forest"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        assert only_oid(game, "t_bear", 0)

    def test_a_spell_sits_on_the_stack_while_an_opponent_can_respond(self, builder):
        game = (
            builder()
            .hand(0, ["t_bear"])
            .battlefield(0, ["forest", "forest"])
            .hand(1, ["t_counterspell"])
            .battlefield(1, ["island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        assert len(game.state.stack) == 1
        assert game.pending().player == 1

    def test_casting_taps_lands(self, builder):
        game = (
            builder()
            .hand(0, ["t_bear"])
            .battlefield(0, ["forest", "forest"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        tapped = [o for o in game.state.battlefield_objects(0) if o.tapped]
        assert len(tapped) == 2

    def test_cannot_cast_without_mana(self, builder):
        game = builder().hand(0, ["t_bear"]).battlefield(0, ["forest"]).build()
        with pytest.raises(AssertionError):
            action_for_card(game, ActionKind.CAST, "t_bear")

    def test_wrong_colour_is_not_castable(self, builder):
        game = builder().hand(0, ["t_bear"]).battlefield(0, ["island", "island"]).build()
        with pytest.raises(AssertionError):
            action_for_card(game, ActionKind.CAST, "t_bear")

    def test_sorcery_speed_blocked_with_stack_non_empty(self, builder):
        """The pump keeps player 0 on priority so the sorcery's absence is observable."""
        game = (
            builder()
            .hand(0, ["t_bear", "t_draw_spell", "t_pump_spell"])
            .battlefield(
                0, ["forest", "forest", "forest", "island", "island", "island", "t_bear"]
            )
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        assert len(game.state.stack) == 1  # player 0 retains priority
        action_for_card(game, ActionKind.CAST, "t_pump_spell")  # instant: still offered
        with pytest.raises(AssertionError):
            action_for_card(game, ActionKind.CAST, "t_draw_spell")

    def test_auto_payment_keeps_scarce_colours_available(self, builder):
        """Paying generic costs must not strand the only source of a colour."""
        game = (
            builder()
            .hand(0, ["t_draw_spell", "t_pump_spell"])
            .battlefield(0, ["forest", "island", "island", "island", "t_bear"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_draw_spell"))
        forest = only_oid(game, "forest", 0)
        assert not game.state.objects[forest].tapped
        action_for_card(game, ActionKind.CAST, "t_pump_spell")

    def test_sorcery_goes_to_the_graveyard(self, builder):
        game = (
            builder()
            .hand(0, ["t_draw_spell"])
            .battlefield(0, ["island", "island", "island"])
            .library(0, ["forest", "forest", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_draw_spell"))
        pass_until(game, lambda g: not g.state.stack)
        assert [
            game.state.objects[o].def_id for o in game.state.players[0].graveyard
        ] == ["t_draw_spell"]
        assert len(game.state.players[0].hand) == 2

    def test_illegal_action_is_rejected(self, builder):
        game = builder().hand(0, ["forest"]).build()
        with pytest.raises(IllegalActionError):
            game.apply(Action(kind=ActionKind.PLAY_LAND, source=999))


class TestStackAndPriority:
    def test_a_response_goes_on_top_of_the_stack(self, builder):
        game = (
            builder()
            .hand(0, ["t_bear", "t_pump_spell"])
            .hand(1, ["t_counterspell"])
            .battlefield(0, ["forest", "forest", "forest", "t_bear"])
            .battlefield(1, ["island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        game.apply(find_action(game, ActionKind.PASS))  # player 0 declines to respond
        game.apply(action_for_card(game, ActionKind.CAST, "t_counterspell"))
        assert [item.def_id for item in game.state.stack] == ["t_bear", "t_counterspell"]

    def test_counterspell_sends_the_creature_to_the_graveyard(self, builder):
        game = (
            builder()
            .hand(0, ["t_bear"])
            .hand(1, ["t_counterspell"])
            .battlefield(0, ["forest", "forest"])
            .battlefield(1, ["island", "island"])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        game.apply(action_for_card(game, ActionKind.CAST, "t_counterspell"))
        pass_until(game, lambda g: not g.state.stack)
        assert not [o for o in game.state.battlefield_objects(0) if o.def_id == "t_bear"]
        assert "t_bear" in [
            game.state.objects[o].def_id for o in game.state.players[0].graveyard
        ]

    def test_a_spell_with_no_legal_target_fizzles(self, builder):
        """Bolt the only creature, then remove it in response: the bolt is countered."""
        game = (
            builder()
            .hand(0, ["t_bolt"])
            .hand(1, ["t_removal"])
            .battlefield(0, ["mountain"])
            .battlefield(1, ["plains", "t_bear"])
            .build()
        )
        bolt = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.targets and a.targets[0].kind == "object"
        )
        game.apply(bolt)
        removal = action_for_card(game, ActionKind.CAST, "t_removal")
        game.apply(removal)
        pass_until(game, lambda g: not g.state.stack)
        events = [e.type for e in game.state.events]
        assert "spell_fizzled" in events


class TestTurnStructure:
    def test_turn_walks_through_every_step(self, builder):
        """Auto-pass skips *decisions*, not steps -- the event log proves it."""
        game = builder().build()
        pass_until(game, lambda g: g.state.turn == 2, limit=800)
        stepped = {
            e.data.get("step") for e in game.state.events if e.type == "step_ended"
        }
        for name in ("PRECOMBAT_MAIN", "DECLARE_ATTACKERS", "END_STEP", "CLEANUP"):
            assert name in stepped

    def test_active_player_alternates(self, builder):
        game = builder().hand(0, ["forest"]).hand(1, ["forest"]).build()
        assert game.state.turn == 1
        first = game.state.active_player
        pass_until(game, lambda g: g.state.turn == 2, limit=800)
        assert game.state.active_player != first

    def test_starting_player_skips_the_first_draw_in_a_duel(self, builder):
        game = builder().build()
        assert len(game.state.players[0].hand) == 0
        pass_until(game, lambda g: g.state.step is Step.PRECOMBAT_MAIN and g.state.turn == 2)
        # Player 1's first turn is turn 2 and they do draw.
        assert len(game.state.players[1].hand) == 1

    def test_mana_pool_empties_between_steps(self, builder):
        game = builder().battlefield(0, ["forest"]).build()
        game.state.players[0].mana_pool.add("G", 3)
        pass_until(game, lambda g: g.state.step is Step.END_STEP)
        assert game.state.players[0].mana_pool.total() == 0

    def test_cleanup_discards_down_to_seven(self, builder):
        game = (
            builder()
            .hand(0, ["forest"] * 9)
            .build()
        )
        pass_until(game, lambda g: g.state.turn == 2, limit=800)
        assert len(game.state.players[0].hand) <= 7


class TestGameEnd:
    def test_zero_life_loses(self, builder):
        game = builder().life(1, 0).build()
        assert game.over
        assert game.winners == [0]

    def test_drawing_from_an_empty_library_loses(self, builder):
        game = builder().library(1, []).build()
        pass_until(game, lambda g: g.over, limit=800)
        assert game.over
        assert game.winners == [0]

    def test_turn_cap_is_a_draw(self, builder):
        game = builder().max_turns(2).build()
        pass_until(game, lambda g: g.over, limit=2000)
        assert game.over
        assert game.state.result == "draw"


class TestZones:
    def test_objects_move_between_zones_exactly_once(self, builder):
        game = builder().hand(0, ["forest"]).build()
        oid = game.state.players[0].hand[0]
        game.apply(action_for_card(game, ActionKind.PLAY_LAND, "forest"))
        assert game.state.objects[oid].zone is Zone.BATTLEFIELD
        assert oid not in game.state.players[0].hand
        assert game.state.battlefield.count(oid) == 1

    def test_decision_kind_is_priority_by_default(self, builder):
        game = builder().build()
        assert game.pending().kind is DecisionKind.PRIORITY
