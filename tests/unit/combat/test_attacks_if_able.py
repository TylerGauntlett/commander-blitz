"""A continuous attack requirement: "attacks each combat if able".

Marauding Maulhorn is the shipped witness -- "This creature attacks each combat
if able unless you control a creature named Advocate of the Beast" -- and it is
the *permanent* half of a requirement the engine already half had.

The `must_attack` op (Bident of Thassa, Trench Behemoth) writes a one-shot flag
on the object which `discharge_attack_requirements` spends once attackers are
locked in. That is right for "attacks this turn if able" and wrong for a printed
line, which is true again next turn, is true for a creature that entered after
the op would have resolved, and stops being true the moment its source leaves.
So this is a static, read live off the battlefield, and it joins `must_attack`
at the one enforcement point rather than adding a second.

Rule 508.1d is the half that makes it real: a legal attack declaration must
include every creature that is required to attack **and able to**. The engine
enforces that by *withholding* "Done attacking" while a required creature is not
attacking, so the properties worth pinning are about legal_actions, not about
flags:

- With the requirement live, the declaration cannot be finished early.
- "…if able" is not optional -- a tapped, summoning-sick or `defender` creature
  owes nothing, and the requirement must not deadlock the step by demanding an
  attack that cannot legally be made.
- The `unless` clause is a real switch, and it works in both directions on the
  same board.

`cant_attack` (Stormtide Leviathan) is the mirror image and shares the shape:
one static effect, an `affects` filter that routinely names creatures the
source's controller does not control, one place in `combat` that reads it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import attack_required, unmet_attack_requirements
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import attack_compelled

BEAST = "t_compelled_beast"  # attacks each combat if able, unless Advocate
ADVOCATE = "t_advocate_of_the_beast"


def board(builder, own=(BEAST,), *, opponent=(), sick=False):
    """`own` on player 0's battlefield, ready to attack unless `sick`."""
    return (
        builder(players=2)
        .battlefield(0, list(own), sick=sick)
        .battlefield(1, list(opponent))
        .active(0)
        .step(Step.UNTAP)
        .build(advance=False)
    )


def only(game, def_id: str) -> int:
    return next(
        o for o in game.state.battlefield if game.state.objects[o].def_id == def_id
    )


def to_declare_attackers(game):
    """Advance to the declare-attackers decision."""
    game._advance()
    for _ in range(40):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.DECLARE_ATTACKERS:
            return game
        passing = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.PASS), None
        )
        if passing is None:
            return game
        game.apply(passing)
    return game


def can_finish(game) -> bool:
    return any(
        a.kind is ActionKind.FINISH_DECLARATION for a in game.legal_actions()
    )


class TestTheRequirement:
    def test_a_creature_under_it_must_attack(self, builder):
        game = board(builder)
        assert attack_required(game.state, only(game, BEAST))

    def test_the_declaration_cannot_be_finished_early(self, builder):
        game = to_declare_attackers(board(builder))
        assert game.pending().kind is DecisionKind.DECLARE_ATTACKERS
        assert not can_finish(game), (
            "rule 508.1d: a declaration that leaves out an able required "
            "attacker is not a legal declaration"
        )

    def test_it_is_satisfied_by_actually_attacking(self, builder):
        game = to_declare_attackers(board(builder))
        add = next(a for a in game.legal_actions() if a.kind is ActionKind.ADD_ATTACKER)
        game.apply(add)
        assert unmet_attack_requirements(game.state) == []
        assert can_finish(game), "with the obligation met, the step can end"


class TestTheUnlessClause:
    def test_the_named_creature_switches_it_off(self, builder):
        game = board(builder, own=(BEAST, ADVOCATE))
        assert not attack_required(game.state, only(game, BEAST))

    def test_and_the_declaration_can_then_be_finished(self, builder):
        game = to_declare_attackers(board(builder, own=(BEAST, ADVOCATE)))
        assert can_finish(game), "Advocate is out, so nothing is compelled"

    def test_a_different_creature_does_not_count(self, builder):
        game = board(builder, own=(BEAST, "t_bear"))
        assert attack_required(game.state, only(game, BEAST)), (
            "the clause names one card, not any creature"
        )

    def test_an_opponents_advocate_does_not_count(self, builder):
        # "*you* control a creature named Advocate of the Beast".
        game = board(builder, own=(BEAST,), opponent=(ADVOCATE,))
        assert attack_required(game.state, only(game, BEAST))


