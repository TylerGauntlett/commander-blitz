""""You may pay that much life. If you do, draw that many cards."

Niv-Mizzet, Ghost Counsel: "Whenever you gain life, you may pay that much life.
If you do, draw that many cards."

A life price that only the **resolving trigger** knows. `may.pay` accepted a
`pay_life` value expression, but `costs.life_cost` reads one in a bare context
of its own (War Room's, an activated ability's cost with no bindings), so
``{"binding": "amount"}`` came out 0 -- every gain a free draw of that many.
`op_may` now reads the expression in its own context and fixes it to an integer
before the affordability check, so the check and the charge see one price.

Rule 119.4: a player may pay life only if their life total is at least the
payment, and can always pay 0. Rule 118.4 makes the payment a loss of life, so
a life total that can't change cannot pay anything above 0. The near miss is a
`may` around `lose_life`: that is not a payment, and is offered at any life
total and to a locked one.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

COUNSEL = "t_ghost_counsel"
GAIN = "t_gain_three"

PAY_THAT_MUCH = {
    "op": "may",
    "pay": {"pay_life": {"binding": "amount"}},
    "effects": [{"op": "draw", "player": "you", "amount": {"binding": "amount"}}],
}


def position(builder, *, life: int = 20):
    """The Counsel, a Plains to cast a gain of three with, and a library to draw."""
    game = (
        builder(players=2)
        .battlefield(0, [COUNSEL, "plains"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [GAIN])
        .life(0, life)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def gain_until_asked(game):
    """Cast the gain and pass until the Counsel asks its may."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == GAIN
        )
    )
    for _ in range(100):
        decision = game.pending()
        assert decision is not None, "the game stopped before the Counsel asked"
        if decision.kind is DecisionKind.MAY:
            return decision
        game.apply(_default_answer(game, decision))
    raise AssertionError("the Counsel never asked")


def answer(game, kind: ActionKind) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is kind))


def settle(game) -> None:
    for _ in range(100):
        decision = game.pending()
        if decision is None or (decision.kind is DecisionKind.PRIORITY and not game.state.stack):
            return
        game.apply(_default_answer(game, decision))


def life(game) -> int:
    return game.state.players[0].life


def hand(game) -> int:
    return len(game.state.players[0].hand)


class TestThatMuch:
    def test_it_pays_the_life_gained_and_draws_that_many(self, builder):
        game = position(builder)
        before = hand(game)
        gain_until_asked(game)
        assert life(game) == 23
        answer(game, ActionKind.YES)
        settle(game)

        assert life(game) == 20
        # The gain spell left the hand; three cards came in.
        assert hand(game) == before - 1 + 3

    def test_declining_pays_nothing_and_draws_nothing(self, builder):
        game = position(builder)
        before = hand(game)
        gain_until_asked(game)
        answer(game, ActionKind.NO)
        settle(game)

        assert life(game) == 23
        assert hand(game) == before - 1


def resolve(builder, effects, *, life: int, amount: int, yes: bool = True):
    """Run ``effects`` as a resolving trigger whose ``amount`` binding is
    ``amount``. Returns whether the may was asked."""
    game = (
        builder(players=2)
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .life(0, life)
        .build(advance=False)
    )
    ctx = EffectContext(state=game.state, controller=0, bindings={"amount": amount})
    gen = execute(ctx, effects)
    asked = False
    try:
        decision = next(gen)
        while True:
            if decision.kind is DecisionKind.MAY:
                asked = True
                decision = gen.send([0 if yes else 1])
            else:
                decision = gen.send([0])
    except StopIteration:
        pass
    return game, asked


class TestTheBoundary:
    def test_more_life_than_you_have_is_not_offered(self, builder):
        """119.4: five life cannot pay six, so there is no question and no draw."""
        game, asked = resolve(builder, [PAY_THAT_MUCH], life=5, amount=6)

        assert not asked
        assert life(game) == 5
        assert hand(game) == 0

    def test_exactly_your_life_is(self, builder):
        """118.4: paying down to exactly 0 is legal; losing is a state-based
        action afterwards, not a reason the cost was refused."""
        game, asked = resolve(builder, [PAY_THAT_MUCH], life=6, amount=6)

        assert asked
        assert life(game) == 0
        assert hand(game) == 6

    def test_zero_life_is_always_paid(self, builder):
        """119.4: a player can always pay 0 life -- the yes is a payment of
        nothing, and the "if you do" runs (drawing nothing)."""
        game, asked = resolve(builder, [PAY_THAT_MUCH], life=0, amount=0)

        assert asked
        assert life(game) == 0

    def test_the_price_is_the_binding_not_zero(self, builder):
        """The bug this pins: read in a bare context, the price was 0."""
        game, _ = resolve(builder, [PAY_THAT_MUCH], life=20, amount=4)

        assert life(game) == 16
        assert hand(game) == 4


LOCK = {"op": "lock_life_total", "player": "you", "duration": "until_your_next_turn"}


class TestALockedLifeTotal:
    def test_it_cannot_pay_life(self, builder):
        """118.4 makes paying life a loss, and a locked total cannot lose any:
        not offered, and no free draw. A `lose_life` may would draw here."""
        game, asked = resolve(builder, [LOCK, PAY_THAT_MUCH], life=20, amount=3)

        assert not asked
        assert life(game) == 20
        assert hand(game) == 0

    def test_it_can_still_pay_zero(self, builder):
        _, asked = resolve(builder, [LOCK, PAY_THAT_MUCH], life=20, amount=0)

        assert asked


def compile_with(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_counsel",
                "name": "Bad Counsel",
                "oracle_text": "Whenever you gain life, you may pay that much life. If you do, draw that many cards.",
                "mana_cost": "{4}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "Whenever you gain life, you may pay that much life. If you do, draw that many cards.",
                        "trigger": {"event": "you_gain_life", "controller": "you"},
                        "effects": [effect],
                    }
                ],
            }
        )
    )


class TestTheLoader:
    def test_the_good_one_loads(self):
        compile_with(PAY_THAT_MUCH)

    def test_a_malformed_price_is_refused(self):
        """A misspelt expression would otherwise price the life at 0."""
        with pytest.raises(DslError, match="pay_life"):
            compile_with({**PAY_THAT_MUCH, "pay": {"pay_life": {"bindng": "amount"}}})
