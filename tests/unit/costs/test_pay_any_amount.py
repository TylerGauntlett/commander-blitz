"""'You may pay any amount of {R}. When you do, it deals that much damage.'

Leyline Tyrant: "When this creature dies, you may pay any amount of {R}. When
you do, it deals that much damage to any target."

A player-chosen count of **one coloured symbol**, paid while a triggered ability
resolves. Rule 107.1c lets a player choose any amount, 118.3 bounds it by what
they can actually pay, and 603.12 makes "when you do" a reflexive trigger that
fires only if the payment happened -- and paying none of it is not paying. Each
near miss is a different card:

- `may.x` announces an X, and ``ManaCost.with_x`` adds X as *generic*, so a
  Tyrant written that way burns for mana of any colour -- the Forest in these
  positions would pay;
- `pay.times` scales a cost by a number the card computes, never one the
  player picks;
- `may` with `repeat` around {R} is several separate payments with no count to
  bind, and would split the damage into several events.

`any_amount` on `may` composes what exists: after the yes, `ask_x` (the
`choose_x` decision a spell's X uses) offers 1 up to `max_affordable_times`
-- the solver's answer for the symbol scaled N times -- `pay` charges exactly
that, and the count is bound for the reflexive ability to read. Red mana a
`mana_retention` static kept counts, which is how the card is played: the mana
it was holding when it died is what the trigger spends.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost, max_affordable_times
from commanderblitz.engine.turn import advance
from commanderblitz.engine.zones import destroy
from tests.conftest import _default_answer, only_oid

TYRANT = "t_any_red_tyrant"
R = SYMBOL_INDEX["R"]


def position(builder, *, mountains: int, forests: int = 0):
    """The Tyrant with ``mountains`` and ``forests`` beside it; nobody's hand matters."""
    game = (
        builder(players=2)
        .battlefield(0, [TYRANT, *["mountain"] * mountains, *["forest"] * forests])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    return game


def kill_until_asked(game, kind: DecisionKind):
    """Destroy the Tyrant and pass until its trigger asks ``kind``."""
    destroy(game.state, only_oid(game, TYRANT))
    for _ in range(100):
        decision = game.pending()
        assert decision is not None, "the game stopped before the Tyrant asked"
        if decision.kind is kind:
            return decision
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"the Tyrant never asked {kind}")


def answer(game, kind: ActionKind) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is kind))


def choose(game, value: int) -> None:
    decision = game.pending()
    index = next(i for i, o in enumerate(decision.options) if o.value == value)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )


def aim_at_opponent(game) -> None:
    """Answer the reflexive ability's target with player 1, then let it resolve."""
    for _ in range(100):
        decision = game.pending()
        if decision is None or (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            index = next(
                i
                for i, o in enumerate(decision.options)
                if o.ref is not None and o.ref.kind == "player" and o.ref.id == 1
            )
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == index
                )
            )
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the burn never resolved")


def untapped(game, card_id: str) -> int:
    return sum(
        1 for obj in game.state.battlefield_objects(0) if obj.def_id == card_id and not obj.tapped
    )


def life(game, pid: int = 1) -> int:
    return game.state.players[pid].life


