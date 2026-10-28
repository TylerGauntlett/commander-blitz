"""Damage divided among targets on a spell -- 601.2d.

    "Pyrokinesis deals 4 damage divided as you choose among any number of
     target creatures."

The `damage` op deals its whole amount to every object it names, so the near
miss is four damage to *each* target: unbounded damage from one spell. The
division is a 601.2d announcement, made as the spell is cast, after its targets
and before its cost, with every target dealt at least one -- the same walk
`distribute_counters` makes on an activation, reached here from `Game._cast`.

**The amount is read as the spell is cast.** It has to be: the split cannot be
announced before the number is known. Monstrous Onslaught prints the reason --
"where X is the greatest power among creatures you control **as you cast this
spell**" -- and `TestTheAmountIsFixedOnCasting` holds it: the board changing
before resolution changes nothing.

**A target made illegal loses its share** and the rest are not redistributed
(608.2b); asking again on resolution would let the split follow the response.

**There are never more targets than damage**: each needs at least one, so the
"any number" pick is capped by the amount, and legality offers no line beyond.
"""

from __future__ import annotations

import pytest

from commanderblitz.ai.agents import HeuristicAgent
from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy
from tests.conftest import action_for_card, declare_targets, oids_of, only_oid, pass_until

BURN = "t_dd_burn"  # 4 damage divided
ONSLAUGHT = "t_dd_onslaught"  # X divided, X = greatest power you control as cast
OGRE = "t_dd_ogre"  # vanilla 4/4
WALL = "t_dd_wall"  # 0/6, survives any share
BEAR = "t_rc_bear"  # 2/2


def position(builder, hand=(BURN,), *, mine=(), theirs=()):
    """Mountains and ``hand`` for player 0, ``theirs`` for player 1.

    The Lightning Bolt is an anchor: an instant in hand keeps the engine from
    auto-passing the stack away before a test can look at it.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["mountain"] * 6)
        .battlefield(0, list(mine))
        .hand(0, [*hand, "lightning_bolt"])
        .battlefield(1, list(theirs))
        .library(0, ["mountain"] * 10)
        .library(1, ["mountain"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast_at(game, oids, card_id: str = BURN) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    declare_targets(game, *oids)


def division_question(game):
    pending = game.pending()
    if pending is None or pending.kind is not DecisionKind.CHOOSE_OBJECTS:
        return None
    if pending.context.get("purpose") != "divide_damage":
        return None
    return pending


def one_more_to(game, oid: int) -> None:
    assert division_question(game) is not None
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CHOOSE and any(t.id == oid for t in a.targets)
        )
    )


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack)


def damage(game, oid: int) -> int:
    return game.state.objects[oid].damage


def spell_item(game):
    return next(item for item in game.state.stack if item.kind == "spell")


class TestTheDivision:
    def test_one_target_is_dealt_all_four(self, builder):
        game = position(builder, theirs=[WALL])
        wall = only_oid(game, WALL, 1)
        cast_at(game, [wall])
        assert division_question(game) is None, "a forced split asks nothing"
        resolve(game)
        assert damage(game, wall) == 4

    def test_two_targets_split_as_chosen(self, builder):
        game = position(builder, theirs=[WALL, WALL])
        walls = oids_of(game, WALL, 1)
        cast_at(game, walls)
        one_more_to(game, walls[0])
        one_more_to(game, walls[0])
        resolve(game)
        assert [damage(game, w) for w in walls] == [3, 1]

    def test_three_targets_each_take_at_least_one(self, builder):
        game = position(builder, theirs=[WALL, WALL, WALL])
        walls = oids_of(game, WALL, 1)
        cast_at(game, walls)
        one_more_to(game, walls[2])
        resolve(game)
        assert [damage(game, w) for w in walls] == [1, 1, 2]
        assert sum(damage(game, w) for w in walls) == 4

    def test_it_is_announced_before_the_spell_resolves(self, builder):
        """601.2d: the split is on the stack item while the spell waits."""
        game = position(builder, theirs=[WALL, WALL])
        walls = oids_of(game, WALL, 1)
        cast_at(game, walls)
        one_more_to(game, walls[1])
        one_more_to(game, walls[1])
        assert sorted(map(tuple, spell_item(game).bindings["distribution"]["t1"])) == sorted(
            [(walls[0], 1), (walls[1], 3)]
        )

    def test_shares_kill_what_they_are_enough_for(self, builder):
        game = position(builder, theirs=[BEAR, BEAR])
        bears = oids_of(game, BEAR, 1)
        cast_at(game, bears)
        one_more_to(game, bears[0])
        one_more_to(game, bears[1])
        resolve(game)
        assert all(game.state.objects[b].zone is Zone.GRAVEYARD for b in bears)


class TestNeverMoreTargetsThanDamage:
    def test_the_pick_is_capped_at_the_amount(self, builder):
        game = position(builder, theirs=[BEAR] * 6)
        game.apply(action_for_card(game, ActionKind.CAST, BURN))
        assert game.pending().max_count == 4

    def test_an_amount_of_two_caps_at_two(self, builder):
        game = position(builder, hand=[ONSLAUGHT], mine=[BEAR], theirs=[WALL] * 4)
        game.apply(action_for_card(game, ActionKind.CAST, ONSLAUGHT))
        assert game.pending().max_count == 2


class TestAnIllegalTargetTakesItsShare:
    def test_the_survivor_is_not_dealt_more(self, builder):
        game = position(builder, theirs=[WALL, WALL])
        walls = oids_of(game, WALL, 1)
        cast_at(game, walls)
        one_more_to(game, walls[0])
        one_more_to(game, walls[0])
        destroy(game.state, walls[0])
        resolve(game)
        assert damage(game, walls[1]) == 1


class TestTheAmountIsFixedOnCasting:
    """Monstrous Onslaught: "the greatest power among creatures you control as
    you cast this spell"."""

    def test_x_is_the_greatest_power_as_cast(self, builder):
        game = position(builder, hand=[ONSLAUGHT], mine=[OGRE, BEAR], theirs=[WALL])
        wall = only_oid(game, WALL, 1)
        cast_at(game, [wall], ONSLAUGHT)
        resolve(game)
        assert damage(game, wall) == 4

    def test_losing_the_biggest_creature_in_response_changes_nothing(self, builder):
        game = position(builder, hand=[ONSLAUGHT], mine=[OGRE], theirs=[WALL])
        wall = only_oid(game, WALL, 1)
        cast_at(game, [wall], ONSLAUGHT)
        destroy(game.state, only_oid(game, OGRE, 0))
        resolve(game)
        assert damage(game, wall) == 4

    def test_no_creatures_is_nothing_to_divide(self, builder):
        game = position(builder, hand=[ONSLAUGHT], theirs=[WALL])
        game.apply(action_for_card(game, ActionKind.CAST, ONSLAUGHT))
        pending = game.pending()
        if pending is not None and pending.context.get("purpose") == "target":
            assert pending.max_count == 0


