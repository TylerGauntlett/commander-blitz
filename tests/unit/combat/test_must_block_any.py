"""``must_block_any``: "target creature blocks this turn if able."

Rule 509.1c: the defending player's declaration must obey the maximum number of
requirements it can without breaking a restriction. Provoke (`must_block`) is a
requirement that names *what* to block and lasts one combat. This one names no
attacker -- blocking any creature attacking its controller obeys it -- and it
lasts the turn, so it binds every combat in it. Spelled as `must_block`, the
target would have to block the ability's source and only in the next combat,
which is a different card.

Enforced at the same seam provoke is: `combat.unmet_block_requirements` keeps
"Done blocking" withheld while the creature is able to block and is not, and the
CPU's declaration is built from the very same legal actions a human is offered,
so it is held to the requirement without knowing it exists.

Witness: Peema Aether-Seer (`peema_aether_seer`), "Pay {E}{E}{E}: Target
creature blocks this turn if able."
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.agents.heuristic_agent import HeuristicAgent
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.combat import add_attacker, add_blocker, start_combat
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _blocker_actions
from commanderblitz.engine.structs import TargetRef
from tests.conftest import activations, only_oid, pass_until, settle

BEAR = "t_bear"  # 2/2
BIG = "t_big"  # 6/6
MENACER = "t_menacer"  # 3/3 menace
PROVOKER = "t_provoker"


def require(game, oid: int) -> None:
    """Resolve the op on one creature, as Peema's ability would."""
    ctx = EffectContext(
        state=game.state, controller=0, source_oid=None, targets={"t1": (TargetRef.obj(oid),)}
    )
    list(execute(ctx, [{"op": "must_block_any", "objects": {"target": "t1"}}]))


def position(builder, mine, theirs, players: int = 2):
    """Player 0's ``mine`` attacking into player 1's ``theirs``; combat open."""
    b = builder(players=players).battlefield(0, list(mine)).battlefield(1, list(theirs))
    game = b.build(advance=False)
    start_combat(game.state)
    return game


def can_finish(game, defender: int = 1) -> bool:
    return any(
        a.kind is ActionKind.FINISH_DECLARATION for a in _blocker_actions(game.state, defender)
    )


def offered(game, defender: int = 1) -> set[tuple[int, int]]:
    return {
        (a.source, a.targets[0].id)
        for a in _blocker_actions(game.state, defender)
        if a.kind is ActionKind.ADD_BLOCKER
    }


class TestAnyBlockObeysIt:
    def test_done_is_withheld_until_it_blocks(self, builder):
        game = position(builder, [BEAR], [BEAR])
        attacker, victim = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        require(game, victim)
        add_attacker(game.state, attacker, 1)
        assert not can_finish(game)
        assert combat_mod.unmet_block_requirements(game.state, 1) == [victim]
        assert add_blocker(game.state, victim, attacker, 1)
        assert can_finish(game)

    def test_every_attacker_is_offered_and_each_obeys_it(self, builder):
        """No attacker is named, so nothing is narrowed -- unlike provoke."""
        game = position(builder, [BEAR, BIG], [BEAR])
        bear, big, victim = only_oid(game, BEAR, 0), only_oid(game, BIG, 0), only_oid(game, BEAR, 1)
        require(game, victim)
        add_attacker(game.state, bear, 1)
        add_attacker(game.state, big, 1)
        assert offered(game) == {(victim, bear), (victim, big)}
        add_blocker(game.state, victim, big, 1)
        assert can_finish(game)

    def test_without_the_op_blocking_is_free(self, builder):
        game = position(builder, [BEAR], [BEAR])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert can_finish(game)


class TestIfAble:
    def test_a_tapped_creature_owes_nothing(self, builder):
        """The op does not untap -- a tapped target is simply excused."""
        game = position(builder, [BEAR], [BEAR])
        victim = only_oid(game, BEAR, 1)
        require(game, victim)
        game.state.objects[victim].tapped = True
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert can_finish(game)

    def test_with_no_attackers_it_owes_nothing(self, builder):
        game = position(builder, [BEAR], [BEAR])
        require(game, only_oid(game, BEAR, 1))
        assert can_finish(game)

    def test_a_creature_not_under_attack_owes_nothing(self, builder):
        """Multiplayer: it can block only creatures attacking its controller."""
        game = (
            builder(players=3)
            .battlefield(0, [BEAR])
            .battlefield(1, [BEAR])
            .battlefield(2, [BEAR])
            .build(advance=False)
        )
        start_combat(game.state)
        victim = only_oid(game, BEAR, 1)
        require(game, victim)
        add_attacker(game.state, only_oid(game, BEAR, 0), 2)
        assert combat_mod.unmet_block_requirements(game.state, 1) == []

    def test_alone_against_menace_it_owes_nothing(self, builder):
        """Menace is a restriction on the whole declaration: one creature can
        never legally block it, so the requirement cannot be obeyed (509.1c)."""
        game = position(builder, [MENACER], [BEAR])
        victim = only_oid(game, BEAR, 1)
        require(game, victim)
        add_attacker(game.state, only_oid(game, MENACER, 0), 1)
        assert can_finish(game)

    def test_against_menace_with_a_partner_it_must_block(self, builder):
        game = position(builder, [MENACER], [BEAR, BIG])
        victim = only_oid(game, BEAR, 1)
        require(game, victim)
        add_attacker(game.state, only_oid(game, MENACER, 0), 1)
        assert combat_mod.unmet_block_requirements(game.state, 1) == [victim]


