""""During target opponent's next turn, creatures that player controls attack
Gideon Jura if able." -- 508.1d, a requirement that names one attack target.

Gideon Jura's +2 is the witness. The engine had three attack requirements and
none could say it: `must_attack` flags only the creatures on the battlefield at
resolution, lasts `this_turn`/`next_combat` and names no defender; the
`attacks_if_able` static names no defender either; and goad points *away* from a
player. Here the creatures are "that player's" during that turn -- ones that
arrive later included -- and the attack must go at one planeswalker.

So `must_attack_planeswalker` marks the **planeswalker**
(`GameObject.must_be_attacked_by`), pending until the compelled player's next
untap step, in force for that turn, and gone at its cleanup. What is pinned:

1. During that turn every creature of that player that can attack must attack,
   and only the walker is offered as its target.
2. "If able": a tapped creature owes nothing, and a creature prohibited from
   attacking the walker is free.
3. Not before and not after: the controller's own turn and the turn after the
   compelled one are unconstrained.
4. 400.7: a walker that left is not the one they were told to attack.
5. Beside goad, 508.1d's count: each target is scored by the requirements an
   attack on it obeys, and only the best-scoring targets are offered -- ties
   all of them.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine import combat as combat_mod
from automtg.engine import sba
from automtg.engine.enums import ActionKind, DecisionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import goad_creature, require_attack_on, restrict_attack
from automtg.engine.temp_effects import ATTACK_REQUIREMENT_PENDING
from automtg.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until

BEAR = "t_bear"
WALKER = "t_walker"
TAUNTER = "t_taunting_walker"  # +2: target opponent's creatures attack it next turn


def position(builder, *, players=2, theirs=(BEAR,), active=1, armed=True, their_hand=()):
    """Player 0 has a walker marked for player 1; player 1 has ``theirs``.

    Built at player ``active``'s untap step. ``armed`` places the mark as the
    untap step would have left it on the compelled player's turn.
    """
    b = builder(players=players).battlefield(0, [WALKER])
    if theirs:
        b.battlefield(1, list(theirs))
    if their_hand:
        b.hand(1, list(their_hand))
    for pid in range(players):
        b.library(pid, ["forest"] * 20)
    game = b.active(active).step(Step.UNTAP).build()
    walker = only_oid(game, WALKER, 0)
    require_attack_on(game.state, walker, 1)
    if armed:
        game.state.objects[walker].must_be_attacked_by[1] = game.state.turn
    return game, walker


def to_declare_attackers(game, limit: int = 80):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def targets_offered(game, oid: int) -> tuple[list[int], list[int]]:
    """(players, planeswalkers) this creature is offered as attack targets."""
    actions = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ADD_ATTACKER and a.source == oid
    ]
    players = sorted(t.id for a in actions for t in a.targets if t.kind == "player")
    walkers = sorted(t.id for a in actions for t in a.targets if t.kind == "object")
    return players, walkers


def can_finish(game) -> bool:
    return any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


class TestTheRequirement:
    def test_the_creature_must_attack(self, builder):
        game, _ = position(builder)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert not can_finish(game)

    def test_only_the_walker_is_offered(self, builder):
        game, walker = position(builder)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([], [walker])

    def test_without_the_mark_the_player_is_offered(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WALKER])
            .battlefield(1, [BEAR])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(1)
            .step(Step.UNTAP)
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([0], [only_oid(game, WALKER, 0)])
        assert can_finish(game)

    def test_a_creature_that_arrives_later_is_compelled_too(self, builder):
        """"Creatures that player controls" during that turn, not a list taken
        at resolution -- the difference from `must_attack`."""
        game, walker = position(builder, theirs=(), their_hand=(BEAR,))
        bear = game.state.players[1].hand[0]  # put onto the battlefield after the mark
        move_object(game.state, bear, Zone.BATTLEFIELD)
        game.state.objects[bear].entered_turn = game.state.turn - 1  # not summoning sick
        assert combat_mod.required_attack_walkers(game.state, bear) == {walker}


class TestIfAble:
    def test_a_tapped_creature_owes_nothing(self, builder):
        game, _ = position(builder)
        bear = only_oid(game, BEAR, 1)
        to_declare_attackers(game)
        game.state.objects[bear].tapped = True
        assert combat_mod.unmet_attack_requirements(game.state) == []

    def test_a_prohibition_on_the_walker_frees_the_creature(self, builder):
        """A `planeswalkers` attack restriction forbids the walker; the
        requirement never makes an illegal attack legal."""
        game, _walker = position(builder)
        bear = only_oid(game, BEAR, 1)
        restrict_attack(game.state, 1, 0, "this_turn", planeswalkers=True)
        assert combat_mod.required_attack_walkers(game.state, bear) == set()


class TestTheClock:
    def test_a_pending_mark_does_not_bite(self, builder):
        game, _ = position(builder, armed=False)
        bear = only_oid(game, BEAR, 1)
        assert combat_mod.required_attack_walkers(game.state, bear) == set()

    def test_the_compelled_players_untap_arms_it(self, builder):
        game, walker = position(builder, active=0, armed=False)
        assert game.state.objects[walker].must_be_attacked_by == {1: ATTACK_REQUIREMENT_PENDING}
        pass_until(game, lambda g: g.state.turn >= 2 and g.state.step > Step.UNTAP)
        assert game.state.active_player == 1
        assert game.state.objects[walker].must_be_attacked_by == {1: game.state.turn}

    def test_it_ends_with_that_turn(self, builder):
        game, walker = position(builder, active=0, armed=False)
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.objects[walker].must_be_attacked_by == {}

    def test_it_does_not_bite_on_the_controllers_turn(self, builder):
        """Only the compelled player's creatures, on their turn."""
        game, _walker = position(builder, active=0)
        assert combat_mod.required_attack_walkers(
            game.state, only_oid(game, BEAR, 1)
        ) == set()

    def test_an_eliminated_players_mark_is_dropped(self, builder):
        game, walker = position(builder, players=3, active=0, armed=False)
        game.state.players[1].life = 0
        sba.run(game.state)
        assert game.state.objects[walker].must_be_attacked_by == {}


