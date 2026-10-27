"""`max_blockers` -- "can't be blocked by more than one creature".

    Challenger Troll -- "Each creature you control with power 4 or greater
    can't be blocked by more than one creature."

Rule 509.1b: a restriction on how many creatures may block an attacker is a
fact about the whole declaration, the shape menace has from the other side
(at least two). Neither existing `block_restriction` form counts: `blockers`
refuses a blocker by what it *is*, so refusing every blocker would make the
creature unblockable, and `require_all` is Tromokratis' all-or-nothing.

So the cap is a third form, checked twice. `blocks_valid` is the rule; the
per-pair `can_block` refuses a blocker once the attacker has its quota, because
no later choice can make that declaration legal again and offering it would only
build a block the finish refuses.

The `affects` filter reads **current** power, as every `block_restriction` does
(it is no layer), so a 3-power creature with a counter gains the restriction and
the Troll's line follows the board rather than the printed sizes.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import blocks_valid, can_block
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters
from commanderblitz.engine.structs import TargetRef
from tests.conftest import attack_with, find_action, pass_until

TROLL = "t_mb_troll"     # 6/5, the static
BEAR = "t_bear"          # 2/2
DORK = "t_dork"          # 1/1


def board(builder, attacker: str, *, counters: int = 0):
    """``(game, attacker_oid)``: the Troll at home, ``attacker`` attacking into
    two bears and a dork."""
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + [TROLL] + ([attacker] if attacker != TROLL else []))
        .battlefield(1, [BEAR, BEAR, DORK])
        .build()
    )
    oid = next(
        o.oid for o in game.state.battlefield_objects(0) if o.def_id == attacker
    )
    if counters:
        add_counters(game.state, oid, "+1/+1", counters)
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    attack_with(game, oid)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS
    )
    return game, oid


def block(game, blocker: int, attacker: int) -> None:
    game.apply(
        find_action(
            game, ActionKind.ADD_BLOCKER, source=blocker, targets=(TargetRef.obj(attacker),)
        )
    )


def bears(game) -> list[int]:
    return [o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR]


class TestOneBlockerAtMost:
    def test_one_blocker_is_legal(self, builder):
        game, troll = board(builder, TROLL)
        first, _ = bears(game)
        block(game, first, troll)

        assert blocks_valid(game.state, 1)

    def test_a_second_blocker_is_not_offered(self, builder):
        game, troll = board(builder, TROLL)
        first, second = bears(game)
        block(game, first, troll)

        assert not can_block(game.state, second, troll, 1)
        assert not [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ADD_BLOCKER and a.source == second
        ]

    def test_two_declared_blockers_are_an_illegal_declaration(self, builder):
        """The rule itself, asked of a declaration built around the offer."""
        game, troll = board(builder, TROLL)
        first, second = bears(game)
        block(game, first, troll)
        game.state.combat.blockers[second] = troll
        game.state.combat.block_order[troll].append(second)

        assert not blocks_valid(game.state, 1)

    def test_no_blocker_is_still_legal(self, builder):
        game, _ = board(builder, TROLL)

        assert blocks_valid(game.state, 1)


class TestWhoItCovers:
    def test_a_small_creature_may_be_double_blocked(self, builder):
        game, attacker = board(builder, BEAR)
        first, second = bears(game)
        block(game, first, attacker)

        assert can_block(game.state, second, attacker, 1)

    def test_current_power_decides(self, builder):
        """A 2/2 with two +1/+1 counters is a 4-power creature you control."""
        game, attacker = board(builder, BEAR, counters=2)
        first, second = bears(game)
        block(game, first, attacker)

        assert not can_block(game.state, second, attacker, 1)


class TestTheLoader:
    def _card(self, static: dict) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_mb_probe",
                "name": "Max Blockers Probe",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {"kind": "static", "effect": "block_restriction",
                     "affects": {"self_only": True}, **static}
                ],
            }
        )

    def test_a_cap_loads(self):
        compile_card(self._card({"max_blockers": 1}))

    def test_zero_is_refused(self):
        with pytest.raises(DslError, match="max_blockers"):
            compile_card(self._card({"max_blockers": 0}))

    def test_two_forms_at_once_are_refused(self):
        with pytest.raises(DslError, match="exactly one of"):
            compile_card(self._card({"max_blockers": 1, "require_all": True}))

    def test_it_means_nothing_on_another_static(self):
        with pytest.raises(DslError, match="max_blockers"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_mb_probe2",
                        "name": "Max Blockers Probe Two",
                        "mana_cost": "{1}",
                        "types": ["Creature"],
                        "power": 1,
                        "toughness": 1,
                        "abilities": [
                            {"kind": "static", "effect": "buff", "power": 1, "toughness": 1,
                             "affects": {"self_only": True}, "max_blockers": 1}
                        ],
                    }
                )
            )
