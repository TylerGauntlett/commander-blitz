"""Entwine — "choose both if you pay the entwine cost".

    Tooth and Nail — "Choose one — … Entwine {5} (Choose both if you pay the
    entwine cost.)"

The price needed nothing new: entwine is an additional cost paid as the spell is
cast, which is `kicker`, and legality already offers a kickable card twice. What
was missing is that the two cast lines must lead to **different questions** —
the plain one asks which mode, the entwined one asks nothing and runs both.

`all_if` is that, and it forces rather than offers. Two near misses, both of
which load:

- a wider `count` when kicked asks "which two of these two", a question with
  exactly one answer, and puts a decision on screen that is not a decision;
- a `may` would let a player pay the entwine cost and then decline half of what
  they bought.

Rule 702.42a puts the choice at the moment of casting — "you may choose all
modes instead of just one; if you do, you pay [cost]" — and choosing the
entwine cast line *is* that choice, so by resolution there is nothing left to
ask.

The half worth pinning is where `kicked` is legible. Modes are answered as the
spell goes on the stack (601.2b), and the `kicked` flag does not reach the
object until resolution — so the cast-time path has to be told, or every
entwined spell quietly picks one mode.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.loader.effects import _validate_effect
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from tests.conftest import pass_until

FOREST = "forest"
ENTWINE = "t_entwiner"      # {1}{G}, entwine {2}


def position(builder, lands: int):
    return builder(players=2).battlefield(0, [FOREST] * lands).hand(0, [ENTWINE]).library(
        0, [FOREST] * 10
    ).build()


def cast_lines(game):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == ENTWINE
    ]


def resolve(game):
    pass_until(game, lambda g: not g.state.stack)


class TestTheTwoCastLines:
    def test_both_are_offered_with_the_mana_for_it(self, builder):
        game = position(builder, 4)
        assert len(cast_lines(game)) == 2, "plain, and entwined"

    def test_only_the_plain_line_is_offered_without(self, builder):
        game = position(builder, 2)
        lines = cast_lines(game)
        assert len(lines) == 1
        assert not lines[0].kicked


class TestTheUnentwinedSpell:
    def test_it_asks_which_mode(self, builder):
        game = position(builder, 2)
        game.apply(next(a for a in cast_lines(game) if not a.kicked))
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_MODE
        assert (decision.min_count, decision.max_count) == (1, 1)

    def test_only_the_chosen_mode_happens(self, builder):
        game = position(builder, 2)
        life = game.state.players[0].life
        hand = len(game.state.players[0].hand)
        game.apply(next(a for a in cast_lines(game) if not a.kicked))
        # Mode 0 is the draw.
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
        resolve(game)

        assert len(game.state.players[0].hand) == hand, "cast one, drew one"
        assert game.state.players[0].life == life, "the other mode did not happen"


class TestTheEntwinedSpell:
    def test_it_asks_nothing(self, builder):
        """"Which two of these two" is not a decision; it must not be offered."""
        game = position(builder, 4)
        game.apply(next(a for a in cast_lines(game) if a.kicked))
        decision = game.pending()
        assert decision is None or decision.kind is not DecisionKind.CHOOSE_MODE

    def test_both_modes_happen(self, builder):
        game = position(builder, 4)
        life = game.state.players[0].life
        hand = len(game.state.players[0].hand)
        game.apply(next(a for a in cast_lines(game) if a.kicked))
        resolve(game)

        assert len(game.state.players[0].hand) == hand, "cast one, drew one"
        assert game.state.players[0].life == life + 3, "and gained the life too"


class TestTheGuards:
    def _card(self, effect: dict, **extra) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_entwine_probe",
                "name": "Entwine Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [effect],
                **extra,
            }
        )

    def _modal(self, **extra) -> dict:
        return {
            "op": "choose_mode",
            "count": 1,
            "modes": [
                {"label": "a", "effects": [{"op": "draw", "player": "you"}]},
                {"label": "b", "effects": [{"op": "gain_life", "player": "you"}]},
            ],
            **extra,
        }

    def test_a_well_formed_entwine_loads(self):
        compile_card(self._card(self._modal(all_if={"kicked": True}), kicker="{2}"))

    def test_all_if_elsewhere_is_refused(self):
        """Ignored, the card would read "choose both" and choose one."""
        with pytest.raises(DslError, match="only means anything on choose_mode"):
            _validate_effect(
                {"op": "draw", "player": "you", "all_if": {"kicked": True}}, "test", {}
            )

    def test_a_malformed_condition_is_refused(self):
        with pytest.raises(DslError):
            _validate_effect(self._modal(all_if={"nonsense": True}), "test", {})

    def test_all_if_kicked_satisfies_the_half_a_kicker_guard(self):
        """The entwine cost is read by `all_if` and nowhere else on the card."""
        card = compile_card(self._card(self._modal(all_if={"kicked": True}), kicker="{2}"))
        assert card.kicker is not None

    def test_an_entwine_cost_nothing_reads_is_still_refused(self):
        with pytest.raises(DslError, match="no effect reads"):
            compile_card(self._card(self._modal(), kicker="{2}"))
