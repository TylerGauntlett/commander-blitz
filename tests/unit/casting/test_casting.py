"""Playing lands, casting spells, the stack, and priority."""

from __future__ import annotations

import pytest

from commanderblitz.engine.actions import Action
from commanderblitz.engine.costs import land_drops_available
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import IllegalActionError
from tests.conftest import (
    _default_answer,
    action_for_card,
    find_action,
    only_oid,
    pass_until,
)


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

    def test_every_copy_of_a_land_in_hand_is_playable(self, builder):
        """One action per land *object*, not per land name.

        Deduplicating by card id offered a single "Play Forest" no matter how
        many you held, and the client keys playability by object id -- so the
        second and third Forest rendered dimmed and undraggable.
        """
        game = builder().hand(0, ["forest", "forest", "forest"]).build()
        lands = [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]
        assert len(lands) == 3
        assert sorted(a.source for a in lands) == sorted(game.state.players[0].hand)

    def test_a_mixed_hand_offers_every_land(self, builder):
        """The reported symptom: a hand of basics offered exactly two actions."""
        game = builder().hand(0, ["forest", "island", "forest", "island", "forest"]).build()
        lands = [a for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]
        assert len(lands) == 5

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

    def test_both_copies_of_a_spell_are_castable(self, builder):
        """Same dedupe defect as the land drop, same consequence in the UI."""
        game = (
            builder()
            .hand(0, ["t_bear", "t_bear"])
            .battlefield(0, ["forest", "forest"])
            .build()
        )
        casts = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "t_bear"
        ]
        assert len(casts) == 2
        assert len({a.source for a in casts}) == 2

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


