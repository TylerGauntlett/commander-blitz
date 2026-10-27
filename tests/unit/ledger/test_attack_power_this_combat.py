"""Pack tactics -- the attackers' total power, read as they were declared.

    "Pack tactics -- Whenever this creature attacks, if you attacked with
    creatures with total power 6 or greater this combat, you may put a Dragon
    creature card from your hand onto the battlefield tapped and attacking."
                                                    -- Minion of the Mighty

Pack tactics is an ability word (CR 207.2c), so it has no rule of its own: the
whole mechanic is an intervening-if (603.4) over one number. The rulings fix
when that number is read -- **as attackers are declared** -- and that is what
rules out the near miss. `power_of` over `{"attacking": true}` sums the live
board, so a trigger whose condition held at declaration would fail its recheck
on resolution once an attacker was killed, bounced or shrunk in response, and a
creature put onto the battlefield attacking (never declared, 508.4) would count.

`TurnLedger.attack_power_this_combat` is therefore a number frozen in
`GameState._tally` at `ATTACKERS_DECLARED`, which fires before any
creature's ATTACKS trigger, and reset by `combat.start_combat`, because the
printed words are "this combat" and not "this turn".

The witness is Test Pack Hunter, a 2/2 that puts a +1/+1 counter on itself
under the printed condition -- Gnoll Hunter's text.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.engine.combat import start_combat
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.conditions import evaluate_condition
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.values import evaluate_value, validate_value
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.zones import move_object
from tests.conftest import find_action, oids_of, only_oid, pass_until, plus_one_counters

HUNTER = "t_pack_hunter"  # {1}{G} 2/2, pack tactics: +1/+1 counter on itself
BEAR = "t_bear"  # {1}{G} 2/2
BIG = "t_big"  # {5}{G} 6/6
BOLT = "t_bolt"  # {R} instant, so priority stops while the trigger is on the stack

VALUE = {"attack_power_this_combat": "you"}
PACK = {"cmp": ">=", "left": VALUE, "right": {"const": 6}}


def board(builder, mine):
    return (
        builder(players=2)
        .battlefield(0, ["mountain"] * 2)
        .hand(0, [BOLT])
        .battlefield(0, list(mine))
        .build()
    )


def declare(game, *oids: int) -> None:
    """Declare these attackers and lock the declaration in, triggers and all."""
    pass_until(
        game, lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS
    )
    for oid in oids:
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),)
            )
        )
    game.apply(find_action(game, ActionKind.FINISH_DECLARATION))


def power(game, controller: int = 0) -> int:
    return evaluate_value(EffectContext(state=game.state, controller=controller), VALUE)


def resolve_stack(game) -> None:
    pass_until(game, lambda g: not g.state.stack)


class TestTheTotalIsReadAtTheDeclaration:
    def test_it_sums_the_declared_attackers(self, builder):
        game = board(builder, (HUNTER, BEAR, BEAR))
        declare(game, only_oid(game, HUNTER, 0), *oids_of(game, BEAR, 0))
        assert power(game) == 6

    def test_only_declared_creatures_count(self, builder):
        game = board(builder, (HUNTER, BEAR, BEAR))
        declare(game, only_oid(game, HUNTER, 0), oids_of(game, BEAR, 0)[0])
        assert power(game) == 4, "the bear that stayed home adds nothing"

    def test_before_any_declaration_it_is_nought(self, builder):
        game = board(builder, (BEAR,))
        assert power(game) == 0

    def test_an_opponents_total_is_not_yours(self, builder):
        game = board(builder, (BIG,))
        declare(game, only_oid(game, BIG, 0))
        assert power(game, controller=1) == 0
        assert evaluate_value(
            EffectContext(state=game.state, controller=1), {"attack_power_this_combat": "each_opponent"}
        ) == 6

    def test_it_reads_derived_power(self, builder):
        """An anthem or a counter counts: the power the attacker has, not its print."""
        from commanderblitz.engine.primitives import add_counters

        game = board(builder, (HUNTER, BEAR))
        bear = only_oid(game, BEAR, 0)
        add_counters(game.state, bear, "+1/+1", 2)
        declare(game, only_oid(game, HUNTER, 0), bear)
        assert power(game) == 6


class TestTheTriggerIsAnInterveningIf:
    def test_six_power_puts_the_counter_on(self, builder):
        game = board(builder, (HUNTER, BEAR, BEAR))
        hunter = only_oid(game, HUNTER, 0)
        declare(game, hunter, *oids_of(game, BEAR, 0))
        resolve_stack(game)
        assert plus_one_counters(game, hunter) == 1

    def test_five_power_does_not_trigger(self, builder):
        """The boundary: one short of the printed threshold."""
        game = board(builder, (HUNTER, BEAR))
        hunter = only_oid(game, HUNTER, 0)
        declare(game, hunter, only_oid(game, BEAR, 0))
        assert power(game) == 4
        assert not game.state.stack, "the intervening-if was false when it would trigger"
        resolve_stack(game)
        assert plus_one_counters(game, hunter) == 0

    def test_an_attacker_dying_before_resolution_still_counts(self, builder):
        """The ruling the frozen number exists for, and the near miss's failure."""
        game = board(builder, (HUNTER, BEAR, BEAR))
        hunter = only_oid(game, HUNTER, 0)
        bears = oids_of(game, BEAR, 0)
        declare(game, hunter, *bears)
        assert game.state.stack, "the trigger is waiting to resolve"
        move_object(game.state, bears[0], Zone.GRAVEYARD)

        live = {"power_of": {"objects": {"zone": "battlefield", "attacking": True, "controller": "you"}}}
        assert evaluate_value(EffectContext(state=game.state, controller=0), live) == 4, (
            "the live board has forgotten the dead bear -- the approximation refused"
        )
        assert evaluate_condition(game.state, PACK, controller=0)
        resolve_stack(game)
        assert plus_one_counters(game, hunter) == 1, "the recheck on resolution passed"

    def test_shrinking_an_attacker_does_not_change_the_total(self, builder):
        from commanderblitz.engine.primitives import add_counters

        game = board(builder, (HUNTER, BEAR, BEAR))
        hunter = only_oid(game, HUNTER, 0)
        bears = oids_of(game, BEAR, 0)
        declare(game, hunter, *bears)
        add_counters(game.state, bears[0], "-1/-1", 1)
        assert power(game) == 6