class TestItLastsTheTurn:
    def test_it_binds_a_second_combat_this_turn(self, builder):
        """Provoke is spent when blockers lock in; "this turn" is not."""
        game = position(builder, [BEAR], [BEAR])
        attacker, victim = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        require(game, victim)
        add_attacker(game.state, attacker, 1)
        add_blocker(game.state, victim, attacker, 1)
        combat_mod.finish_blockers(game.state)
        start_combat(game.state)
        add_attacker(game.state, attacker, 1)
        assert combat_mod.unmet_block_requirements(game.state, 1) == [victim]

    def test_it_ends_with_the_turn(self, builder):
        game = position(builder, [BEAR], [BEAR])
        victim = only_oid(game, BEAR, 1)
        require(game, victim)
        game.state.turn += 1
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert can_finish(game)

    def test_a_new_object_owes_nothing(self, builder):
        """400.7: a creature that left and came back is not the one targeted."""
        game = position(builder, [BEAR], [BEAR])
        victim = only_oid(game, BEAR, 1)
        require(game, victim)
        game.state.objects[victim].reset_permanent_state()
        assert game.state.objects[victim].must_block_any_turn is None


class TestBesideProvoke:
    def test_blocking_the_provoker_obeys_both(self, builder):
        game = position(builder, [PROVOKER, BEAR], [BEAR])
        provoker, other = only_oid(game, PROVOKER, 0), only_oid(game, BEAR, 0)
        victim = only_oid(game, BEAR, 1)
        require(game, victim)
        game.state.objects[victim].must_block = provoker
        add_attacker(game.state, provoker, 1)
        add_attacker(game.state, other, 1)
        assert offered(game) == {(victim, provoker)}
        add_blocker(game.state, victim, provoker, 1)
        assert can_finish(game)


class TestTheCpuObeysIt:
    def test_the_heuristic_agent_chumps_when_it_must(self, builder):
        """At full life the agent would never chump a 6/6 with a 2/2. Under
        the requirement "Done blocking" is not among its actions, so the same
        legality the human gets makes it block."""
        game = builder(players=2).battlefield(0, [BIG]).battlefield(1, [BEAR]).build()
        big, victim = only_oid(game, BIG, 0), only_oid(game, BEAR, 1)
        require(game, victim)
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        add_attacker(game.state, big, 1)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        agent = HeuristicAgent(0)
        actions = game.legal_actions()
        assert all(a.kind is not ActionKind.FINISH_DECLARATION for a in actions)
        choice = agent.act(game, 1, actions)
        assert choice.kind is ActionKind.ADD_BLOCKER and choice.source == victim

    def test_without_it_the_agent_declines_the_chump(self, builder):
        game = builder(players=2).battlefield(0, [BIG]).battlefield(1, [BEAR]).build()
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
        )
        add_attacker(game.state, only_oid(game, BIG, 0), 1)
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION)
        )
        pass_until(
            game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
        )
        choice = HeuristicAgent(0).act(game, 1, game.legal_actions())
        assert choice.kind is ActionKind.FINISH_DECLARATION


class TestTheWitness:
    def test_peemas_ability_places_the_requirement(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["peema_aether_seer"])
            .battlefield(1, [BEAR])
            .build(advance=False)
        )
        peema, victim = only_oid(game, "peema_aether_seer", 0), only_oid(game, BEAR, 1)
        game.state.players[0].energy = 3
        game._advance()
        (activate,) = [
            a for a in activations(game, peema) if TargetRef.obj(victim) in (a.targets or ())
        ]
        game.apply(activate)
        settle(game)
        assert game.state.players[0].energy == 0
        assert game.state.objects[victim].must_block_any_turn == game.state.turn


def _probe(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": {"event": "attacks", "source": "self"},
                    "effects": [effect],
                }
            ],
        }
    )


class TestTheLoaderGuardsIt:
    def test_without_objects_it_is_refused(self):
        with pytest.raises(DslError):
            compile_card(_probe({"op": "must_block_any"}))

    def test_an_attacker_is_refused(self):
        with pytest.raises(DslError, match="must_block"):
            compile_card(
                _probe({"op": "must_block_any", "objects": {"self_only": True}, "attacker": {}})
            )