class TestIfAble:
    def test_a_summoning_sick_creature_owes_nothing(self, builder):
        game = board(builder, sick=True)
        assert not attack_required(game.state, only(game, BEAST)), (
            "'if able' is the whole of the second half: a requirement never "
            "makes an illegal attack legal"
        )

    def test_and_so_the_step_does_not_deadlock(self, builder):
        """A second, healthy creature so the step actually happens.

        With the compelled creature sick and nothing else able, the engine
        skips declare-attackers entirely; the interesting case is a real
        declaration where the sick one is simply not owed.
        """
        game = (
            builder(players=2)
            .battlefield(0, [BEAST], sick=True)
            .battlefield(0, ["t_bear"])
            .active(0)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        game = to_declare_attackers(game)
        assert game.pending().kind is DecisionKind.DECLARE_ATTACKERS
        assert can_finish(game), (
            "a requirement that demanded an impossible attack would withhold "
            "'Done attacking' forever"
        )

    def test_a_tapped_creature_owes_nothing(self, builder):
        game = board(builder)
        game.state.objects[only(game, BEAST)].tapped = True
        game.state.bump_chars()
        assert not attack_required(game.state, only(game, BEAST))


class TestItIsContinuous:
    def test_it_reaches_other_players_creatures(self, builder):
        """"Creatures your opponents control attack each combat if able."

        The goad-shaped variant, and the reason this is one static effect with
        an `affects` filter rather than a flag on the card that carries it: the
        banner's controller does not control the creature it compels.
        """
        game = board(builder, own=("t_goading_banner",), opponent=("t_bear",))
        assert attack_compelled(game.state, only(game, "t_bear"))

    def test_but_it_is_owed_only_on_that_creature_s_own_turn(self, builder):
        """A goad must not withhold "Done attacking" from the wrong seat.

        Player 0 controls the banner and it is player 0's turn; the compelled
        bear is player 1's, and a creature cannot attack on somebody else's
        turn -- so "if able" means it owes nothing yet. Without this, player 0
        could never finish a declaration while an opponent held an untapped
        creature.
        """
        game = board(builder, own=("t_goading_banner",), opponent=("t_bear",))
        assert not attack_required(game.state, only(game, "t_bear"))
        assert unmet_attack_requirements(game.state) == []

    def test_and_it_is_owed_when_their_turn_comes(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["t_goading_banner"])
            .battlefield(1, ["t_bear"])
            .active(1)
            .step(Step.UNTAP)
            .build(advance=False)
        )
        bear = only(game, "t_bear")
        assert attack_required(game.state, bear)
        assert unmet_attack_requirements(game.state) == [bear]


def probe(static: dict) -> dict:
    return {
        "id": "probe",
        "name": "Probe",
        "oracle_text": "This creature attacks each combat if able.",
        "mana_cost": "{R}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
        "abilities": [
            {
                "kind": "static",
                "text": "This creature attacks each combat if able.",
                "effect": "attacks_if_able",
                **static,
            }
        ],
    }


class TestNameInTheCondition:
    def test_a_condition_may_name_a_card(self):
        compile_card(
            CardModel.model_validate(
                probe(
                    {
                        "affects": {"self_only": True},
                        "condition": {
                            "not": {"exists": {"controller": "you", "name": "Whatever"}}
                        },
                    }
                )
            )
        )

    def test_affects_still_may_not(self):
        """`name` is a counting key, not a targeting one.

        "Each creature named X gets +1/+1" is not a card, so allowing it in
        `affects` would only invite one.
        """
        with pytest.raises(DslError, match="static filters may only read printed"):
            compile_card(
                CardModel.model_validate(probe({"affects": {"name": "Whatever"}}))
            )