class TestTheHeuristicAgent:
    def test_the_extra_point_goes_to_an_opponents_creature(self, builder):
        game = position(builder, mine=[WALL], theirs=[WALL])
        mine, theirs = only_oid(game, WALL, 0), only_oid(game, WALL, 1)
        cast_at(game, [mine, theirs])
        chosen = HeuristicAgent(0).act(game, 0, game.legal_actions())
        assert any(t.id == theirs for t in chosen.targets)


class TestTheLoader:
    def _card(self, effects, *, targets=None, abilities=None, types=("Instant",)):
        data = {
            "id": "x",
            "name": "X",
            "oracle_text": "X deals 4 damage divided as you choose among any number of target creatures.",
            "mana_cost": "{1}",
            "types": list(types),
            "targets": targets if targets is not None else [_target("any")],
            "spell_effects": effects,
        }
        if abilities is not None:
            data["abilities"] = abilities
        return compile_card(CardModel.model_validate(data))

    def test_a_spell_loads(self):
        self._card([{"op": "damage", "amount": 4, "divided": "t1"}])

    def test_an_undeclared_target_is_refused(self):
        with pytest.raises(DslError, match="does not declare"):
            self._card([{"op": "damage", "amount": 4, "divided": "t9"}])

    def test_a_second_recipient_is_refused(self):
        with pytest.raises(DslError, match="only to the targets"):
            self._card([{"op": "damage", "amount": 4, "divided": "t1", "player": "each_opponent"}])

    def test_more_fixed_targets_than_damage_is_refused(self):
        with pytest.raises(DslError, match="at most 2"):
            self._card([{"op": "damage", "amount": 2, "divided": "t1"}], targets=[_target(3)])

    def test_the_announced_x_is_refused(self):
        with pytest.raises(DslError, match="announced X"):
            self._card([{"op": "damage", "amount": {"x": True}, "divided": "t1"}])

    def test_a_nested_division_is_refused(self):
        nested = {"op": "may", "effects": [{"op": "damage", "amount": 4, "divided": "t1"}]}
        with pytest.raises(DslError, match="top-level effect of a spell"):
            self._card([nested])


def _target(count) -> dict:
    return {
        "id": "t1",
        "kind": "permanent",
        "count": count,
        "selector": {"types": ["Creature"], "controller": "any"},
    }
