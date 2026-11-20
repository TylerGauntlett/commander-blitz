"""The damage dealt this way: `damage`'s ``as`` binding.

    "Enter the God-Eternals deals 4 damage to target creature and you gain life
    equal to the damage dealt this way."

The gain reads a number the damage produced, and the number is what was
**actually dealt** (120.3, 120.4): damage that is prevented was never dealt
(615.1, so protection or a shield gains nothing), damage that is replaced is
dealt in its replaced amount (614.1, so a Furnace of Rath gains the doubled
amount), and a creature dealt more than its toughness was still dealt all of
it -- the excess of 120.4a is a different, smaller number, and it is not this
one. The near miss is ``{"const": 4}`` in the `gain_life`, which agrees with the
printed card exactly while nothing touches the damage and gains 4 off a
shielded creature the moment something does.

`primitives.damage_permanent` and `damage_player` have always returned the
damage actually dealt; `op_damage` threw it away. ``as`` keeps it, summed over
every recipient the one op hit, as a plain int read back with
``{"binding": …}`` -- `lose_life`'s "the life lost this way" shape.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.effects import RECORDING_OPS, execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import PermanentShield, TargetRef
from tests.conftest import only_oid, pass_until

DRAIN = "t_ddtw_drain"  # 4 to target creature, gain the damage dealt this way
BEAR = "t_bear"  # a 2/2
WALL = "t_big_wall"  # a 0/9: all 4 marked, none excess
FURNACE = "t_rd_furnace"  # any damage doubled


def position(builder, *, own=(), defender=(BEAR,)):
    """Player 0 with the drain in hand; player 1 with ``defender``."""
    game = (
        builder(players=2)
        .battlefield(0, ["mountain", *own])
        .battlefield(1, [*defender, "plains"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .hand(0, [DRAIN])
        .life(0, 40)
        .life(1, 40)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast_at(game, victim: int) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == DRAIN
        and a.targets
        and a.targets[0].id == victim
    )
    game.apply(action)
    pass_until(
        game,
        lambda g: not g.state.stack
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def run(game, effects, *, targets=None, controller: int = 0) -> EffectContext:
    """Resolve a decision-free effect list and hand back its context."""
    ctx = EffectContext(state=game.state, controller=controller, targets=targets or {})
    for _ in execute(ctx, effects):  # pragma: no cover - nothing here asks
        raise AssertionError("damage asks no questions")
    return ctx


def life(game) -> list[int]:
    return [p.life for p in game.state.players]


class TestTheSpell:
    def test_it_gains_the_damage_dealt(self, builder):
        game = position(builder, defender=(WALL,))
        wall = only_oid(game, WALL, 1)
        cast_at(game, wall)
        assert life(game) == [44, 40]

    def test_overkill_is_still_all_dealt(self, builder):
        """4 into a 2/2 is 4 damage dealt, not the 2 that was lethal (120.4a's
        excess is a different number)."""
        game = position(builder)
        cast_at(game, only_oid(game, BEAR, 1))
        assert life(game) == [44, 40]

    def test_prevented_damage_gains_nothing(self, builder):
        """The whole reason for the binding: a constant would gain 4 here."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        game.state.objects[bear].damage_shields.append(PermanentShield(player=1))
        cast_at(game, bear)
        assert game.state.objects[bear].on_battlefield, "nothing was dealt"
        assert life(game) == [40, 40]

    def test_doubled_damage_gains_the_doubled_amount(self, builder):
        game = position(builder, own=(FURNACE,), defender=(WALL,))
        wall = only_oid(game, WALL, 1)
        cast_at(game, wall)
        assert life(game) == [48, 40]


class TestTheBinding:
    def test_it_is_summed_over_every_recipient(self, builder):
        """One op hitting a creature and a player is both damages."""
        game = position(builder, defender=(WALL,))
        ctx = run(
            game,
            [
                {
                    "op": "damage",
                    "amount": {"const": 3},
                    "objects": {"zone": "battlefield", "controller": "opponent",
                                "types": ["Creature"]},
                    "player": "each_opponent",
                    "as": "dealt",
                }
            ],
        )
        assert ctx.bindings["dealt"] == 6
        assert isinstance(ctx.bindings["dealt"], int)

    def test_excess_to_counts_both_halves(self, builder):
        """Lethal to the creature and the spill to its controller are one
        damage event, and all of it was dealt."""
        game = position(builder)
        bear = only_oid(game, BEAR, 1)
        ctx = run(
            game,
            [{"op": "damage", "target": "t1", "amount": {"const": 5},
              "excess_to": "controller", "as": "dealt"}],
            targets={"t1": (TargetRef.obj(bear),)},
        )
        assert ctx.bindings["dealt"] == 5
        assert life(game)[1] == 37

    def test_a_recipient_gone_binds_zero(self, builder):
        """No recipient was dealt anything; the name is still written, as 0."""
        game = position(builder, defender=())
        ctx = run(
            game,
            [{"op": "damage", "amount": {"const": 4},
              "objects": {"zone": "battlefield", "controller": "opponent",
                          "types": ["Creature"]},
              "as": "dealt"}],
        )
        assert ctx.bindings["dealt"] == 0

    def test_without_as_nothing_is_written(self, builder):
        game = position(builder)
        ctx = run(game, [{"op": "damage", "player": "each_opponent", "amount": {"const": 2}}])
        assert ctx.bindings == {}
        assert life(game) == [40, 38]

    def test_a_second_damage_overwrites_rather_than_accumulates(self, builder):
        """"This way" is this sentence's damage, not every damage so far."""
        game = position(builder)
        ctx = run(
            game,
            [
                {"op": "damage", "player": "each_opponent", "amount": {"const": 3}, "as": "dealt"},
                {"op": "damage", "player": "each_opponent", "amount": {"const": 1}, "as": "dealt"},
            ],
        )
        assert ctx.bindings["dealt"] == 1


class TestTheLoader:
    def test_damage_is_a_recording_op(self):
        assert "damage" in RECORDING_OPS

    def test_as_on_damage_loads(self):
        _validate_effect(
            {"op": "damage", "target": "t1", "amount": {"const": 4}, "as": "dealt"}, "test", {"t1": "permanent"}
        )

    def test_a_non_string_as_is_refused(self):
        with pytest.raises(DslError):
            _validate_effect(
                {"op": "damage", "target": "t1", "amount": {"const": 4}, "as": 4}, "test", {"t1": "permanent"}
            )
