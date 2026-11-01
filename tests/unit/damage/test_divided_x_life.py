"""X damage divided, where X is life paid as an additional cost -- 601.2b before 601.2c.

    Fire Covenant -- "As an additional cost to cast this spell, pay X life.
    Fire Covenant deals X damage divided as you choose among any number of
    target creatures."

601.2b announces X, 601.2c declares the targets, 601.2d divides the damage,
and 601.2h pays the life. Divided damage gives every target at least one, so
"any number of target creatures" is capped by X -- which can only be done if X
is known when the targets are chosen. `pay_life_x`'s X used to be asked after
the mana was paid, behind the target declaration, so the loader refused a
divided amount that read it: a division of X could have been asked over more
targets than X.

`Game._cast` now announces `pay_life_x`'s X first, before the deferred "any
number" pick, and the pick is capped at X through `engine.division`. Where the
targets are on the cast line instead (a targeting tax on the board stops the
deferral), legality caps them at the most X the life total allows, and the
announcement is floored at the number declared. The life is still paid where it
was, after the mana. A mana {X} is untouched: its ceiling reads cost
reductions that read the targets, so it stays after them and the loader still
refuses a divided mana X.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import action_for_card, declare_targets, oids_of, pass_until

COVENANT = "t_fire_covenant"
WALL = "t_dd_wall"  # 0/6, survives any share


def position(builder, *, theirs=(WALL,) * 4, life: int = 20):
    game = (
        builder(players=2)
        .battlefield(0, ["swamp", "swamp", "mountain", "mountain", "mountain", "mountain"])
        .hand(0, [COVENANT, "lightning_bolt"])
        .battlefield(1, list(theirs))
        .life(0, life)
        .library(0, ["swamp"] * 10)
        .library(1, ["swamp"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def announce(game, x: int) -> None:
    decision = game.pending()
    assert decision is not None and decision.kind is DecisionKind.CHOOSE_X, decision
    game.apply(next(a for a in game.legal_actions() if getattr(a, "choice", None) == x))


def cast_for(game, x: int) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, COVENANT))
    announce(game, x)


def give_rest_to(game, oid: int) -> None:
    """Answer every remaining 'one more damage to which target?' with ``oid``."""
    for _ in range(50):
        pending = game.pending()
        if pending is None or pending.context.get("purpose") != "divide_damage":
            return
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


class TestXIsAnnouncedBeforeTheTargets:
    def test_the_first_question_is_x(self, builder):
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, COVENANT))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        assert max(a.choice for a in game.legal_actions() if a.kind is ActionKind.CHOOSE) == 20

    def test_the_target_pick_is_capped_at_x(self, builder):
        game = position(builder, theirs=[WALL] * 6)
        cast_for(game, 3)
        pending = game.pending()
        assert pending.context["purpose"] == "target"
        assert (pending.min_count, pending.max_count) == (0, 3)

    def test_a_large_x_is_capped_by_the_board_instead(self, builder):
        game = position(builder, theirs=[WALL] * 2)
        cast_for(game, 9)
        assert game.pending().max_count == 2

    def test_x_of_zero_targets_nothing_and_costs_nothing(self, builder):
        game = position(builder)
        walls = oids_of(game, WALL, 1)
        cast_for(game, 0)
        resolve(game)
        assert game.state.players[0].life == 20
        assert all(damage(game, w) == 0 for w in walls)


class TestTheDivisionIsOfX:
    def test_three_split_two_and_one(self, builder):
        game = position(builder)
        walls = oids_of(game, WALL, 1)
        cast_for(game, 3)
        declare_targets(game, walls[0], walls[1])
        give_rest_to(game, walls[1])
        resolve(game)
        assert [damage(game, w) for w in walls[:2]] == [1, 2]

    def test_one_target_takes_all_of_x(self, builder):
        game = position(builder)
        wall = oids_of(game, WALL, 1)[0]
        cast_for(game, 5)
        declare_targets(game, wall)
        resolve(game)
        assert damage(game, wall) == 5

    def test_the_life_is_paid(self, builder):
        game = position(builder)
        wall = oids_of(game, WALL, 1)[0]
        cast_for(game, 4)
        declare_targets(game, wall)
        resolve(game)
        assert game.state.players[0].life == 16

    def test_x_rides_on_the_stack_item(self, builder):
        game = position(builder)
        walls = oids_of(game, WALL, 1)
        cast_for(game, 4)
        declare_targets(game, *walls[:2])
        give_rest_to(game, walls[0])
        item = next(i for i in game.state.stack if i.kind == "spell")
        assert item.x == 4
        assert sorted(n for _, n in item.bindings["distribution"]["t1"]) == [1, 3]


class TestTargetsOnTheLine:
    """Terror of the Peaks taxes spells that target it, which keeps the "any
    number" pick on the cast line: the line's targets are fixed first, so the
    announcement is floored at their number (each must be dealt one)."""

    def test_x_is_floored_at_the_declared_targets(self, builder):
        game = position(builder, theirs=["terror_of_the_peaks", WALL], life=20)
        lines = [
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == COVENANT
            and len(a.targets) == 2
        ]
        assert lines, "a two-target line is offered"
        game.apply(lines[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_X
        offered = [option.value for option in decision.options]
        assert offered[0] == 2, "two targets, each dealt at least one"
        assert offered[-1] == 17, "20 life less Terror's 3-life tax"


class TestTheLoader:
    def _card(self, **extra):
        data = {
            "id": "x",
            "name": "X",
            "oracle_text": "X.",
            "mana_cost": "{1}",
            "types": ["Instant"],
            "targets": [
                {"id": "t1", "kind": "permanent", "count": "any",
                 "selector": {"types": ["Creature"], "controller": "any"}}
            ],
            "spell_effects": [{"op": "damage", "amount": {"x": True}, "divided": "t1"}],
            **extra,
        }
        return compile_card(CardModel.model_validate(data))

    def test_x_from_pay_life_x_loads(self):
        self._card(additional_cost={"pay_life_x": True})

    def test_a_mana_x_is_still_refused(self):
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="announced X"):
            self._card(mana_cost="{X}{R}")
