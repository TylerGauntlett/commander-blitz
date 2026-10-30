""""…attacks an opponent with the most life among your opponents each combat if
able" and "…target creature attacks that player each combat if able" --
508.1d, an attack requirement that names the defending player.

Galactus, Devourer of Worlds (the static) and Silver Surfer, Galactus's Herald
(the one-shot, "until the end of your next turn") are the witnesses. Neither
could be written before: the `attacks_if_able` static and `must_attack` name no
defender, so any attack obeyed them -- Galactus swinging at the opponent on
the fewest life, or at a planeswalker, would have satisfied a requirement the
printed card says it has not. Goad points *away* from a seat, and Gideon
Jura's mark names a walker.

So a requirement is now a set of seats (`combat.required_attack_defenders`),
from the static's ``defending`` or the op's `AttackMark`. What is pinned:

1. Only an attack on one of the named **players** obeys it -- not the other
   opponent, and not a planeswalker the named player controls (506.2).
2. Ties among the named seats are the attacking player's choice.
3. "If able": a requirement whose seats are all closed to the creature compels
   nothing -- it does not become "attack somebody else".
4. The static's condition switches it off; without ``defending`` the same static
   is the plain requirement any attack obeys.
5. The mark's clock is "until the end of your next turn", and the mark ends
   with the creature (400.7) and with a seat leaving the game (800.4a).
6. Beside goad, 508.1d's count decides which targets are offered.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine import sba
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.temp_effects import (
    goad_creature,
    require_attack_player,
    restrict_attack,
)
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, only_oid, pass_until, static_probe

TITAN = "t_hungry_titan"  # attacks an opponent with the most life ... unless Test Herald
BRUTE = "t_hungry_brute"  # the near miss: attacks each combat if able, no defender
HERALD = "t_test_herald"
BEAR = "t_bear"
WALKER = "t_walker"


def position(builder, *, mine=(TITAN,), lives=(40, 30, 20, 20), players=4, walker_for=None):
    """Player 0 attacks with ``mine``; the others' life totals are ``lives``."""
    b = builder(players=players).battlefield(0, list(mine))
    if walker_for is not None:
        b.battlefield(walker_for, [WALKER])
    for pid in range(players):
        b.library(pid, ["forest"] * 20)
    game = b.active(0).step(Step.UNTAP).build()
    for pid, life in enumerate(lives[:players]):
        game.state.players[pid].life = life
    return game


def to_declare_attackers(game, limit: int = 80):
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        game.apply(_default_answer(game, decision))
    raise AssertionError("never reached declare attackers")


def targets_offered(game, oid: int) -> tuple[list[int], list[int]]:
    """(players, permanents) this creature is offered as attack targets."""
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


def run_op(game, spec: dict, *, controller: int = 0, defender: int | None = None) -> None:
    ctx = EffectContext(state=game.state, controller=controller)
    if defender is not None:
        ctx.bindings["defender"] = defender
    gen = execute(ctx, [spec])
    with contextlib.suppress(StopIteration):
        while True:
            next(gen)


class TestTheStatic:
    def test_it_must_attack(self, builder):
        game = position(builder)
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [titan]
        assert not can_finish(game)

    def test_only_the_opponent_with_the_most_life_is_offered(self, builder):
        game = position(builder)
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        assert targets_offered(game, titan) == ([1], [])

    def test_the_comparison_is_among_opponents_only(self, builder):
        """Player 0's own 40 life is not "among your opponents"."""
        game = position(builder, lives=(40, 10, 25, 25))
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        assert targets_offered(game, titan) == ([2, 3], [])

    def test_the_named_players_walker_does_not_obey_it(self, builder):
        """506.2: attacking a planeswalker is not attacking its controller."""
        game = position(builder, walker_for=1)
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        assert targets_offered(game, titan) == ([1], [])

    def test_it_is_read_live(self, builder):
        game = position(builder)
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        game.state.players[2].life = 35
        assert targets_offered(game, titan) == ([2], [])

    def test_attacking_the_named_player_finishes_the_declaration(self, builder):
        game = position(builder)
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        assert combat_mod.add_attacker(game.state, titan, 1)
        assert can_finish(game)

    def test_the_condition_switches_it_off(self, builder):
        game = position(builder, mine=(TITAN, HERALD))
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert targets_offered(game, titan) == ([1, 2, 3], [])

    def test_without_defending_any_attack_obeys(self, builder):
        """The near miss: the same static with no defender."""
        game = position(builder, mine=(BRUTE,))
        brute = only_oid(game, BRUTE, 0)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [brute]
        assert targets_offered(game, brute) == ([1, 2, 3], [])


