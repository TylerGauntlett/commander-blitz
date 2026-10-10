""""You may pay {X}, where X is less than or equal to the amount of life you gained."

Well of Lost Dreams: "Whenever you gain life, you may pay {X}, where X is less
than or equal to the amount of life you gained. If you do, draw X cards."

An X announced while a triggered ability **resolves**. X had only ever been
announced as a spell was cast or an ability activated (601.2b, 602.2b), and the
two near misses are each a different card:

- `may`'s `pay` with `times` scales a cost by a number the **card** computes, so
  it could charge exactly X = the life gained and never less -- a Well that
  cannot draw two off a gain of five when only two mana is open;
- `may` with `repeat` around {1} and one card draws one at a time with no
  ceiling at the life gained, and lets the draws inform the payments, which the
  printed card does not.

`x` on `may` composes what exists: after the yes, `ask_x` (the `choose_x`
decision a spell's X already uses) offers 0 up to the **smaller** of the printed
ceiling and what the player can pay, `pay` charges exactly that, and the paid X
is bound for the "if you do" effects. Both halves of the ceiling are tested,
because each alone is a card that looks right on an ordinary board.

**The printed ceiling is optional**, because it is a rule the *card* makes and
not every card makes one. Decree of Justice prints "you may pay {X}. If you do,
create X 1/1 white Soldier creature tokens" with no maximum anywhere on it, and
for that card 118.3 — what the player can actually pay — is the only bound there
is. `x.max` was once required on the grounds that "pay any amount" was join
forces; it is not, since `op_join_forces` asks every player for `{1}` at a time
and binds the sum, where this is announced once by one player. Requiring it
forced an invented number that was load-bearing rather than cosmetic:
`_announce_x` hands `x.max` to `max_affordable_x` as the probe `cap`, so a
made-up 20 silently *became* the ceiling. `TestAnUnboundedX` covers the relaxed
form, and pins the printed-ceiling contrast on the same board so that relaxing
the requirement did not relax the rule.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

WELL = "t_well"
GAIN = "t_gain_three"


def position(builder, *, spare_lands: int):
    """The Well, a Plains to cast the gain with, and ``spare_lands`` Islands."""
    game = (
        builder(players=2)
        .battlefield(0, [WELL, "plains", *["island"] * spare_lands])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [GAIN])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def gain_until_asked(game, kind: DecisionKind):
    """Cast the gain and pass until the Well asks ``kind``; return the decision."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == GAIN
        )
    )
    for _ in range(100):
        decision = game.pending()
        assert decision is not None, "the game stopped before the Well asked"
        if decision.kind is kind:
            return decision
        game.apply(_default_answer(game, decision))
    raise AssertionError(f"the Well never asked {kind}")


def answer_yes(game) -> None:
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.YES))


def choose_x(game, x: int) -> None:
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == x)
    )


def settle(game) -> None:
    for _ in range(100):
        decision = game.pending()
        if decision is None or (decision.kind is DecisionKind.PRIORITY and not game.state.stack):
            return
        game.apply(_default_answer(game, decision))


def untapped_islands(game) -> int:
    return sum(
        1
        for obj in game.state.battlefield_objects(0)
        if obj.def_id == "island" and not obj.tapped
    )


class TestTheCeiling:
    def test_it_is_the_life_gained(self, builder):
        """Ten Islands open, three life gained: X runs 0..3, not 0..10."""
        game = position(builder, spare_lands=10)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.player == 0
        assert [o.value for o in decision.options] == [0, 1, 2, 3]

    def test_it_is_what_the_player_can_pay(self, builder):
        """Three life gained and one Island open: X runs 0..1."""
        game = position(builder, spare_lands=1)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_X
        assert [o.value for o in decision.options] == [0, 1]

    def test_nothing_open_charges_zero_and_asks_no_x(self, builder):
        """X = 0 is the only answer, so it is not asked -- and it draws nothing."""
        game = position(builder, spare_lands=0)
        hand = len(game.state.players[0].hand)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        settle(game)

        assert len(game.state.players[0].hand) == hand - 1


