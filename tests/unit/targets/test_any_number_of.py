""""Put **any number of** creature cards from your hand onto the battlefield."

Rule 601.2c-style free choices show up all over Magic, and the selector language
could not say one. `count` was either `"all"` -- every matching object, and no
choice about it -- or a value expression, which forces exactly that many because
`choose_objects` passed the single number to `ask_objects` as both the minimum
and the maximum. Neither is "any number": Last March of the Ents lets you put
three creatures onto the battlefield and keep the fourth in hand, and with only
the old spellings it either dumped your whole hand or demanded a fixed count
decided when the card was written rather than when it resolves.

`ask_objects` has always taken distinct `min_count`/`max_count` bounds and
`PendingDecision.min_count` has always been honoured, so nothing under the
decision layer was missing -- only the spelling that reaches it. That is why
this is a new `count` form rather than a new op.

The witness card is Last March of the Ents. What is asserted here is the shape
of the question, because that is what the card is: an open range where an empty
answer and a full answer are both legal, and neither is forced.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import choose_objects, validate_selector
from commanderblitz.engine.errors import DslError

BEAR = "t_bear"  # 2/2
DORK = "t_dork"  # 1/1
BIG = "t_big"  # 6/6


def ask(game, **extra):
    """Drive ``choose_objects`` to its question. Returns (generator, decision).

    ``decision`` is ``None`` when the selector resolved without asking, which is
    itself the claim in a couple of these tests.
    """
    ctx = EffectContext(state=game.state, controller=0)
    selector = {"controller": "you", "types": ["Creature"], **extra}
    gen = choose_objects(ctx, selector, "Choose", "choose")
    try:
        return gen, next(gen)
    except StopIteration:
        return gen, None


def answer(gen, indices: list[int]) -> list[int]:
    """Send an answer and return what the selector resolved to."""
    try:
        gen.send(indices)
    except StopIteration as stop:
        return list(stop.value)
    raise AssertionError("the selector asked a second question")


def resolved_without_asking(game, **extra) -> list[int]:
    ctx = EffectContext(state=game.state, controller=0)
    selector = {"controller": "you", "types": ["Creature"], **extra}
    gen = choose_objects(ctx, selector, "Choose", "choose")
    try:
        next(gen)
    except StopIteration as stop:
        return list(stop.value)
    raise AssertionError("the selector asked a question it should not have")


class TestTheRangeItAsksFor:
    def test_it_offers_everything_and_demands_nothing(self, builder):
        """The whole capability, in one assertion: zero is legal, all is legal."""
        game = builder(players=2).battlefield(0, [BEAR, DORK, BIG]).build()
        _, decision = ask(game, count="any")
        assert decision is not None, "'any number' is always a genuine question"
        assert decision.min_count == 0, "you may decline every one of them"
        assert decision.max_count == 3, "…or take every one of them"
        assert len(decision.options) == 3

    def test_the_chooser_is_the_controller_by_default(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, DORK]).build()
        _, decision = ask(game, count="any")
        assert decision.player == 0


class TestWhatComesBack:
    def test_a_strict_subset_is_exactly_what_was_picked(self, builder):
        """The case neither old spelling could produce: some, not all."""
        game = builder(players=2).battlefield(0, [BEAR, DORK, BIG]).build()
        gen, decision = ask(game, count="any")
        picked = answer(gen, [0, 2])
        assert picked == [decision.options[0].value, decision.options[2].value]
        assert decision.options[1].value not in picked, "the one left behind stays behind"

    def test_choosing_none_returns_nothing(self, builder):
        """`count: "all"` cannot say this and a fixed count cannot either."""
        game = builder(players=2).battlefield(0, [BEAR, DORK, BIG]).build()
        gen, _ = ask(game, count="any")
        assert answer(gen, []) == []

    def test_choosing_all_of_them_is_legal(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, DORK, BIG]).build()
        gen, _ = ask(game, count="any")
        assert len(answer(gen, [0, 1, 2])) == 3

    def test_an_empty_pool_asks_nothing(self, builder):
        """No question, no crash -- "any number" of nothing is nothing."""
        game = builder(players=2).battlefield(0, []).build()
        assert resolved_without_asking(game, count="any") == []

    def test_a_pool_of_one_still_asks(self, builder):
        """Boundary. One card is still a choice: you may leave it in hand."""
        game = builder(players=2).battlefield(0, [BEAR]).build()
        _, decision = ask(game, count="any")
        assert decision is not None
        assert (decision.min_count, decision.max_count) == (0, 1)


class TestItIsNotTheOtherTwoSpellings:
    def test_all_never_asks(self, builder):
        """`all` is mandatory, which is the whole difference."""
        game = builder(players=2).battlefield(0, [BEAR, DORK, BIG]).build()
        assert len(resolved_without_asking(game, count="all")) == 3

    def test_a_fixed_count_forces_exactly_that_many(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, DORK, BIG]).build()
        _, decision = ask(game, count={"const": 2})
        assert (decision.min_count, decision.max_count) == (2, 2), "not a free subset"

    def test_a_fixed_count_equal_to_the_pool_still_takes_everything(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, DORK]).build()
        assert len(resolved_without_asking(game, count={"const": 2})) == 2


class TestTheLoaderGuards:
    def test_any_is_accepted(self):
        validate_selector({"controller": "you", "count": "any"}, "test")

    def test_all_is_still_accepted(self):
        validate_selector({"controller": "you", "count": "all"}, "test")

    def test_a_misspelled_count_is_refused(self):
        """Without this it would reach `evaluate_value` and fail mid-game."""
        with pytest.raises(DslError, match="unknown count"):
            validate_selector({"controller": "you", "count": "anny"}, "test")

    @pytest.mark.parametrize(
        "extra",
        [{"random": True}, {"chooser": "none"}],
        ids=["random", "no-chooser"],
    )
    def test_any_without_a_chooser_is_refused(self, extra):
        """Both would silently resolve the whole pool -- that is `all` wearing
        the wrong name, and it makes a strictly different card."""
        with pytest.raises(DslError):
            validate_selector({"controller": "you", "count": "any", **extra}, "test")
