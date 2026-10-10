"""The archetypes, each in the one position that shows what it is for.

Pinned with an explicit ``HeuristicAgent(strategy=...)`` rather than a deck id,
so these say what an archetype does whatever deck later chooses it. The deck
modules' own tests (``decks/``) cover the plans built on top.
"""

from __future__ import annotations

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.ai.strategy import Combo, DeckPlan, DefaultStrategy
from commanderblitz.ai.strategy.archetypes import Aristocrats, GoWide, Mill, Voltron
from commanderblitz.engine.enums import ActionKind, DecisionKind
from tests.conftest import only_oid, pass_until


def make_commander(game, seat: int, card_id: str) -> int:
    """Mark a battlefield creature as this seat's commander."""
    oid = only_oid(game, card_id, seat)
    game.state.objects[oid].is_commander = True
    game.state.players[seat].commanders.append(oid)
    return oid


class TestVoltron:
    def test_the_equipment_goes_on_the_commander(self, builder):
        game = (
            builder()
            .battlefield(0, ["bonesplitter", "t_bear", "grizzly_bears", "mountain", "mountain"])
            .build()
        )
        commander = make_commander(game, 0, "grizzly_bears")
        agent = HeuristicAgent(0, strategy=Voltron())
        chosen = agent.act(game, 0, game.legal_actions())
        assert chosen.kind is ActionKind.ACTIVATE
        assert [ref.id for ref in chosen.targets] == [commander]

    def test_the_rest_of_the_team_stays_home(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_bear", "grizzly_bears"])
            .battlefield(1, ["t_bear"])
            .build()
        )
        make_commander(game, 0, "grizzly_bears")
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        bear = only_oid(game, "t_bear", 0)
        strategy = Voltron()
        # A 2/2 into a 2/2 that would trade is not worth leaving the commander
        # without a guard.
        assert strategy.attack_value(game.state, 0, bear, 1, 1.0) == 0.0


class TestGoWide:
    def test_a_wide_board_swings_past_one_big_blocker(self, builder):
        game = (
            builder()
            .battlefield(0, ["t_bear"] * 6)
            .battlefield(1, ["t_big"])
            .build()
        )
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        assert DefaultStrategy().attack_value(game.state, 0, _first_bear(game), 1, 0.0) == 0.0
        chosen = HeuristicAgent(0, strategy=GoWide()).act(game, 0, game.legal_actions())
        assert chosen.kind is ActionKind.ADD_ATTACKER

    def test_a_narrow_board_does_not(self, builder):
        game = builder().battlefield(0, ["t_bear"] * 2).battlefield(1, ["t_big"]).build()
        pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
        chosen = HeuristicAgent(0, strategy=GoWide()).act(game, 0, game.legal_actions())
        assert chosen.kind is ActionKind.FINISH_DECLARATION


class TestAristocrats:
    def test_tokens_are_sacrificed_first(self, builder, registry):
        token = next(c.id for c in registry if c.is_token and c.is_creature)
        game = builder().battlefield(0, ["t_bear", token]).build()
        strategy = Aristocrats()
        bear = only_oid(game, "t_bear", 0)
        fodder = only_oid(game, token, 0)
        assert strategy.junk_value(game.state, 0, fodder, 0.0) > strategy.junk_value(
            game.state, 0, bear, 0.0
        )


class TestMill:
    def test_the_shortest_library_is_the_target(self, builder):
        game = builder(players=3).library(1, ["island"] * 50).library(2, ["island"] * 8).build()
        strategy = Mill()
        assert strategy.player_score(game.state, 0, 2, "mill") > strategy.player_score(
            game.state, 0, 1, "mill"
        )


class TestCombos:
    def test_the_last_piece_is_worth_far_more_than_the_first(self, builder):
        plan = DeckPlan(
            deck_id="x",
            archetype="test",
            combos=(Combo("pair", frozenset({"t_bear", "t_big"}), bonus=400.0),),
        )
        strategy = DefaultStrategy(plan)
        alone = builder().hand(0, ["t_bear"]).build()
        assert strategy.combo_bonus(alone.state, 0, "t_bear") == 0.0
        paired = builder().hand(0, ["t_bear"]).battlefield(0, ["t_big"]).build()
        assert strategy.combo_bonus(paired.state, 0, "t_bear") == 400.0


def _first_bear(game) -> int:
    return next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == "t_bear")