class TestIfYouDo:
    def test_x_is_paid_and_x_is_drawn(self, builder):
        game = position(builder, spare_lands=10)
        hand = len(game.state.players[0].hand)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        choose_x(game, 2)
        settle(game)

        # The gain spell left the hand; two cards came in.
        assert len(game.state.players[0].hand) == hand - 1 + 2
        assert untapped_islands(game) == 8

    def test_a_smaller_x_than_the_gain_is_allowed(self, builder):
        """The whole difference from `pay.times`: one card off a gain of three."""
        game = position(builder, spare_lands=10)
        hand = len(game.state.players[0].hand)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        choose_x(game, 1)
        settle(game)

        assert len(game.state.players[0].hand) == hand - 1 + 1
        assert untapped_islands(game) == 9

    def test_x_of_zero_pays_and_draws_nothing(self, builder):
        game = position(builder, spare_lands=10)
        hand = len(game.state.players[0].hand)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        choose_x(game, 0)
        settle(game)

        assert len(game.state.players[0].hand) == hand - 1
        assert untapped_islands(game) == 10

    def test_declining_asks_no_x_and_costs_nothing(self, builder):
        game = position(builder, spare_lands=10)
        hand = len(game.state.players[0].hand)
        gain_until_asked(game, DecisionKind.MAY)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.NO))

        assert game.pending() is None or game.pending().kind is not DecisionKind.CHOOSE_X
        settle(game)
        assert len(game.state.players[0].hand) == hand - 1
        assert untapped_islands(game) == 10


def compile_with(effect: dict) -> None:
    compile_card(
        CardModel.model_validate(
            {
                "id": "t_bad_well",
                "name": "Bad Well",
                "oracle_text": "Whenever you gain life, you may pay {X}. If you do, draw X cards.",
                "mana_cost": "{4}",
                "types": ["Artifact"],
                "abilities": [
                    {
                        "kind": "triggered",
                        "text": "Whenever you gain life, you may pay {X}. If you do, draw X cards.",
                        "trigger": {"event": "you_gain_life", "controller": "you"},
                        "effects": [effect],
                    }
                ],
            }
        )
    )


DRAW_X = [{"op": "draw", "amount": {"binding": "paid_x"}}]
GOOD_X = {"max": {"binding": "amount"}, "as": "paid_x"}


class TestTheLoaderRefuses:
    def test_the_good_one_loads(self):
        compile_with({"op": "may", "pay": {"mana": "{X}"}, "x": GOOD_X, "effects": DRAW_X})

    def test_an_x_payment_with_nothing_announcing_it(self):
        """It would charge {0} and draw nothing, on every trigger, silently."""
        with pytest.raises(DslError, match="needs 'x'"):
            compile_with({"op": "may", "pay": {"mana": "{X}"}, "effects": DRAW_X})

    def test_an_announcement_with_no_x_to_pay(self):
        with pytest.raises(DslError, match="has none"):
            compile_with({"op": "may", "pay": {"mana": "{2}"}, "x": GOOD_X, "effects": DRAW_X})

    def test_no_ceiling_is_allowed_now(self):
        """A printed ceiling is a rule the *card* makes, and not every card makes
        one.

        This used to be refused, on the grounds that "pay any amount" was join
        forces. It is not: `op_join_forces` walks every player in turn order
        asking `{1}` at a time and binds the sum, where an unbounded X here is
        announced once by one player and no opponent may add to it. Decree of
        Justice prints exactly that -- "you may pay {X}. If you do, create X 1/1
        white Soldier creature tokens" -- with no maximum anywhere on it.

        Refusing it forced an invented number, and the invented number was not
        cosmetic: `_announce_x` passes `x.max` to `max_affordable_x` as the probe
        `cap`, so a made-up 20 silently *becomes* the card's ceiling. With `max`
        absent the only bound is 118.3, what the player can actually pay, which
        is what the printed card says.
        """
        compile_with(
            {"op": "may", "pay": {"mana": "{X}"}, "x": {"as": "paid_x"}, "effects": DRAW_X}
        )

    def test_no_binding(self):
        with pytest.raises(DslError, match="as"):
            compile_with(
                {"op": "may", "pay": {"mana": "{X}"}, "x": {"max": 3}, "effects": DRAW_X}
            )

    def test_an_unknown_key(self):
        with pytest.raises(DslError, match="unsupported"):
            compile_with(
                {"op": "may", "pay": {"mana": "{X}"}, "x": {**GOOD_X, "min": 1}, "effects": DRAW_X}
            )

    def test_with_repeat(self):
        with pytest.raises(DslError, match="repeat"):
            compile_with(
                {
                    "op": "may",
                    "pay": {"mana": "{X}"},
                    "x": GOOD_X,
                    "repeat": True,
                    "effects": DRAW_X,
                }
            )

    def test_with_times(self):
        with pytest.raises(DslError, match="times"):
            compile_with(
                {"op": "may", "pay": {"mana": "{X}", "times": 2}, "x": GOOD_X, "effects": DRAW_X}
            )

    def test_on_a_may_with_no_payment(self):
        with pytest.raises(DslError, match="'x'"):
            compile_with({"op": "may", "x": GOOD_X, "effects": DRAW_X})

    def test_on_another_op(self):
        with pytest.raises(DslError, match="'x'"):
            compile_with({"op": "draw", "x": GOOD_X, "amount": 1})