class TestItIsPerCombat:
    def test_a_new_combat_starts_from_nought(self, builder):
        """An extra combat's pack tactics counts only that combat's attackers."""
        game = board(builder, (BIG,))
        declare(game, only_oid(game, BIG, 0))
        assert power(game) == 6
        start_combat(game.state)
        assert power(game) == 0

    def test_cleanup_clears_it(self, builder):
        game = board(builder, (BIG,))
        declare(game, only_oid(game, BIG, 0))
        game.state.turn_ledger.clear()
        assert power(game) == 0

    def test_a_creature_put_onto_the_battlefield_attacking_adds_nothing(self, builder):
        """508.4: it was never declared, so the ruling's total never saw it."""
        game = board(builder, (HUNTER, BEAR))
        hunter = only_oid(game, HUNTER, 0)
        declare(game, hunter, only_oid(game, BEAR, 0))
        before = power(game)
        ctx = EffectContext(state=game.state, controller=0, source_oid=hunter)
        effects = [
            {"op": "create_token", "token": "dragon_6_6_r_flying", "tapped": True, "attacking": True}
        ]
        with contextlib.suppress(StopIteration):
            gen = execute(ctx, effects)
            while True:
                next(gen)
        dragon = only_oid(game, "dragon_6_6_r_flying", 0)
        assert game.state.combat.attackers.get(dragon) == 1, "it is attacking"
        assert power(game) == before == 4


class TestTheLoaderGuard:
    def test_a_player_spec_loads(self):
        validate_value(VALUE, "test")

    @pytest.mark.parametrize("bad", [True, None, 3, {"you": True}, "everyone"])
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(DslError, match="attack_power_this_combat"):
            validate_value({"attack_power_this_combat": bad}, "test")