class TestTheCeiling:
    def test_it_is_what_the_player_can_pay_in_red(self, builder):
        """Three Mountains and four Forests: 1..3, never 7 -- the Forests make
        mana but not red, which is the whole difference from `may.x`."""
        game = position(builder, mountains=3, forests=4)
        kill_until_asked(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.player == 0
        assert [o.value for o in decision.options] == [1, 2, 3]

    def test_no_red_at_all_is_not_offered(self, builder):
        """Forests only: {R} is unaffordable once, so the may is not asked and
        no burn is put on the stack."""
        game = position(builder, mountains=0, forests=4)
        start = life(game)
        destroy(game.state, only_oid(game, TYRANT))
        for _ in range(100):
            decision = game.pending()
            assert decision is None or decision.kind is not DecisionKind.MAY
            if decision is None or (
                decision.kind is DecisionKind.PRIORITY
                and not game.state.stack
                and not game.state.pending_triggers
            ):
                break
            game.apply(_default_answer(game, decision))
        assert life(game) == start
        assert untapped(game, "forest") == 4

    def test_exactly_one_payable_asks_no_count(self, builder):
        """The floor is 1, so a single Mountain leaves nothing to choose."""
        game = position(builder, mountains=1)
        start = life(game)
        kill_until_asked(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        assert game.pending() is None or game.pending().kind is not DecisionKind.CHOOSE_X
        aim_at_opponent(game)

        assert life(game) == start - 1
        assert untapped(game, "mountain") == 0


class TestWhenYouDo:
    def test_n_is_paid_and_n_is_dealt(self, builder):
        game = position(builder, mountains=5)
        start = life(game)
        kill_until_asked(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        choose(game, 3)
        aim_at_opponent(game)

        assert life(game) == start - 3
        assert untapped(game, "mountain") == 2

    def test_declining_pays_nothing_and_burns_nothing(self, builder):
        game = position(builder, mountains=5)
        start = life(game)
        kill_until_asked(game, DecisionKind.MAY)
        answer(game, ActionKind.NO)
        aim_at_opponent(game)

        assert life(game) == start
        assert untapped(game, "mountain") == 5
        assert not game.state.stack

    def test_zero_is_never_on_offer(self, builder):
        """Paying none is not paying, so "when you do" cannot fire off {0}: the
        no is the only way to pay nothing."""
        game = position(builder, mountains=4)
        kill_until_asked(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)

        assert 0 not in [o.value for o in game.pending().options]


class TestKeptRedMana:
    def test_red_mana_kept_across_the_turn_pays_it(self, builder):
        """The way the card is played: red floated on one turn, held by the
        Tyrant's own `mana_retention`, spent by its death trigger on the next.
        No lands at all, so only the kept pool can pay."""
        game = position(builder, mountains=0)
        game.state.players[0].mana_pool.add("R", 4)
        turn = game.state.turn
        while game.state.turn == turn:
            advance(game.state)
        assert game.state.players[0].mana_pool.amounts[R] == 4

        start = life(game)
        kill_until_asked(game, DecisionKind.MAY)
        answer(game, ActionKind.YES)
        assert [o.value for o in game.pending().options] == [1, 2, 3, 4]
        choose(game, 4)
        aim_at_opponent(game)

        assert life(game) == start - 4
        assert game.state.players[0].mana_pool.amounts[R] == 0


class TestTheProbe:
    """`max_affordable_times` in isolation: the symbol scaled, not X added."""

    def test_only_the_named_symbol_counts(self):
        pool = [0] * len(SYMBOL_INDEX)
        pool[R] = 2
        pool[SYMBOL_INDEX["G"]] = 5
        assert max_affordable_times(ManaCost.parse("{R}"), pool, []) == 2

    def test_nothing_payable_is_zero(self):
        assert max_affordable_times(ManaCost.parse("{R}"), [0] * len(SYMBOL_INDEX), []) == 0


def compile_with(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_tyrant",
                "name": "Bad Tyrant",
                "oracle_text": "When this creature dies, you may pay any amount of {R}.",
                "mana_cost": "{4}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "When this creature dies, you may pay any amount of {R}.",
                        "trigger": {"event": "dies", "source": "self"},
                        "effects": [effect],
                    }
                ],
            }
        )
    )


GAIN = [{"op": "gain_life", "player": "you", "amount": {"binding": "paid"}}]
GOOD = {"as": "paid"}


class TestTheLoaderRefuses:
    def test_the_good_one_loads(self):
        compile_with({"op": "may", "pay": {"mana": "{R}"}, "any_amount": GOOD, "effects": GAIN})

    def test_colorless_loads(self):
        compile_with({"op": "may", "pay": {"mana": "{C}"}, "any_amount": GOOD, "effects": GAIN})

    @pytest.mark.parametrize("mana", ["{1}", "{R}{R}", "{X}", "{1}{R}", "{R/G}", ""])
    def test_anything_but_one_symbol(self, mana):
        with pytest.raises(DslError, match="any_amount"):
            compile_with(
                {"op": "may", "pay": {"mana": mana}, "any_amount": GOOD, "effects": GAIN}
            )

    def test_another_cost_beside_it(self):
        with pytest.raises(DslError, match="one mana symbol and nothing else"):
            compile_with(
                {"op": "may", "pay": {"mana": "{R}", "pay_life": 2}, "any_amount": GOOD,
                 "effects": GAIN}
            )

    def test_with_times(self):
        with pytest.raises(DslError, match="times"):
            compile_with(
                {"op": "may", "pay": {"mana": "{R}", "times": 2}, "any_amount": GOOD,
                 "effects": GAIN}
            )

    def test_no_binding(self):
        with pytest.raises(DslError, match="as"):
            compile_with({"op": "may", "pay": {"mana": "{R}"}, "any_amount": {}, "effects": GAIN})

    def test_an_unknown_key(self):
        with pytest.raises(DslError, match="unsupported"):
            compile_with(
                {"op": "may", "pay": {"mana": "{R}"}, "any_amount": {**GOOD, "max": 3},
                 "effects": GAIN}
            )

    def test_with_repeat(self):
        with pytest.raises(DslError, match="repeat"):
            compile_with(
                {"op": "may", "pay": {"mana": "{R}"}, "any_amount": GOOD, "repeat": True,
                 "effects": GAIN}
            )

    def test_on_a_may_with_no_payment(self):
        with pytest.raises(DslError, match="any_amount"):
            compile_with({"op": "may", "any_amount": GOOD, "effects": GAIN})

    def test_on_another_op(self):
        with pytest.raises(DslError, match="any_amount"):
            compile_with({"op": "gain_life", "player": "you", "amount": 1, "any_amount": GOOD})