UNBOUNDED = "t_well_unbounded"  # the same trigger with no printed ceiling


def unbounded_position(builder, *, spare_lands: int):
    """`t_well_unbounded` in the Well's place: "you may pay {X}", no maximum."""
    game = (
        builder(players=2)
        .battlefield(0, [UNBOUNDED, "plains", *["island"] * spare_lands])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, [GAIN])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


class TestAnUnboundedX:
    """A card that prints no ceiling -- Decree of Justice's "you may pay {X}".

    The printed maximum is a rule the *card* makes, and not every card makes
    one. Requiring it forced an invented number, and the number was load-bearing
    rather than cosmetic: `_announce_x` hands `x.max` to `max_affordable_x` as
    the probe `cap`, so a made-up 20 silently becomes the card's real ceiling.
    With `max` absent the only bound left is the one 118.3 makes.

    This is not join forces, which `op_join_forces` implements by walking every
    player in turn order asking `{1}` at a time and binding the sum. Here one
    player announces once and no opponent may add to it — which is why the
    decision below belongs to seat 0 alone.
    """

    def test_x_runs_up_to_what_the_player_can_pay(self, builder):
        """Three life gained but *five* Islands open: X runs 0..5, where the
        printed-ceiling Well would have stopped at 3."""
        game = unbounded_position(builder, spare_lands=5)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_X
        assert decision.player == 0
        assert [o.value for o in decision.options] == [0, 1, 2, 3, 4, 5]

    def test_the_printed_ceiling_version_still_stops_at_three(self, builder):
        """The contrast, on the same board. `max` is honoured where it exists,
        so relaxing the requirement did not relax the rule."""
        game = position(builder, spare_lands=5)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)

        assert [o.value for o in game.pending().options] == [0, 1, 2, 3]

    def test_the_paid_x_is_still_bound_for_the_if_you_do(self, builder):
        """The `as` half is still required, and still read: four paid, four
        drawn."""
        game = unbounded_position(builder, spare_lands=5)
        hand = len(game.state.players[0].hand)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        choose_x(game, 4)
        settle(game)

        # -1 for the gain spell that left the hand, +4 drawn.
        assert len(game.state.players[0].hand) == hand - 1 + 4

    def test_nothing_open_still_asks_nothing(self, builder):
        """The boundary: with no mana the only answer is 0, so `ask_x` short
        circuits exactly as it does with a printed ceiling of 0."""
        game = unbounded_position(builder, spare_lands=0)
        hand = len(game.state.players[0].hand)
        gain_until_asked(game, DecisionKind.MAY)
        answer_yes(game)
        settle(game)

        assert len(game.state.players[0].hand) == hand - 1
