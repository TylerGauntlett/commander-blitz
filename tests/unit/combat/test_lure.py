"""Lure: "All creatures able to block this creature do so" (509.1c).

Treeshaker Chimera is the witness, and Marble Priest ("All Walls able to block
this creature do so") the narrowed form. The requirement sits on the
*attacker* and binds each creature that could block it, so it is neither of
the engine's other block requirements: `must_block` (provoke) is a one-shot
op on the blocker that needs a trigger -- and an `attacks` trigger never fires
for a creature put onto the battlefield attacking -- and `blocks_if_able` is
obeyed by blocking *any* attacker, where a lure is obeyed only by blocking the
lure. It is the `lure` static, read live by `characteristics.lures` at
`combat.unmet_block_requirements`.

509.1c asks the declaration to obey as many requirements as it can, so they
are counted: a creature torn between two lures obeys one whichever it blocks,
and one both provoked and lured may block either. Without the static the
Chimera is a vanilla 8/5 its controller's opponents block as they please, a
different card from the printed one.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import combat as combat_mod
from commanderblitz.engine.combat import add_attacker, add_blocker, start_combat
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _blocker_actions
from tests.conftest import oids_of, only_oid

LURER = "t_lurer"  # 4/4, all creatures able to block it do so
WALL_LURER = "t_wall_lurer"  # 3/3, all Walls able to block it do so
MENACE_LURER = "t_menace_lurer"  # 4/4 menace, lure
BEAR = "t_bear"  # 2/2
WALL = "t_wall"  # 0/4 defender Wall
BERZERKER = "t_berzerker"  # attacks or blocks each combat if able


def position(builder, mine, theirs):
    """Player 0's ``mine`` on the battlefield facing player 1's ``theirs``; combat open."""
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    start_combat(game.state)
    return game


def can_finish(game, defender: int = 1) -> bool:
    return any(
        a.kind is ActionKind.FINISH_DECLARATION for a in _blocker_actions(game.state, defender)
    )


def offered(game, blocker: int, defender: int = 1) -> set[int]:
    return {
        a.targets[0].id
        for a in _blocker_actions(game.state, defender)
        if a.kind is ActionKind.ADD_BLOCKER and a.source == blocker
    }


class TestEveryAbleCreatureBlocksIt:
    def test_done_is_withheld_until_every_able_creature_blocks(self, builder):
        game = position(builder, [LURER], [BEAR, BEAR])
        lurer = only_oid(game, LURER, 0)
        first, second = oids_of(game, BEAR, 1)
        add_attacker(game.state, lurer, 1)
        assert not can_finish(game), "rule 509.1c: an able creature left out is unmet"
        assert set(combat_mod.unmet_block_requirements(game.state, 1)) == {first, second}
        add_blocker(game.state, first, lurer, 1)
        assert combat_mod.unmet_block_requirements(game.state, 1) == [second]
        assert not can_finish(game)
        add_blocker(game.state, second, lurer, 1)
        assert can_finish(game)

    def test_a_lured_creature_is_offered_only_the_lure(self, builder):
        """Blocking is exclusive, so blocking another attacker first would be a
        way out of the requirement; `legal_blocks` closes it."""
        game = position(builder, [LURER, BEAR], [BEAR])
        lurer, bear = only_oid(game, LURER, 0), only_oid(game, BEAR, 0)
        add_attacker(game.state, lurer, 1)
        add_attacker(game.state, bear, 1)
        assert offered(game, only_oid(game, BEAR, 1)) == {lurer}

    def test_blocking_another_attacker_does_not_meet_it(self, builder):
        game = position(builder, [LURER, BEAR], [BEAR])
        bear, blocker = only_oid(game, BEAR, 0), only_oid(game, BEAR, 1)
        add_attacker(game.state, only_oid(game, LURER, 0), 1)
        add_attacker(game.state, bear, 1)
        add_blocker(game.state, blocker, bear, 1)
        assert combat_mod.unmet_block_requirements(game.state, 1) == [blocker]

    def test_it_binds_however_the_creature_came_to_attack(self, builder):
        """Read live while it is attacking: nothing is triggered or spent, so a
        creature put onto the battlefield attacking lures as one declared does,
        and every later combat too."""
        game = position(builder, [LURER], [BEAR])
        lurer = only_oid(game, LURER, 0)
        game.state.combat.attackers[lurer] = 1
        assert not can_finish(game)
        combat_mod.discharge_block_requirements(game.state)
        assert not can_finish(game)

    def test_not_attacking_it_lures_nothing(self, builder):
        game = position(builder, [LURER, BEAR], [BEAR])
        add_attacker(game.state, only_oid(game, BEAR, 0), 1)
        assert can_finish(game)


class TestIfAble:
    def test_a_tapped_creature_owes_nothing(self, builder):
        game = position(builder, [LURER], [BEAR])
        game.state.objects[only_oid(game, BEAR, 1)].tapped = True
        add_attacker(game.state, only_oid(game, LURER, 0), 1)
        assert can_finish(game)

    def test_a_creature_that_cannot_block_it_is_free(self, builder):
        """A lure never makes an illegal block legal: with no lure it could block
        it is offered every attacker, and owes nothing."""
        game = position(builder, [LURER, BEAR], [BEAR])
        lurer, bear = only_oid(game, LURER, 0), only_oid(game, BEAR, 0)
        add_attacker(game.state, lurer, 1)
        add_attacker(game.state, bear, 1)
        game.state.combat.removed.add(lurer)
        assert offered(game, only_oid(game, BEAR, 1)) == {bear}
        assert can_finish(game)

    def test_alone_against_menace_it_owes_nothing(self, builder):
        game = position(builder, [MENACE_LURER], [BEAR])
        add_attacker(game.state, only_oid(game, MENACE_LURER, 0), 1)
        assert can_finish(game)

    def test_against_menace_with_a_partner_both_must_block(self, builder):
        game = position(builder, [MENACE_LURER], [BEAR, BEAR])
        lurer = only_oid(game, MENACE_LURER, 0)
        add_attacker(game.state, lurer, 1)
        assert not can_finish(game)
        for blocker in oids_of(game, BEAR, 1):
            add_blocker(game.state, blocker, lurer, 1)
        assert can_finish(game)


class TestBlockersFilter:
    def test_only_matching_creatures_owe_the_block(self, builder):
        """Marble Priest: the Walls must block it, the Bear may do as it likes."""
        game = position(builder, [WALL_LURER], [WALL, BEAR])
        priest = only_oid(game, WALL_LURER, 0)
        wall, bear = only_oid(game, WALL, 1), only_oid(game, BEAR, 1)
        add_attacker(game.state, priest, 1)
        assert combat_mod.unmet_block_requirements(game.state, 1) == [wall]
        add_blocker(game.state, wall, priest, 1)
        assert can_finish(game)
        assert bear not in combat_mod.unmet_block_requirements(game.state, 1)


class TestMostRequirementsObeyed:
    def test_between_two_lures_either_obeys_one(self, builder):
        game = position(builder, [LURER, MENACE_LURER], [BEAR, BEAR, BEAR])
        lurer, menacer = only_oid(game, LURER, 0), only_oid(game, MENACE_LURER, 0)
        add_attacker(game.state, lurer, 1)
        add_attacker(game.state, menacer, 1)
        first, second, third = oids_of(game, BEAR, 1)
        assert offered(game, first) == {lurer, menacer}
        add_blocker(game.state, first, lurer, 1)
        add_blocker(game.state, second, menacer, 1)
        add_blocker(game.state, third, menacer, 1)
        assert can_finish(game)

    def test_a_nameless_requirement_is_met_by_the_lure_too(self, builder):
        """Khârn's "blocks each combat if able" beside a lure: blocking the lure
        obeys both, so that is the only block it is offered."""
        game = position(builder, [LURER, BEAR], [BERZERKER])
        lurer, bear = only_oid(game, LURER, 0), only_oid(game, BEAR, 0)
        kharn = only_oid(game, BERZERKER, 1)
        add_attacker(game.state, lurer, 1)
        add_attacker(game.state, bear, 1)
        assert offered(game, kharn) == {lurer}
        add_blocker(game.state, kharn, lurer, 1)
        assert can_finish(game)

    def test_provoke_and_a_lure_are_one_each(self, builder):
        game = position(builder, [LURER, BEAR], [BEAR])
        lurer, bear = only_oid(game, LURER, 0), only_oid(game, BEAR, 0)
        blocker = only_oid(game, BEAR, 1)
        add_attacker(game.state, lurer, 1)
        add_attacker(game.state, bear, 1)
        game.state.objects[blocker].must_block = bear
        assert offered(game, blocker) == {lurer, bear}
        add_blocker(game.state, blocker, bear, 1)
        assert can_finish(game)


def _probe(static: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{G}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [{"kind": "static", "text": "x", **static}],
        }
    )


class TestLoader:
    def test_a_counting_form_is_refused(self):
        with pytest.raises(DslError, match="lure takes only"):
            compile_card(
                _probe({"effect": "lure", "affects": {"self_only": True}, "max_blockers": 1})
            )

    def test_an_unknown_blockers_key_is_refused(self):
        with pytest.raises(DslError, match="lure 'blockers'"):
            compile_card(
                _probe(
                    {"effect": "lure", "affects": {"self_only": True}, "blockers": {"bogus": 1}}
                )
            )

    def test_blockers_elsewhere_is_still_refused(self):
        with pytest.raises(DslError, match="only mean"):
            compile_card(
                _probe(
                    {
                        "effect": "blocks_if_able",
                        "affects": {"self_only": True},
                        "blockers": {"subtypes": ["Wall"]},
                    }
                )
            )