class TestIfAble:
    def test_a_closed_seat_frees_the_creature(self, builder):
        """The top seat cannot be attacked: the requirement owes nothing, and
        does not become "attack the next one down"."""
        game = position(builder)
        titan = only_oid(game, TITAN, 0)
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        assert combat_mod.required_attack_defenders(game.state, titan) == []
        assert combat_mod.unmet_attack_requirements(game.state) == []
        assert targets_offered(game, titan) == ([2, 3], [])

    def test_one_open_seat_of_a_tie_is_enough(self, builder):
        game = position(builder, lives=(40, 30, 30, 20))
        titan = only_oid(game, TITAN, 0)
        restrict_attack(game.state, 0, 1, "this_turn")
        to_declare_attackers(game)
        assert combat_mod.required_attack_defenders(game.state, titan) == [frozenset({2})]
        assert targets_offered(game, titan) == ([2], [])

    def test_a_tapped_creature_owes_nothing(self, builder):
        game = position(builder)
        titan = only_oid(game, TITAN, 0)
        to_declare_attackers(game)
        game.state.objects[titan].tapped = True
        assert combat_mod.unmet_attack_requirements(game.state) == []


def mark(game, oid: int, defender: int, clock: int = 0) -> None:
    assert require_attack_player(game.state, oid, defender, clock)


class TestTheMark:
    def test_the_marked_creature_must_attack_that_player(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 3)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == [bear]
        assert targets_offered(game, bear) == ([3], [])

    def test_the_op_writes_one_mark_per_player(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        run_op(
            game,
            {
                "op": "must_attack_player",
                "objects": {"controller": "any", "types": ["Creature"]},
                "defender": {"binding": "defender"},
                "duration": "end_of_your_next_turn",
            },
            controller=1,
            defender=2,
        )
        (only,) = game.state.objects[bear].attack_marks
        assert (only.defender, only.until_end_of_turn_of) == (2, 1)

    def test_two_marks_are_two_requirements(self, builder):
        """Marked for players 2 and 3: either obeys one of them, so both are
        offered and player 1 -- obeying none -- is not."""
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 2)
        mark(game, bear, 3)
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([2, 3], [])

    def test_a_mark_naming_its_own_controller_compels_nothing(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 0)
        to_declare_attackers(game)
        assert combat_mod.unmet_attack_requirements(game.state) == []

    def test_beside_goad_the_count_decides(self, builder):
        """Marked for player 2 and goaded by player 3: attacking 2 obeys both
        (it is the named seat, and not the goader's), attacking 1 obeys goad's
        alone and attacking 3 neither -- so 508.1d's maximum is player 2."""
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 2)
        goad_creature(game.state, bear, 3)
        to_declare_attackers(game)
        assert targets_offered(game, bear) == ([2], [])


class TestTheClock:
    def test_it_lasts_through_the_other_turns_and_ends_with_yours(self, builder):
        game = position(builder, mine=(BEAR,), players=2, lives=(20, 20))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 1, clock=0)  # made on player 0's own turn
        pass_until(game, lambda g: g.state.turn >= 2)
        assert game.state.objects[bear].attack_marks, "survives this turn's cleanup"
        pass_until(game, lambda g: g.state.turn >= 3)
        assert game.state.objects[bear].attack_marks, "and the opponent's turn"
        pass_until(game, lambda g: g.state.turn >= 4)
        assert game.state.objects[bear].attack_marks == [], "ends with your next turn"

    def test_a_creature_that_left_is_a_new_object(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 2)
        move_object(game.state, bear, Zone.EXILE)
        move_object(game.state, bear, Zone.BATTLEFIELD)
        assert game.state.objects[bear].attack_marks == []

    def test_a_named_player_leaving_ends_it(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 2, clock=1)
        game.state.players[2].life = 0
        sba.run(game.state)
        assert game.state.objects[bear].attack_marks == []

    def test_the_clocks_player_leaving_ends_it(self, builder):
        game = position(builder, mine=(BEAR,))
        bear = only_oid(game, BEAR, 0)
        mark(game, bear, 2, clock=1)
        game.state.players[1].life = 0
        sba.run(game.state)
        assert game.state.objects[bear].attack_marks == []


def _sorcery(effect: dict) -> dict:
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
        "op": "must_attack_player",
        "objects": {"types": ["Creature"]},
        "defender": "each_opponent",
        "duration": "end_of_your_next_turn",
    }

    @pytest.mark.parametrize("missing", ["objects", "defender", "duration"])
    def test_each_key_is_required(self, missing):
        effect = {k: v for k, v in self.base.items() if k != missing}
        with pytest.raises(DslError, match="must_attack_player needs"):
            compile_card(CardModel.model_validate(_sorcery(effect)))

    def test_an_unknown_duration_is_refused(self):
        with pytest.raises(DslError, match="must_attack_player needs a 'duration'"):
            compile_card(
                CardModel.model_validate(_sorcery({**self.base, "duration": "next_turn"}))
            )

    def test_defending_on_another_static_is_refused(self):
        probe = static_probe(
            {"effect": "cant_attack", "affects": {"types": ["Creature"]},
             "defending": "opponent_most_life"}
        )
        with pytest.raises(DslError, match="'defending' only means anything"):
            compile_card(CardModel.model_validate(probe))

    def test_an_unknown_defending_word_is_refused(self):
        probe = static_probe(
            {"effect": "attacks_if_able", "affects": {"self_only": True}, "defending": "most_life"}
        )
        with pytest.raises(Exception, match="defending"):
            compile_card(CardModel.model_validate(probe))
