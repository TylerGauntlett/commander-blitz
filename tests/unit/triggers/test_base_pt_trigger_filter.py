"""Bess, Soul Nourisher -- "whenever one or more other creatures you control
**with base power and toughness 1/1** enter".

Rule 613.4: power and toughness are applied in sublayers, and a creature's
*base* power and toughness is what 7a (characteristic-defining abilities and
copy values) and 7b (effects that set it) leave, before 7c's anthems, pumps and
counters. A trigger filter's ``power``/``toughness`` read the live value --
Welcoming Vampire's "power 2 or less" is asked of the creature as it stands --
and on any board with an anthem or a shrink the live and base readings name
different creatures in both directions: a 1/1 token entering under an anthem is
a 2/2 the live reading misses, and a 2/2 entering under a -1/-1 effect is a 1/1
it wrongly counts.

``base_power``/``base_toughness`` in a trigger filter are read at
`characteristics._base_pt`, the function the effect-side selector and
`_compute` both start from. On a ``batched`` trigger the filter is asked of
each entering object before the batch is spent, so "one or more" of them is
any one of them.

`t_soul_nourisher` is Bess's first line; `t_live_nourisher` is the near miss,
the same trigger with the live clauses, so each claim is measured against the
card an author would write without this key.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, only_oid, plus_one_counters, pt, settle

BESS = "t_soul_nourisher"
LIVE = "t_live_nourisher"
ANTHEM = "t_token_anthem"
BLIGHT = "t_token_blight"
ONE_ONE = "cat_1_1_w"
TWO_TWO = "cat_2_2_w"


def board(builder, nourisher: str = BESS, *mine: str, theirs=()):
    """``nourisher`` and ``mine`` for player 0, frozen in the main phase."""
    game = (
        builder(players=2)
        .battlefield(0, [nourisher, *mine])
        .battlefield(1, list(theirs))
        .build(advance=False)
    )
    return game, only_oid(game, nourisher)


def create(game, token: str, amount: int = 1, *, controller: int = 0) -> None:
    """One `create_token` op: ``amount`` tokens entering at once."""
    ctx = EffectContext(state=game.state, controller=controller, source_oid=None)
    spec = {"op": "create_token", "token": token, "amount": {"const": amount}}
    for _ in execute(ctx, [spec]):
        raise AssertionError("create_token asks nothing here")


def counters_after(game, oid: int, token: str, amount: int = 1, **kw) -> int:
    create(game, token, amount, **kw)
    game._advance()
    settle(game)
    return plus_one_counters(game, oid)


class TestTheBaseSizeIsAsked:
    def test_a_one_one_entering_triggers(self, builder):
        game, oid = board(builder)
        assert counters_after(game, oid, ONE_ONE) == 1

    def test_a_two_two_entering_does_not(self, builder):
        game, oid = board(builder)
        assert counters_after(game, oid, TWO_TWO) == 0

    def test_an_opponents_one_one_does_not(self, builder):
        """"…you control" -- the controller clause still applies beside it."""
        game, oid = board(builder)
        assert counters_after(game, oid, ONE_ONE, controller=1) == 0


class TestTheLayersAboveTheBaseAreIgnored:
    def test_a_one_one_token_under_an_anthem_still_triggers(self, builder):
        game, oid = board(builder, BESS, ANTHEM)
        create(game, ONE_ONE)
        token = oids_of(game, ONE_ONE, 0)[0]
        assert pt(game, token) == (2, 2), "the anthem has made it a 2/2"
        game._advance()
        settle(game)
        assert plus_one_counters(game, oid) == 1

    def test_the_live_reading_misses_it(self, builder):
        """The near miss: ``power``/``toughness`` see the 2/2 the anthem made."""
        game, oid = board(builder, LIVE, ANTHEM)
        assert counters_after(game, oid, ONE_ONE) == 0

    def test_a_two_two_shrunk_to_one_one_does_not_trigger(self, builder):
        game, oid = board(builder, BESS, BLIGHT)
        create(game, TWO_TWO)
        token = oids_of(game, TWO_TWO, 0)[0]
        assert pt(game, token) == (1, 1), "the blight has made it a 1/1"
        game._advance()
        settle(game)
        assert plus_one_counters(game, oid) == 0

    def test_the_live_reading_counts_it(self, builder):
        """The near miss the other way: a printed 2/2 read as a 1/1."""
        game, oid = board(builder, LIVE, BLIGHT)
        assert counters_after(game, oid, TWO_TWO) == 1


class TestOneOrMore:
    def test_three_at_once_is_one_counter(self, builder):
        game, oid = board(builder)
        assert counters_after(game, oid, ONE_ONE, 3) == 1

    def test_the_filter_is_asked_of_each_entering_object(self, builder):
        """A batch whose *first* object fails the filter still triggers on a
        later one: two 2/2s then a 1/1, entering together."""
        game, oid = board(builder)
        ctx = EffectContext(state=game.state, controller=0, source_oid=None)
        specs = [
            {"op": "create_token", "token": TWO_TWO, "amount": {"const": 2}},
            {"op": "create_token", "token": ONE_ONE, "amount": {"const": 1}},
        ]
        for _ in execute(ctx, specs):
            raise AssertionError("create_token asks nothing here")
        game._advance()
        settle(game)
        assert plus_one_counters(game, oid) == 1


def _probe(filt: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_probe",
            "name": "Probe",
            "mana_cost": "{2}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": {"event": "permanent_enters", "controller": "you", "filter": filt},
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }
    )


class TestTheLoader:
    @pytest.mark.parametrize(
        "spec", [1, {"op": "<=", "value": 1}, {"op": "==", "value": 1}, {"parity": "odd"}]
    )
    @pytest.mark.parametrize("key", ["base_power", "base_toughness"])
    def test_a_literal_comparison_loads(self, key, spec):
        compile_card(_probe({"types": ["Creature"], key: spec}))

    @pytest.mark.parametrize(
        "spec",
        [
            "1",
            True,
            {"amount": 1},
            {"op": "!=", "value": 1},
            {"op": "<=", "value": {"const": 1}},
            {"op": "<=", "value": {"power_of": {"self": True}}},
        ],
    )
    @pytest.mark.parametrize("key", ["base_power", "base_toughness"])
    def test_anything_the_matcher_would_misread_is_refused(self, key, spec):
        with pytest.raises(DslError, match=key):
            compile_card(_probe({"types": ["Creature"], key: spec}))
