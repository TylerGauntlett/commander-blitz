"""Escalate -- 702.120a, an additional cost paid once per mode beyond the first.

    Collective Resistance -- "Escalate {G} (Pay this cost for each mode chosen
    beyond the first.) Choose one or more -- ..."

601.2b chooses the modes and 601.2f totals the cost from them, so how many modes
a cast takes is part of its price. Every near miss prices the wrong thing:
spree charges each mode, the first included; a plain `or_more` takes all three
modes for the printed cost; multikicker pays any number of times with nothing
tying the count to the modes.

So escalate desugars as multikicker does -- a repeatable optional additional
cost, one cast line per number of payments -- and two readers tie the count to
the modes: `casting._additional_ceiling` offers at most one payment per mode
beyond the first, and `Game._cast` makes the cast choose exactly one mode more
than it paid for.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

SPELL = "t_esc_spell"   # {1}{G}, escalate {G}: gain 3 / draw / lose 1


def board(builder, lands: int):
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * lands)
        .hand(0, [SPELL])
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_lines(game):
    return sorted(
        a.additional_times
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SPELL
    )


def cast(game, times: int, picks: list[int]):
    """Cast the line paying escalate ``times`` over and choose ``picks``."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == SPELL
            and a.additional_times == times
        )
    )
    decision = game.pending()
    assert decision.kind is DecisionKind.CHOOSE_MODE
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
    for _ in range(200):
        decision = game.pending()
        if decision is None or (decision.kind is DecisionKind.PRIORITY and not game.state.stack):
            break
        game.apply(_default_answer(game, decision))


def untapped(game) -> int:
    return sum(1 for o in game.state.battlefield_objects(0) if not o.tapped)


class TestTheLines:
    def test_one_line_per_affordable_count(self, builder):
        assert cast_lines(board(builder, 2)) == [0]
        assert cast_lines(board(builder, 3)) == [0, 1]

    def test_never_more_payments_than_modes_beyond_the_first(self, builder):
        """Three modes, so two payments at most however much mana there is."""
        assert cast_lines(board(builder, 8)) == [0, 1, 2]


class TestTheModesFollowThePrice:
    def test_one_mode_costs_the_printed_cost(self, builder):
        game = board(builder, 4)
        life = game.state.players[0].life

        cast(game, 0, [0])

        assert game.state.players[0].life == life + 3
        assert untapped(game) == 2

    def test_two_modes_cost_one_escalate(self, builder):
        game = board(builder, 4)
        life, hand = game.state.players[0].life, len(game.state.players[0].hand)

        cast(game, 1, [0, 1])

        assert game.state.players[0].life == life + 3
        assert len(game.state.players[0].hand) == hand  # the spell left, a card came
        assert untapped(game) == 1

    def test_the_paid_line_asks_for_exactly_that_many(self, builder):
        game = board(builder, 4)
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
    def _card(self, **extra) -> CardModel:
        spell = {
            "id": "t_esc_probe",
            "name": "Escalate Probe",
            "mana_cost": "{1}{G}",
            "types": ["Sorcery"],
            "escalate": "{G}",
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
        spell.update(extra)
        return CardModel.model_validate(spell)

    def test_it_loads(self):
        card = compile_card(self._card())
        assert card.escalate is not None
        assert card.additional_repeatable and card.additional_optional

    def test_it_needs_one_or_more_modes(self):
        with pytest.raises(DslError, match="escalate"):
            compile_card(
                self._card(spell_effects=[{"op": "draw", "amount": {"const": 1}}])
            )

    def test_it_is_the_only_additional_cost(self):
        with pytest.raises(DslError, match="escalate"):
            compile_card(self._card(additional_cost={"mana": "{1}"}))

    def test_a_free_escalate_is_refused(self):
        with pytest.raises(DslError, match="escalate"):
            compile_card(self._card(escalate="{0}"))
