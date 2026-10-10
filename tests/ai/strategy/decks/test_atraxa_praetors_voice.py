"""Atraxa ("Superfriends"): walkers before creatures, proliferate only when it grows something."""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.structs import TargetRef
from tests.conftest import find_action, only_oid, pass_until

DECK = "atraxa_praetors_voice"


def chosen(game, seat: int = 0):
    return HeuristicAgent(0).act(game, seat, game.legal_actions())


def card_of(game, action) -> str:
    return game.state.objects[action.source].def_id if action.source is not None else ""


class TestWalkersFirst:
    def test_a_planeswalker_comes_down_before_a_creature_of_the_same_cost(self, builder):
        game = (
            builder()
            .hand(0, ["oko_thief_of_crowns", "eternal_witness"])
            .battlefield(0, ["forest", "forest", "island"])
            .deck(0, DECK)
            .build()
        )
        assert card_of(game, chosen(game)) == "oko_thief_of_crowns"


class TestProliferate:
    def test_karn_s_bastion_does_not_proliferate_an_empty_board(self, builder):
        game = builder().battlefield(0, ["karn_s_bastion"] + ["forest"] * 4).deck(0, DECK).build()
        action = chosen(game)
        assert not (action.kind is ActionKind.ACTIVATE and action.ability_index == 1)

    def test_karn_s_bastion_proliferates_a_walker(self, builder):
        game = (
            builder()
            .battlefield(0, ["karn_s_bastion"] + ["forest"] * 4)
            .battlefield(0, ["ajani_the_greathearted"], counters={"loyalty": 5})
            .deck(0, DECK)
            .build()
        )
        # As if Ajani had already used his loyalty this turn: the land is what is left.
        actions = [
            a
            for a in game.legal_actions()
            if not (a.source is not None and card_of(game, a) == "ajani_the_greathearted")
        ]
        action = HeuristicAgent(0).act(game, 0, actions)
        assert card_of(game, action) == "karn_s_bastion"
        assert action.ability_index == 1


class TestJaceUltimate:
    def build(self, builder, library: int):
        return (
            builder(players=3)
            .battlefield(0, ["jace_memory_adept"], counters={"loyalty": 8})
            .library(0, ["island"] * 15)
            .library(1, ["island"] * library)
            .library(2, ["island"] * library)
            .deck(0, DECK)
            .build()
        )

    def test_twenty_cards_go_only_at_libraries_they_empty(self, builder):
        game = self.build(builder, library=12)
        action = chosen(game)
        assert action.ability_index == 2
        assert sorted(ref.id for ref in action.targets) == [1, 2]

    def test_never_at_a_deep_library_and_never_at_ourselves(self, builder):
        game = self.build(builder, library=40)
        action = chosen(game)
        assert action.ability_index != 2


class TestTeferisProtection:
    def test_it_is_held_in_the_main_phase(self, builder):
        game = (
            builder().hand(0, ["teferi_s_protection"]).battlefield(0, ["plains"] * 3).deck(0, DECK).build()
        )
        assert chosen(game).kind is ActionKind.PASS

    def test_it_answers_the_swing_that_would_kill_us(self, builder):
        game = (
            builder()
            .hand(0, ["teferi_s_protection"])
            .battlefield(0, ["plains"] * 3)
            .battlefield(1, ["t_big"])
            .active(1)
            .life(0, 6)
            .deck(0, DECK)
            .build()
        )
        pass_until(game, lambda g: g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        big = only_oid(game, "t_big", 1)
        game.apply(find_action(game, ActionKind.ADD_ATTACKER, source=big, targets=(TargetRef.player(0),)))
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game,
            lambda g: g.state.step is Step.DECLARE_BLOCKERS
            and g.pending().kind is DecisionKind.PRIORITY
            and g.pending().player == 0,
        )
        assert card_of(game, chosen(game)) == "teferi_s_protection"
