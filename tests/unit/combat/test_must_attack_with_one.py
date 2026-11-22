"""A requirement on a player's declaration: "must attack with at least one creature".

Seeker of Slaanesh is the witness: "Allure of Slaanesh -- Each opponent must
attack with at least one creature each combat if able." Rule 508.1d: the
declaration must obey as many requirements as possible without breaking a
restriction, and a player is never required to pay a cost to obey one.

The requirement names a player, not a creature. `attacks_if_able` with
``affects: {controller: opponent}`` is the near miss and a far stronger card --
it compels *every* creature the opponent controls. Here any one attacker meets
it, so the claims are about the empty declaration only:

- with a creature able to attack for free, "Done attacking" is withheld until
  one attacks, and any one will do;
- "if able" is real -- a tapped, summoning-sick, taxed or lone can't-attack-
  alone creature owes nothing, and the empty declaration stays legal;
- two can't-attack-alone creatures can attack together, so they do owe it;
- the static's controller is not bound by "each opponent".

`t_allure` (tests/data/must_attack_with_one.cards.json) is the line on its own.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import attack_with_one_unmet, start_combat
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import advance_to_step, attack_with, oids_of, static_probe

ALLURE = "t_allure"
BEAR = "t_bear"
ALONE = "beast_4_4_w_alone"  # can't attack or block alone
FORT = "t_propaganda"  # attacks on its controller cost {2} each


def board(builder, *, healthy=(BEAR,), sick=(), tapped=(), theirs=(ALLURE,), lands=0):
    """Player 0 at declare-attackers; player 1 holds ``theirs``."""
    b = builder(players=2).battlefield(0, list(healthy))
    b = b.battlefield(0, list(sick), sick=True).battlefield(0, list(tapped), tapped=True)
    b = b.battlefield(0, ["forest"] * lands).battlefield(1, list(theirs))
    game = b.build()
    advance_to_step(game, Step.DECLARE_ATTACKERS)
    return game


def can_finish(game) -> bool:
    return any(a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions())


def finish(game) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def offered(game) -> set[int]:
    return {a.source for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER}


class TestTheRequirement:
    def test_an_empty_declaration_is_withheld(self, builder):
        game = board(builder)
        assert game.pending().kind is DecisionKind.DECLARE_ATTACKERS
        assert attack_with_one_unmet(game.state, 0)
        assert not can_finish(game), (
            "508.1d: a declaration with no attacker obeys none of the requirement "
            "when a creature could attack"
        )

    def test_one_attacker_meets_it(self, builder):
        game = board(builder)
        attack_with(game, oids_of(game, BEAR, 0)[0])
        assert can_finish(game)

    @pytest.mark.parametrize("which", [0, 1, 2])
    def test_any_one_will_do(self, builder, which):
        game = board(builder, healthy=(BEAR, BEAR, BEAR))
        attack_with(game, oids_of(game, BEAR, 0)[which])
        assert can_finish(game), "the requirement names no creature, so the rest stay home"

    def test_it_binds_each_combat_afresh(self, builder):
        """Read live at each declaration, never spent by the first one."""
        game = board(builder)
        bear = oids_of(game, BEAR, 0)[0]
        attack_with(game, bear)
        finish(game)
        assert not attack_with_one_unmet(game.state, 0)
        game.state.objects[bear].tapped = False
        start_combat(game.state)
        assert attack_with_one_unmet(game.state, 0), "a new combat is a new declaration"


class TestIfAble:
    def test_nothing_able_means_nothing_owed(self, builder):
        """No creature could attack: the empty declaration obeys all it can."""
        game = (
            builder(players=2)
            .battlefield(0, [BEAR], sick=True)
            .battlefield(0, [BEAR], tapped=True)
            .battlefield(1, [ALLURE])
            .build(advance=False)
        )
        start_combat(game.state)
        assert not attack_with_one_unmet(game.state, 0)

    def test_tapped_and_sick_creatures_are_not_counted(self, builder):
        game = board(builder, healthy=(BEAR,), sick=(BEAR,), tapped=(BEAR,))
        assert not can_finish(game)
        able = offered(game)
        assert len(able) == 1, "only the untapped, unsick bear can attack"
        attack_with(game, able.pop())
        assert can_finish(game)

    def test_a_taxed_attack_is_not_owed(self, builder):
        """508.1d: no player is required to pay a cost to obey a requirement."""
        game = board(builder, theirs=(ALLURE, FORT), lands=2)
        assert offered(game), "the attack is still offered, at its price"
        assert can_finish(game)

    def test_a_lone_cant_attack_alone_creature_is_not_owed(self, builder):
        game = board(builder, healthy=(ALONE,))
        assert game.pending().kind is DecisionKind.DECLARE_ATTACKERS
        assert not attack_with_one_unmet(game.state, 0)
        assert can_finish(game), "its only attack would break a restriction"

    def test_two_of_them_can_attack_together_so_they_owe_it(self, builder):
        game = board(builder, healthy=(ALONE, ALONE))
        assert not can_finish(game)
        first, second = oids_of(game, ALONE, 0)
        attack_with(game, first)
        assert not can_finish(game), "one alone still breaks can't-attack-alone"
        attack_with(game, second)
        assert can_finish(game)


class TestWhoIsBound:
    def test_without_the_static_nothing_is_owed(self, builder):
        assert can_finish(board(builder, theirs=()))

    def test_the_controller_is_not_an_opponent(self, builder):
        game = board(builder, healthy=(BEAR, ALLURE), theirs=())
        assert can_finish(game), "'each opponent' does not bind the static's controller"


class TestTheLoader:
    def test_it_needs_to_say_whose(self):
        probe = static_probe({"effect": "must_attack_with_at_least_one_creature"})
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(probe))

    def test_it_takes_no_creature_filter(self):
        probe = static_probe(
            {
                "effect": "must_attack_with_at_least_one_creature",
                "affects_player": "opponent",
                "affects": {"types": ["Creature"]},
            }
        )
        with pytest.raises(DslError, match="no 'affects'"):
            compile_card(CardModel.model_validate(probe))
