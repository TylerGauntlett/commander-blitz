"""A spree mode that owns its target: declared only when that mode is bought.

    Requisition Raid — "Spree / + {1} — Destroy target artifact. / + {1} —
    Destroy target enchantment. / + {1} — Put a +1/+1 counter on each creature
    target player controls."

Spree (702.172) buys its modes as additional costs at 601.2b, and 601.2c
declares the targets after that, so a cast declares exactly the targets of the
modes it bought. Without a mode-owned spec the card has two wrong spellings:
three unconditional targets demand an artifact, an enchantment and a player on
every cast (the artifact mode alone is uncastable with no enchantment around),
and three `optional` ones let a cast that bought a mode skip its target, or
point at things for modes it never paid for.

So a target spec takes `spree_mode: n`, `CardDef.targets_for` keeps it only for
a subset containing n, and the cast line, `Game._cast`, resolution's 608.2b
split and a copy (707.10 copies the bought modes) all read that one list.
`t_spree_raid` is the witness as an instant, so a cast-trigger copier can copy
it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import plus_one_counters, settle_completely

RAID = "t_spree_raid"
RELIC = "t_raid_relic"
CHARM = "t_raid_charm"
BEAR = "grizzly_bears"
STORMCAT = "t_stormcat"  # copies your instants, keeping the targets


def position(builder, theirs=(RELIC, CHARM, BEAR), mine=()):
    game = (
        builder(players=2)
        .battlefield(0, ["plains"] + ["wastes"] * 4 + list(mine))
        .battlefield(1, list(theirs))
        .hand(0, [RAID])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def casts(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == RAID
    ]


def offered(game) -> set[tuple[int, ...]]:
    return {a.spree_modes for a in casts(game)}


def kinds(game, action) -> list[str]:
    """What each declared target is: a player, or the card id of an object."""
    return [
        "player" if ref.kind == "player" else game.state.objects[ref.id].def_id
        for ref in action.targets
    ]


def oid(game, card_id: str) -> int:
    return next(o.oid for o in game.state.battlefield_objects() if o.def_id == card_id)


def on_battlefield(game, card_id: str) -> bool:
    return any(o.def_id == card_id for o in game.state.battlefield_objects())


def cast(game, modes: tuple[int, ...], *, player: int = 1):
    action = next(
        a
        for a in casts(game)
        if a.spree_modes == modes
        and all(ref.id == player for ref in a.targets if ref.kind == "player")
    )
    game.apply(action)
    settle_completely(game)


class TestEachSubsetDeclaresItsOwnTargets:
    def test_every_subset_is_offered_when_every_target_exists(self, builder):
        assert offered(position(builder)) == {
            (0,), (1,), (2,), (0, 1), (0, 2), (1, 2), (0, 1, 2)
        }

    def test_one_mode_declares_one_target(self, builder):
        game = position(builder)
        for action in casts(game):
            if action.spree_modes == (0,):
                assert kinds(game, action) == [RELIC]
            if action.spree_modes == (1,):
                assert kinds(game, action) == [CHARM]
            if action.spree_modes == (2,):
                assert kinds(game, action) == ["player"]

    def test_two_modes_declare_exactly_their_two(self, builder):
        game = position(builder)
        lines = [a for a in casts(game) if a.spree_modes == (0, 2)]
        assert lines and all(kinds(game, a) == [RELIC, "player"] for a in lines)

    def test_a_missing_target_withdraws_only_the_subsets_that_need_it(self, builder):
        """No enchantment: every subset with the enchantment mode goes, no other."""
        game = position(builder, theirs=(RELIC, BEAR))
        assert offered(game) == {(0,), (2,), (0, 2)}

    def test_no_artifact_or_enchantment_leaves_the_player_mode(self, builder):
        assert offered(position(builder, theirs=(BEAR,))) == {(2,)}


class TestResolution:
    def test_only_the_bought_modes_happen(self, builder):
        game = position(builder)
        cast(game, (0, 2))
        assert not on_battlefield(game, RELIC)
        assert on_battlefield(game, CHARM)
        assert plus_one_counters(game, oid(game, BEAR)) == 1

    def test_a_later_mode_reads_its_own_ref(self, builder):
        """(1, 2) stores the enchantment first; it must be read as the enchantment."""
        game = position(builder)
        cast(game, (1, 2))
        assert on_battlefield(game, RELIC)
        assert not on_battlefield(game, CHARM)
        assert plus_one_counters(game, oid(game, BEAR)) == 1

    def test_all_three(self, builder):
        game = position(builder)
        cast(game, (0, 1, 2))
        assert not on_battlefield(game, RELIC)
        assert not on_battlefield(game, CHARM)
        assert plus_one_counters(game, oid(game, BEAR)) == 1

    def test_the_target_player_is_whose_creatures(self, builder):
        game = position(builder, mine=[BEAR])
        cast(game, (2,), player=0)
        mine = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == BEAR)
        theirs = next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR)
        assert plus_one_counters(game, mine) == 1
        assert plus_one_counters(game, theirs) == 0


class TestACopyKeepsTheBoughtModes:
    def test_a_copy_of_the_player_mode_counts_again(self, builder):
        """707.10: the copy has the original's spree modes, and its target."""
        game = position(builder, mine=[STORMCAT])
        cast(game, (2,))
        assert plus_one_counters(game, oid(game, BEAR)) == 2


class TestLoaderRefusals:
    def _card(self, target: dict, **extra) -> CardModel:
        fields = {
            "id": "t_spree_target_probe",
            "name": "Spree Target Probe",
            "mana_cost": "{W}",
            "types": ["Instant"],
            "spree": [{"mana": "{1}"}, {"mana": "{1}"}],
            "targets": [target],
            "spell_effects": [
                {"op": "if", "condition": {"spree_mode": 0},
                 "then": [{"op": "destroy", "objects": {"target": "t1"}}]},
                {"op": "if", "condition": {"spree_mode": 1},
                 "then": [{"op": "draw", "player": "you", "amount": {"const": 1}}]},
            ],
        }
        fields.update(extra)
        return CardModel(**fields)

    TARGET = {"id": "t1", "kind": "permanent", "count": 1, "selector": {}}

    def test_the_witness_shape_loads(self):
        compile_card(self._card({**self.TARGET, "spree_mode": 0}))

    def test_a_mode_the_card_lacks(self):
        with pytest.raises(DslError, match="spree mode 2 does not exist"):
            compile_card(self._card({**self.TARGET, "spree_mode": 2}))

    def test_on_a_card_without_spree(self):
        with pytest.raises(DslError, match="spree"):
            compile_card(self._card({**self.TARGET, "spree_mode": 0}, spree=[]))

    def test_beside_mode(self):
        with pytest.raises(DslError):
            compile_card(self._card({**self.TARGET, "spree_mode": 0, "mode": 0}))

    def test_two_variable_targets_in_one_subset(self):
        many = {"kind": "permanent", "count": "any", "selector": {}}
        model = self._card(
            {**many, "id": "t1", "spree_mode": 0},
            targets=[
                {**many, "id": "t1", "spree_mode": 0},
                {**many, "id": "t2", "spree_mode": 1},
            ],
        )
        with pytest.raises(DslError, match="variable-size"):
            compile_card(model)
