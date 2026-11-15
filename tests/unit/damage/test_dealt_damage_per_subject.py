"""One firing per damaged permanent: ``per_subject`` on a batched `dealt_damage`.

    "Whenever a Dinosaur you control is dealt damage, it deals **that much**
    damage to any target that isn't a Dinosaur."      -- Wrathful Raptors

The trigger watches other permanents, and each Dinosaur dealt damage is its own
trigger event: a sweeper that hits three Dinosaurs triggers three times, each
for the damage that Dinosaur was dealt. "That much" is all of it at once
(510.2): a Dinosaur blocked by two creatures triggers once for the sum.

Neither existing spelling says that. Unbatched, `dealt_damage` fires once per
`DAMAGE_DEALT`, which is one per source, so the double block triggers twice
with split amounts. ``batched`` alone keys the batch by the ability, not the
victim -- right for Hercules, whose subject is always himself -- so the sweeper
folds every Dinosaur into one firing whose subject is the first and whose
amount is the sum. ``per_subject`` keys it by the damaged permanent as well
(`triggers._batch_subject`).

`t_dps_watcher` puts "that many" +1/+1 counters on the Dinosaur that fired, so
the counters say which one fired and for how much; `t_dps_near_miss` is the
same line without ``per_subject``.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from tests.conftest import attack_with, find_action, only_oid, pass_until, plus_one_counters

WATCHER = "t_dps_watcher"
NEAR_MISS = "t_dps_near_miss"
BRUTE = "t_dps_brute"  # 2/6 Dinosaur
QUAKE = "t_dps_quake"  # {R}: 1 damage to each creature
BEAR = "t_bear"  # 2/2


def settle_all(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers and (
        g.pending() is None or g.pending().kind is DecisionKind.PRIORITY
    ))


def quaked(builder, watcher: str):
    game = (
        builder(players=2)
        .battlefield(0, [watcher, BRUTE, BRUTE, "mountain"])
        .hand(0, [QUAKE])
        .active(0)
        .build()
    )
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == QUAKE
        )
    )
    settle_all(game)
    brutes = [o.oid for o in game.state.battlefield_objects(0) if o.def_id == BRUTE]
    return [plus_one_counters(game, oid) for oid in brutes]


def double_blocked(builder, watcher: str) -> int:
    game = (
        builder(players=2)
        .battlefield(0, [watcher, BRUTE])
        .battlefield(1, [BEAR, BEAR])
        .active(0)
        .build()
    )
    brute = only_oid(game, BRUTE, 0)
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS)
    attack_with(game, brute)
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_BLOCKERS)
    for blocker in game.state.battlefield_objects(1):
        game.apply(
            find_action(
                game, ActionKind.ADD_BLOCKER, source=blocker.oid, targets=(TargetRef.obj(brute),)
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
    pass_until(
        game,
        lambda g: g.state.step >= Step.END_OF_COMBAT
        and not g.state.stack
        and not g.state.pending_triggers,
    )
    return plus_one_counters(game, brute)


class TestOnePerDamagedPermanent:
    def test_a_sweeper_fires_once_for_each_dinosaur(self, builder):
        assert quaked(builder, WATCHER) == [1, 1]

    def test_without_it_the_sweeper_folds_into_one_firing(self, builder):
        """The near miss: one firing, the first Dinosaur, the sum."""
        assert sorted(quaked(builder, NEAR_MISS)) == [0, 2]


class TestThatMuchIsAllOfIt:
    def test_two_blockers_are_one_firing_for_the_sum(self, builder):
        assert double_blocked(builder, WATCHER) == 4


class TestTheLoader:
    def card(self, **trigger):
        return CardModel.model_validate(
            {
                "id": "t_bad_per_subject",
                "name": "Test Bad Per Subject",
                "oracle_text": "Whenever a Dinosaur you control is dealt damage, you gain 1 life.",
                "mana_cost": "{G}",
                "types": ["Enchantment"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "Whenever a Dinosaur you control is dealt damage, you gain 1 life.",
                        "trigger": {"filter": {"subtypes": ["Dinosaur"]}, **trigger},
                        "effects": [{"op": "gain_life", "amount": {"const": 1}}],
                    }
                ],
            }
        )

    def test_it_loads_on_a_batched_dealt_damage(self):
        compile_card(
            self.card(event="dealt_damage", batched=True, per_subject=True), source="t"
        )

    @pytest.mark.parametrize(
        "trigger",
        [
            {"event": "dealt_damage", "per_subject": True},
            {"event": "dies", "batched": True, "per_subject": True},
        ],
    )
    def test_it_is_refused_anywhere_else(self, trigger):
        with pytest.raises(DslError, match="per_subject"):
            compile_card(self.card(**trigger), source="t")
