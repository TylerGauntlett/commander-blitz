"""Escalate with a non-mana cost -- 702.120a, whatever the cost is.

    Collective Effort -- "Escalate--Tap an untapped creature you control. (Pay
    this cost for each mode chosen beyond the first.) Choose one or more -- ..."

702.120a names "[cost]", not a mana cost: the cost is paid once for each mode
chosen beyond the first, and each payment is a payment of its own. A tap cost
paid twice taps two creatures -- the first is tapped by the time the second is
chosen, so the creatures are distinct by construction. The near misses are
wrong in the way mana escalate's are: an `additional_cost` of
`tap_permanents` made repeatable is multikicker's shape, with nothing tying the
taps to the modes, and a plain `or_more` takes every mode for no taps at all.

What a non-mana escalate adds is a ceiling the solver cannot supply: mana
escalate's lines are bounded by what the lands can pay, but a tap line has no
mana to price, so `casting._additional_ceiling` counts the untapped creatures
and offers no more payments than there are creatures to tap.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

SPELL = "t_esc_tap_spell"   # {G}, escalate tap a creature: gain 3 / draw / lose 1


def board(builder, creatures: int, *, tapped: int = 0):
    b = (
        builder(players=2)
        .battlefield(0, ["forest"])
        .battlefield(0, ["grizzly_bears"] * creatures)
        .hand(0, [SPELL])
        .library(0, ["forest"] * 20)
    )
    game = b.build()
    bears = [o for o in game.state.battlefield_objects(0) if o.def_id == "grizzly_bears"]
    for bear in bears[:tapped]:
        bear.tapped = True
    return game


def cast_lines(game):
    return sorted(
        a.additional_times
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SPELL
    )


def cast(game, times: int, picks: list[int]) -> list[DecisionKind]:
    """Cast the line paying escalate ``times`` over, choose ``picks``, resolve.

    Returns the decision kinds met after the modes, so a test can see the
    creatures being asked for.
    """
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == SPELL
            and a.additional_times == times
        )
    )
    # Every mode on offer is no choice at all, and is not asked.
    if game.pending().kind is DecisionKind.CHOOSE_MODE:
        for want in picks:
            game.apply(
                next(
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.CHOOSE and a.choice == want
                )
            )
        done = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION), None
        )
        if done is not None:
            game.apply(done)
    seen: list[DecisionKind] = []
    for _ in range(200):
        decision = game.pending()
        if decision is None or (decision.kind is DecisionKind.PRIORITY and not game.state.stack):
            break
        seen.append(decision.kind)
        game.apply(_default_answer(game, decision))
    return seen


def tapped_bears(game) -> int:
    return sum(
        1
        for o in game.state.battlefield_objects(0)
        if o.def_id == "grizzly_bears" and o.tapped
    )


class TestTheLines:
    def test_no_creature_offers_only_the_one_mode(self, builder):
        assert cast_lines(board(builder, 0)) == [0]

    def test_one_payment_per_untapped_creature(self, builder):
        assert cast_lines(board(builder, 1)) == [0, 1]

    def test_never_more_payments_than_modes_beyond_the_first(self, builder):
        assert cast_lines(board(builder, 5)) == [0, 1, 2]

    def test_a_tapped_creature_pays_nothing(self, builder):
        assert cast_lines(board(builder, 2, tapped=1)) == [0, 1]


class TestThePayments:
    def test_one_mode_taps_nothing(self, builder):
        game = board(builder, 2)
        life = game.state.players[0].life

        cast(game, 0, [0])

        assert game.state.players[0].life == life + 3
        assert tapped_bears(game) == 0

    def test_each_mode_beyond_the_first_taps_a_distinct_creature(self, builder):
        game = board(builder, 3)
        life, hand = game.state.players[0].life, len(game.state.players[0].hand)

        seen = cast(game, 2, [0, 1, 2])

        assert seen.count(DecisionKind.CHOOSE_OBJECTS) == 2  # one creature per payment
        assert game.state.players[0].life == life + 3 - 1
        assert len(game.state.players[0].hand) == hand  # the spell left, a card came
        assert tapped_bears(game) == 2

    def test_the_paid_line_asks_for_exactly_that_many_modes(self, builder):
        game = board(builder, 2)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and a.additional_times == 1
            )
        )
        decision = game.pending()

        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert (decision.min_count, decision.max_count) == (2, 2)


class TestTheLoader:
    def _card(self, escalate) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_esc_tap_probe",
                "name": "Escalate Tap Probe",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "escalate": escalate,
                "spell_effects": [
                    {
                        "op": "choose_mode",
                        "count": 1,
                        "or_more": True,
                        "modes": [
                            {"label": "a", "effects": [{"op": "gain_life", "amount": {"const": 1}}]},
                            {"label": "b", "effects": [{"op": "draw", "amount": {"const": 1}}]},
                        ],
                    }
                ],
            }
        )

    def test_a_full_cost_loads(self):
        card = compile_card(self._card({"tap_permanents": {"types": ["Creature"]}}))
        assert card.escalate is not None and card.escalate.tap_permanents is not None
        assert card.additional_cost == card.escalate
        assert card.additional_repeatable and card.additional_optional

    def test_an_empty_cost_is_refused(self):
        with pytest.raises(DslError, match="escalate"):
            compile_card(self._card({}))

    def test_a_tap_of_the_spell_itself_is_refused(self):
        with pytest.raises(DslError, match="escalate"):
            compile_card(self._card({"tap": True}))
