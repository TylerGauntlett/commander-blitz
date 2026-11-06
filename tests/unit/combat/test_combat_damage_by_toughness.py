""""Assigns combat damage equal to its toughness rather than its power" (510.1a).

Rule 510.1a has each creature assign combat damage equal to its power. Doran,
Assault Formation, Felothar the Steadfast and Baldin, Century Herdmaster
substitute toughness for power **at assignment and nowhere else**. The near
misses all get some creature wrong: `buff`/`set_pt` change power itself, which a
fight, "power 4 or greater" and Felothar's own "discard cards equal to its
power" would all read; `replace_damage` scales an amount already computed from
power.

So `combat.combat_damage_amount` reads one predicate,
`player_statics.assigns_damage_by_toughness`, for every attacker and every
blocker, and the lethal-first walk and trample (510.1c) divide what it returns.
Pinned below: the static on your creatures only; Baldin's any-controller form
that holds only during its controller's turn; the blocker's side; trample's
excess; power left alone; and the timed op (Walking Bulwark) on its target
only, until end of turn.

The witnesses are Assault Formation, Felothar the Steadfast, Baldin, Century
Herdmaster and Walking Bulwark; the `t_cdt_*` cards are their damage clauses
alone.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.combat import combat_damage_amount
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import assigns_damage_by_toughness
from tests.conftest import attack_with, only_oid, pass_until, pt
from tests.unit.combat.test_combat import (
    block_with,
    done,
    resolve_combat,
    to_attackers,
    to_blockers,
)

FORMATION = "t_cdt_formation"  # each creature you control: toughness
HERDMASTER = "t_cdt_herdmaster"  # 1/3; during your turn, each creature: toughness
BRACE = "t_cdt_brace"  # {T}: until end of turn, target creature: toughness
TOWER = "t_cdt_tower"  # 1/5 trample
BEAR = "t_bear"  # 2/2


def position(builder, mine=(), theirs=(), *, active=0):
    """``mine`` for player 0, ``theirs`` for player 1, at ``active``'s main phase."""
    b = builder(players=2)
    if mine:
        b.battlefield(0, list(mine))
    if theirs:
        b.battlefield(1, list(theirs))
    return b.active(active).step(Step.UNTAP).build()


def swing(game, attacker, *, blocker=None, defender=1):
    """Attack with ``attacker``, optionally blocked by ``blocker``, through damage."""
    to_attackers(game)
    attack_with(game, attacker, defender)
    done(game)
    if blocker is not None:
        to_blockers(game)
        block_with(game, blocker, attacker)
        done(game)
    resolve_combat(game)


class TestTheStatic:
    def test_an_attacker_deals_its_toughness(self, builder):
        game = position(builder, mine=(FORMATION, TOWER))
        swing(game, only_oid(game, TOWER, 0))
        assert game.state.players[1].life == 35

    def test_the_baseline_is_power(self, builder):
        game = position(builder, mine=(TOWER,))
        swing(game, only_oid(game, TOWER, 0))
        assert game.state.players[1].life == 39

    def test_power_itself_is_untouched(self, builder):
        """The substitution is in assignment only -- every other power read sees 1."""
        game = position(builder, mine=(FORMATION, TOWER))
        tower = only_oid(game, TOWER, 0)
        assert pt(game, tower) == (1, 5)
        assert assigns_damage_by_toughness(game.state, tower)
        assert combat_damage_amount(game.state, tower) == 5

    def test_a_blocker_deals_its_toughness(self, builder):
        """The blocker's half of 510.1a: player 1's Tower kills the Bear it blocks."""
        game = position(builder, mine=(BEAR,), theirs=(FORMATION, TOWER))
        bear = only_oid(game, BEAR, 0)
        swing(game, bear, blocker=only_oid(game, TOWER, 1))
        assert bear not in game.state.battlefield

    def test_it_reaches_only_your_creatures(self, builder):
        """"Each creature **you control**": the opponent's Tower deals 1."""
        game = position(builder, mine=(FORMATION, BEAR), theirs=(TOWER,))
        bear = only_oid(game, BEAR, 0)
        assert not assigns_damage_by_toughness(game.state, only_oid(game, TOWER, 1))
        swing(game, bear, blocker=only_oid(game, TOWER, 1))
        assert bear in game.state.battlefield

    def test_trample_assigns_the_excess_of_toughness(self, builder):
        """510.1c over the substituted amount: 2 lethal to the Bear, 3 through."""
        game = position(builder, mine=(FORMATION, TOWER), theirs=(BEAR,))
        bear = only_oid(game, BEAR, 1)
        swing(game, only_oid(game, TOWER, 0), blocker=bear)
        assert bear not in game.state.battlefield
        assert game.state.players[1].life == 37

    def test_a_zero_power_creature_deals_its_toughness(self, builder):
        """A 0/4 deals 4: the creature's own power of 0 is not a floor."""
        game = position(builder, mine=(FORMATION, "t_wall"))
        wall = only_oid(game, "t_wall", 0)
        assert combat_damage_amount(game.state, wall) == 4


