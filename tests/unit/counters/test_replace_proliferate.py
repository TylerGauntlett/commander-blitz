"""Proliferating twice instead.

    Tekuthal, Inquiry Dominus — "If you would proliferate, proliferate twice
    instead."

A replacement of an **action**, not of a number. Proliferate (701.27a) has no
count to multiply, so "twice" is the whole proliferate performed again -- with
its own choice, the second seeing the counters the first added. Doubling the
counters one proliferate adds would be a different card: it would grow a kind by
two in one step and never offer the second choice, which matters the moment the
first proliferate killed something or put a counter where there was none.

Two Tekuthals are two replacements of one event, each applying once (614.5) to
the event the other produced (616.1): one proliferate becomes four.

The `replace_proliferate` static, read by the `proliferate` op through
`player_statics.proliferate_times`; the witness card is Tekuthal.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.errors import DslError
from automtg.engine.player_statics import proliferate_times
from tests.conftest import only_oid

DOUBLER = "t_proliferate_doubler"
BEAR = "t_bear"


def position(builder, mine: int = 1, theirs: int = 0):
    """Our bear with a +1/+1 counter, and ``mine``/``theirs`` doublers."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR], counters={"+1/+1": 1})
        .battlefield(0, [DOUBLER] * mine)
        .battlefield(1, [DOUBLER] * theirs)
        .build()
    )
    return game, only_oid(game, BEAR, 0)


def proliferate(game, answer=None, controller: int = 0) -> list:
    """Resolve one proliferate op; answer everything unless told otherwise."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = execute(ctx, [{"op": "proliferate"}])
    asked = []
    try:
        decision = next(gen)
        while True:
            asked.append(decision)
            picks = answer(decision) if answer else list(range(len(decision.options)))
            decision = gen.send(picks)
    except StopIteration:
        pass
    return asked


def plus_ones(game, oid: int) -> int:
    return game.state.objects[oid].counters.get("+1/+1", 0)


class TestItProliferatesTwice:
    def test_one_doubler_is_two_proliferates(self, builder):
        game, bear = position(builder)
        assert len(proliferate(game)) == 2
        assert plus_ones(game, bear) == 3

    def test_without_it_is_once(self, builder):
        game, bear = position(builder, mine=0)
        assert len(proliferate(game)) == 1
        assert plus_ones(game, bear) == 2

    def test_two_doublers_compound_to_four(self, builder):
        game, bear = position(builder, mine=2)
        assert proliferate_times(game.state, 0) == 4
        assert len(proliferate(game)) == 4
        assert plus_ones(game, bear) == 5


class TestEachIsItsOwnChoice:
    def test_the_second_can_decline_what_the_first_took(self, builder):
        game, bear = position(builder)
        answers = iter([[0], []])
        proliferate(game, lambda d: next(answers))
        assert plus_ones(game, bear) == 2

    def test_the_second_sees_what_the_first_started(self, builder):
        """The second is asked after the first resolved: what the first grew is
        offered again, and grows again."""
        game, _ = position(builder)
        game.state.players[1].poison = 1
        asked = proliferate(game)
        assert [o.ref.kind for o in asked[1].options].count("player") == 1
        assert game.state.players[1].poison == 3


class TestWhoseProliferate:
    def test_an_opponents_doubler_does_not_double_mine(self, builder):
        game, bear = position(builder, mine=0, theirs=1)
        assert len(proliferate(game)) == 1
        assert plus_ones(game, bear) == 2

    def test_it_leaves_the_battlefield_and_stops(self, builder):
        game, _ = position(builder)
        doubler = only_oid(game, DOUBLER, 0)
        game.state.battlefield.remove(doubler)
        game.state.bump_chars()
        assert proliferate_times(game.state, 0) == 1


class TestTheLoaderGuardsIt:
    def _model(self, **extra):
        ability = {
            "kind": "static",
            "text": "If you would proliferate, proliferate twice instead.",
            "effect": "replace_proliferate",
            "affects_player": "you",
            **extra,
        }
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "oracle_text": ability["text"],
                "mana_cost": "{2}{U}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def test_a_well_formed_static_loads(self):
        compile_card(self._model())

    def test_affects_player_is_required(self):
        with pytest.raises(DslError, match="needs 'affects_player'"):
            compile_card(self._model(affects_player=None))

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="replace_proliferate takes"):
            compile_card(self._model(amount=3))