class TestPriorityStops:
    """Which priority windows a player is actually asked about.

    Eleven of the thirteen steps grant priority, and instants are legal in all
    of them, so one instant in hand used to mean eleven forced Pass clicks per
    turn -- on every player's turn. `auto_pass` keeps the windows where passing
    is a real choice and skips the rest.
    """

    @staticmethod
    def _windows(builder, *, auto_pass: bool, full_control: bool = False):
        """Every step player 0 is offered priority in, over one full turn."""
        game = (
            builder()
            .hand(0, ["t_pump_spell"])
            .battlefield(0, ["forest", "forest", "forest", "t_bear"])
            .build(advance=False)
        )
        game.state.players[0].auto_pass = auto_pass
        game.state.players[0].full_control = full_control
        game._advance()

        seen = []
        for _ in range(800):
            if game.over or game.state.turn >= 2:
                break
            decision = game.pending()
            if decision is None:
                break
            if decision.kind is DecisionKind.PRIORITY and decision.player == 0:
                seen.append(game.state.step)
            game.apply(_default_answer(game, decision))
        return seen

    def test_without_auto_pass_every_step_asks(self, builder):
        steps = self._windows(builder, auto_pass=False)
        # The regression: an instant in hand defeats the "only Pass is legal"
        # guard, so steps with nothing to respond to stop anyway. (The builder
        # opens in turn 1's precombat main, so upkeep is already behind us.)
        assert Step.BEGIN_COMBAT in steps
        assert Step.END_OF_COMBAT in steps
        assert Step.END_STEP in steps

    def test_auto_pass_keeps_only_the_meaningful_windows(self, builder):
        steps = set(self._windows(builder, auto_pass=True))
        assert steps <= {
            Step.PRECOMBAT_MAIN,
            Step.POSTCOMBAT_MAIN,
            Step.DECLARE_BLOCKERS,
        }
        # Your own main phase is a stop: it is the sorcery-speed window.
        assert Step.PRECOMBAT_MAIN in steps

    def test_full_control_puts_every_window_back(self, builder):
        smart = self._windows(builder, auto_pass=True)
        everything = self._windows(builder, auto_pass=True, full_control=True)
        assert len(everything) > len(smart)
        assert Step.BEGIN_COMBAT in everything
        assert Step.END_STEP in everything

    def test_a_response_on_the_stack_always_stops(self, builder):
        """Auto-pass must never skip past something you could respond to."""
        game = (
            builder()
            .hand(0, ["t_pump_spell"])
            .battlefield(0, ["forest", "forest", "forest", "t_bear"])
            .hand(1, ["t_bear"])
            .battlefield(1, ["forest", "forest"])
            .build(advance=False)
        )
        game.state.players[0].auto_pass = True
        game._advance()
        pass_until(game, lambda g: g.pending() and g.pending().player == 1)
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        decision = game.pending()
        assert decision is not None
        assert decision.kind is DecisionKind.PRIORITY
        assert decision.player == 0
        assert game.state.stack

    @staticmethod
    def _opponent_casts_a_bear(builder):
        """Player 1's main phase; player 0 holds removal and the mana for it.

        Player 1 casts a bear. While it is on the stack removal has nothing to
        target, so that window is (correctly) skipped and the bear resolves.
        """
        game = (
            builder()
            .hand(0, ["t_removal"])
            .battlefield(0, ["plains"])
            .hand(1, ["t_bear"])
            .battlefield(1, ["forest", "forest"])
            .active(1)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game.state.players[0].auto_pass = True
        game._advance()
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        return game

    def test_the_window_after_a_resolution_stops(self, builder):
        """The playtest report: mana held up on an opponent's turn could answer
        their spells but never the creatures those spells became, because the
        stack was empty again by the time the creature was there to target."""
        game = self._opponent_casts_a_bear(builder)
        pass_until(game, lambda g: g.pending() and g.pending().player == 0)

        bear = only_oid(game, "t_bear", 1)
        assert game.state.active_player == 1
        assert game.state.step is Step.PRECOMBAT_MAIN
        assert not game.state.stack

        game.apply(action_for_card(game, ActionKind.CAST, "t_removal"))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[bear].zone is Zone.EXILE

    def test_and_it_ends_with_the_step(self, builder):
        """Passing it lets the turn move on: the opponent's later steps, with
        nothing resolving in them, are skipped as before."""
        game = self._opponent_casts_a_bear(builder)
        pass_until(game, lambda g: g.pending() and g.pending().player == 0)
        game.apply(find_action(game, ActionKind.PASS))

        stops = []
        for _ in range(200):
            decision = game.pending()
            if decision is None or game.state.active_player != 1:
                break
            if decision.kind is DecisionKind.PRIORITY and decision.player == 0:
                stops.append(game.state.step)
            game.apply(_default_answer(game, decision))
        assert set(stops) <= {Step.DECLARE_BLOCKERS}


class TestManaThatUnlocksASpell:
    """The playtest report: Treasure and Master of Dark Rites make mana the
    payment solver cannot tap, so a spell that needs it is not offered -- and
    a window of Pass plus mana abilities read as empty, so main phase went
    straight on to combat with the spell still castable."""

    @staticmethod
    def _game(builder, hand, *, auto_pass=True, active=0):
        game = (
            builder()
            .hand(0, hand)
            .battlefield(0, ["forest", "treasure_token"])
            .active(active)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game.state.players[0].auto_pass = auto_pass
        game._advance()
        return game

    @staticmethod
    def _stopped_in_own_main(game) -> bool:
        decision = game.pending()
        return (
            decision is not None
            and decision.kind is DecisionKind.PRIORITY
            and decision.player == 0
            and game.state.active_player == 0
            and game.state.step is Step.PRECOMBAT_MAIN
        )

    def test_main_phase_stops_when_the_treasure_pays_for_a_spell(self, builder):
        game = self._game(builder, ["t_bear"])
        assert self._stopped_in_own_main(game)
        # Not castable yet: the Forest alone is one mana short.
        assert not [a for a in game.legal_actions() if a.kind is ActionKind.CAST]

        treasure = only_oid(game, "treasure_token", 0)
        green = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == treasure and "G" in a.label
        )
        game.apply(green)
        game.apply(action_for_card(game, ActionKind.CAST, "t_bear"))
        pass_until(game, lambda g: not g.state.stack)
        assert game.state.objects[only_oid(game, "t_bear", 0)].zone is Zone.BATTLEFIELD

    def test_no_stop_when_nothing_in_hand_needs_the_mana(self, builder):
        game = self._game(builder, [])
        assert not self._stopped_in_own_main(game)

    def test_an_ai_seat_is_not_stopped(self, builder):
        """``auto_pass`` is off for AI seats, and the heuristic agent would
        sacrifice the Treasure for nothing if offered the window."""
        game = self._game(builder, ["t_bear"], auto_pass=False)
        assert not self._stopped_in_own_main(game)

    def test_not_on_an_opponents_turn(self, builder):
        game = self._game(builder, ["t_bear"], active=1)
        decision = game.pending()
        assert not (
            decision is not None
            and decision.player == 0
            and game.state.active_player == 1
            and game.state.step is Step.PRECOMBAT_MAIN
        )


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