class TestDuringYourTurn:
    def test_your_attacker_deals_its_toughness(self, builder):
        game = position(builder, mine=(HERDMASTER, TOWER))
        swing(game, only_oid(game, TOWER, 0))
        assert game.state.players[1].life == 35

    def test_each_creature_includes_the_opponents(self, builder):
        """"Each creature", any controller: their blocking Tower deals 5."""
        game = position(builder, mine=(HERDMASTER, BEAR), theirs=(TOWER,))
        bear = only_oid(game, BEAR, 0)
        swing(game, bear, blocker=only_oid(game, TOWER, 1))
        assert bear not in game.state.battlefield

    def test_not_during_the_opponents_turn(self, builder):
        game = position(builder, mine=(HERDMASTER,), theirs=(TOWER,), active=1)
        tower = only_oid(game, TOWER, 1)
        assert not assigns_damage_by_toughness(game.state, tower)
        swing(game, tower, defender=0)
        assert game.state.players[0].life == 39


class TestTheTimedOp:
    def activate(self, game, target):
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.ACTIVATE
            and game.state.objects[a.source].def_id == BRACE
            and any(t.id == target for t in a.targets)
        )
        game.apply(action)
        pass_until(game, lambda g: not g.state.stack)

    def board(self, builder):
        return (
            builder(players=2)
            .battlefield(0, [BRACE, TOWER, "t_wall"])
            .active(0)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )

    def test_the_target_deals_its_toughness(self, builder):
        game = self.board(builder)
        tower = only_oid(game, TOWER, 0)
        self.activate(game, tower)
        assert pt(game, tower) == (1, 5)
        swing(game, tower)
        assert game.state.players[1].life == 35

    def test_only_the_target(self, builder):
        game = self.board(builder)
        tower = only_oid(game, TOWER, 0)
        self.activate(game, tower)
        assert not assigns_damage_by_toughness(game.state, only_oid(game, "t_wall", 0))

    def test_it_ends_at_cleanup(self, builder):
        game = self.board(builder)
        tower = only_oid(game, TOWER, 0)
        self.activate(game, tower)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn != turn)
        assert not assigns_damage_by_toughness(game.state, tower)


def _card(ability: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": "X.",
            "mana_cost": "{G}",
            "types": ["Artifact"],
            "abilities": [ability],
        }
    )


TARGET = [{"id": "t1", "kind": "permanent", "selector": {"zone": "battlefield", "types": ["Creature"]}}]


class TestTheLoader:
    def test_the_static_needs_affects(self):
        with pytest.raises(DslError, match="combat_damage_by_toughness needs an 'affects'"):
            compile_card(_card({"kind": "static", "text": "X.", "effect": "combat_damage_by_toughness"}))

    def test_the_op_needs_objects(self):
        ability = {
            "kind": "activated", "text": "X.", "cost": {"tap": True},
            "effects": [{"op": "combat_damage_by_toughness"}],
        }
        with pytest.raises(DslError, match="needs 'objects'"):
            compile_card(_card(ability))

    @pytest.mark.parametrize(("duration", "ok"), [("this_turn", True), ("until_your_next_turn", False)])
    def test_the_op_lasts_this_turn_only(self, duration, ok):
        ability = {
            "kind": "activated", "text": "X.", "cost": {"tap": True}, "targets": TARGET,
            "effects": [
                {"op": "combat_damage_by_toughness", "objects": {"target": "t1"}, "duration": duration}
            ],
        }
        if ok:
            compile_card(_card(ability))
        else:
            with pytest.raises(DslError, match="lasts until end of turn"):
                compile_card(_card(ability))