class TestANewObjectIsNotTheOneNamed:
    def test_a_walker_that_left_and_came_back_is_unmarked(self, builder):
        game, walker = position(builder)
        move_object(game.state, walker, Zone.EXILE)
        move_object(game.state, walker, Zone.BATTLEFIELD)
        assert combat_mod.required_attack_walkers(
            game.state, only_oid(game, BEAR, 1)
        ) == set()

    def test_the_primitive_refuses_the_walkers_own_controller(self, builder):
        game, walker = position(builder)
        assert not require_attack_on(game.state, walker, 0)


class TestBesideGoad:
    def test_the_target_obeying_both_wins(self, builder):
        """Goaded by player 2 and marked for player 0's walker: attacking the
        walker obeys both requirements (it is the walker, and no goader
        controls it), attacking player 0 obeys goad's alone and attacking
        player 2 neither -- so 508.1d's maximum is the walker only."""
        game, walker = position(builder, players=3)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 2)
        to_declare_attackers(game)
        players, walkers = targets_offered(game, bear)
        assert walkers == [walker], "the walker (player 0's, no goader's) scores two"
        assert players == [], "player 0 scores one and player 2 scores zero"

    def test_a_goaders_walker_ties_with_the_other_seat(self, builder):
        """When the walker's controller *is* the goader, attacking it obeys the
        walker requirement and attacking the other opponent obeys goad's: one
        each, so both are offered and the goader's seat is not."""
        game, walker = position(builder, players=3)
        bear = only_oid(game, BEAR, 1)
        goad_creature(game.state, bear, 0)
        to_declare_attackers(game)
        players, walkers = targets_offered(game, bear)
        assert walkers == [walker]
        assert players == [2]


class TestTheOp:
    def test_the_loyalty_ability_marks_itself_for_the_target(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [TAUNTER])
            .battlefield(1, [BEAR])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .active(0)
            .step(Step.UNTAP)
            .build()
        )
        taunter = only_oid(game, TAUNTER, 0)
        pass_until(
            game,
            lambda g: any(
                a.kind is ActionKind.ACTIVATE and a.source == taunter for a in g.legal_actions()
            ),
        )
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE and a.source == taunter
        )
        game.apply(action)
        pass_until(game, lambda g: bool(g.state.objects[taunter].must_be_attacked_by))
        # The sandbox may run on into player 1's turn once nobody has a play, in
        # which case their untap step has already armed it.
        (turn,) = game.state.objects[taunter].must_be_attacked_by.values()
        assert list(game.state.objects[taunter].must_be_attacked_by) == [1]
        assert turn == ATTACK_REQUIREMENT_PENDING or (
            turn == game.state.turn and game.state.active_player == 1
        )


def _card(effect: dict) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "Probe.",
        "mana_cost": "{W}",
        "types": ["Sorcery"],
        "spell_effects": [effect],
    }


class TestTheLoader:
    base = {
        "op": "must_attack_planeswalker",
        "player": "opponent",
        "objects": {"self_only": True},
    }

    @pytest.mark.parametrize("missing", ["player", "objects"])
    def test_each_key_is_required(self, missing):
        effect = {k: v for k, v in self.base.items() if k != missing}
        with pytest.raises(DslError, match="must_attack_planeswalker needs"):
            compile_card(CardModel.model_validate(_card(effect)))

    def test_a_duration_is_refused(self):
        with pytest.raises(DslError, match="takes no 'duration'"):
            compile_card(
                CardModel.model_validate(_card({**self.base, "duration": "this_turn"}))
            )
