""""You **may** reveal a Human or artifact card from among them and put it into
your hand."

Boromir, Gondor's Hope looks at the top six cards of your library, offers you at
most one of them, and puts the rest on the bottom in a random order. The middle
sentence is a declinable bounded pick -- "exactly one of these, or none" -- and
the selector language had no spelling for it. `count` had three (rule 601.2b is
not the issue; the issue is which of them says "up to one"):

- a **value** makes the number both the minimum and the maximum, so `count: 1`
  deletes the printed "You may". Worse, `pick_from_pool` short-circuits on
  `count >= len(pool)` and returns the pool without asking at all, so a top six
  holding exactly one Human put it in hand with no decision offered;
- **`"any"`** is min 0 / max *pool*, which is "any number of them" -- it would
  put every Human and artifact among the six into hand, a strictly better card;
- **`"all"`** is mandatory by definition.

Wrapping the whole `look_at_top` in `may` is not the same card in either branch.
`op_may` gates the entire effect list, so declining skips the mandatory look and
the mandatory `rest_to_bottom` -- and `_bottom_in_random_order` is a real,
distinct game action, not `shuffle_library` -- and it asks the yes/no *before*
anything has been seen, turning the one informed decision on the card into a
blind one.

So `optional: true` alongside an integer `count`, named after `TargetModel.
optional`, which is this exact shape ("exactly N, or none") on the declared-
target side. Nothing under the decision layer was missing: `ask_objects` has
always taken distinct `min_count`/`max_count` bounds. Only the floor had to be
allowed to move while the ceiling stayed at the printed number, which is the
whole difference between this and `"any"`.

The last class covers a bug this card is the first to reach: an `any_of` branch
was matched against the *caller's* default zone rather than the zone the outer
selector chose, so "a Human **or** artifact card" from a library look matched
nothing and the op silently never asked. Every shipped `any_of` is on the
battlefield, where the default happened to be right.
"""

from __future__ import annotations

import contextlib

import pytest

from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import choose_objects, validate_selector
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import library_ids

BEAR = "t_bear"
DORK = "t_dork"
FOREST = "forest"
ISLAND = "island"


def ask(game, **extra):
    """Drive ``choose_objects`` to its question. ``(generator, decision|None)``.

    ``None`` means it resolved without asking, which is the claim in several of
    these tests -- the difference between a card that offers a choice and one
    that takes the card.
    """
    ctx = EffectContext(state=game.state, controller=0)
    selector = {"controller": "you", "types": ["Creature"], **extra}
    gen = choose_objects(ctx, selector, "Choose", "choose")
    try:
        return gen, next(gen)
    except StopIteration as stop:
        return list(stop.value), None


def answer(gen, indices: list[int]) -> list[int]:
    """Send an answer and return what the selector resolved to."""
    try:
        gen.send(indices)
    except StopIteration as stop:
        return list(stop.value)
    raise AssertionError("the selector asked a second question")


def boromir(game, **extra):
    """Boromir's trigger, run to its question. Returns the decision, or None."""
    ctx = EffectContext(state=game.state, controller=0)
    spec = {
        "op": "look_at_top",
        "amount": {"const": 6},
        "destination": "hand",
        "rest_to_bottom": True,
        "objects": {"count": 1, "optional": True, **extra},
    }
    gen = OPS["look_at_top"](ctx, spec)
    try:
        decision = next(gen)
    except StopIteration:
        return None, None
    return gen, decision


def finish(gen, indices: list[int]) -> None:
    with contextlib.suppress(StopIteration):
        gen.send(indices)


class TestTheRangeItAsksFor:
    def test_the_floor_is_zero_and_the_ceiling_is_the_printed_number(self, builder):
        """The whole capability in one assertion: declinable, and still bounded."""
        game = builder(players=2).battlefield(0, [BEAR, DORK]).build()
        _, decision = ask(game, count={"const": 1}, optional=True)
        assert decision is not None, "'you may' is always a genuine question"
        assert decision.min_count == 0, "you may reveal nothing"
        assert decision.max_count == 1, "…but never two"
        assert len(decision.options) == 2, "both are offered; only one may be taken"

    def test_a_pool_of_one_still_asks(self, builder):
        """The boundary the old shortcut got wrong.

        `count >= len(pool)` returned the pool without asking, which is right for
        a mandatory pick and is the deletion of "You may" here.
        """
        game = builder(players=2).battlefield(0, [BEAR]).build()
        _, decision = ask(game, count={"const": 1}, optional=True)
        assert decision is not None
        assert (decision.min_count, decision.max_count) == (0, 1)

    def test_an_empty_pool_asks_nothing(self, builder):
        """No question, no crash: none of nothing is nothing."""
        game = builder(players=2).battlefield(0, []).build()
        resolved, decision = ask(game, count={"const": 1}, optional=True)
        assert decision is None
        assert resolved == []

    def test_a_larger_count_keeps_its_ceiling(self, builder):
        """"Exile up to **two** cards from among them" -- N is not always 1."""
        game = builder(players=2).battlefield(0, [BEAR, DORK, BEAR]).build()
        _, decision = ask(game, count={"const": 2}, optional=True)
        assert (decision.min_count, decision.max_count) == (0, 2)

    def test_the_chooser_is_the_controller_by_default(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, DORK]).build()
        _, decision = ask(game, count={"const": 1}, optional=True)
        assert decision.player == 0


class TestWhatComesBack:
    def test_taking_one_returns_exactly_that_one(self, builder):
        game = builder(players=2).battlefield(0, [BEAR, DORK]).build()
        gen, decision = ask(game, count={"const": 1}, optional=True)
        picked = answer(gen, [1])
        assert picked == [decision.options[1].value]

    def test_declining_returns_nothing(self, builder):
        """The branch no existing spelling could produce."""
        game = builder(players=2).battlefield(0, [BEAR, DORK]).build()
        gen, _ = ask(game, count={"const": 1}, optional=True)
        assert answer(gen, []) == []


class TestItIsNotTheOtherSpellings:
    def test_a_bare_count_forces_the_pick(self, builder):
        """Without `optional` the number is both bounds -- "You may" is gone."""
        game = builder(players=2).battlefield(0, [BEAR, DORK]).build()
        _, decision = ask(game, count={"const": 1})
        assert (decision.min_count, decision.max_count) == (1, 1)

    def test_a_bare_count_equal_to_the_pool_never_even_asks(self, builder):
        """The sharper half: the card is taken with no decision offered."""
        game = builder(players=2).battlefield(0, [BEAR]).build()
        resolved, decision = ask(game, count={"const": 1})
        assert decision is None
        assert len(resolved) == 1, "taken without asking"

    def test_any_would_take_every_one_of_them(self, builder):
        """"Any number of them" is a different and strictly better card."""
        game = builder(players=2).battlefield(0, [BEAR, DORK, BEAR]).build()
        _, decision = ask(game, count="any")
        assert decision.max_count == 3, "…which is exactly what 'optional' must not be"


class TestBoromirsTrigger:
    """The witness card: an optional pick from a pool `look_at_top` bounds."""

    def test_it_offers_one_of_the_matches_and_forces_none(self, builder):
        game = builder(players=2).library(0, [BEAR, FOREST, DORK, ISLAND]).build()
        _, decision = boromir(game, types=["Creature"])
        assert (decision.min_count, decision.max_count) == (0, 1)
        assert len(decision.options) == 2, "both creatures are offered"

    def test_the_chosen_card_goes_to_hand(self, builder):
        game = builder(players=2).library(0, [BEAR, FOREST, DORK]).build()
        gen, _ = boromir(game, types=["Creature"])
        finish(gen, [0])
        assert len(game.state.players[0].hand) == 1

    def test_declining_still_bottoms_the_rest(self, builder):
        """The reason this is not `may` around the whole op.

        Declining the reveal must not skip the look or the bottoming -- both are
        printed as mandatory, and `_bottom_in_random_order` is a real game action
        that reorders only the six looked at.
        """
        game = builder(players=2, seed=3).library(0, [BEAR, FOREST, DORK] + [ISLAND] * 6).build()
        before = library_ids(game)
        gen, _ = boromir(game, types=["Creature"])
        finish(gen, [])
        after = library_ids(game)
        assert game.state.players[0].hand == [], "nothing was revealed"
        assert sorted(after) == sorted(before), "and nothing was lost"
        assert after[:3] != before[:3], "but the six looked at went to the bottom"

    def test_the_decision_comes_after_the_look(self, builder):
        """"…from among **them**": the pick is over what was seen.

        A `may` wrapper asks before the look, so the player answers blind. Here
        the options *are* the cards, which can only be true afterwards.
        """
        game = builder(players=2).library(0, [BEAR, FOREST]).build()
        top = game.state.players[0].library[0]
        _, decision = boromir(game, types=["Creature"])
        assert decision.options[0].value == top

    def test_a_card_below_the_window_is_not_offered(self, builder):
        game = builder(players=2).library(0, [FOREST] * 6 + [BEAR]).build()
        bear = game.state.players[0].library[6]
        _, decision = boromir(game, types=["Creature"])
        assert decision is None, "nothing among the top six matched"
        assert game.state.objects[bear].zone is Zone.LIBRARY


class TestAnyOfInsideTheLook:
    """"A Human **or** artifact card" -- a union, read in the library."""

    def test_a_union_matches_in_a_library(self, builder):
        game = builder(players=2).library(0, [BEAR, FOREST, ISLAND]).build()
        _, decision = boromir(
            game, any_of=[{"types": ["Creature"]}, {"subtypes": ["Forest"]}]
        )
        assert decision is not None, "the branch must inherit the outer zone"
        assert len(decision.options) == 2, "one by type, one by subtype"

    def test_a_union_still_narrows(self, builder):
        """The union is an or, not a wildcard: what matches neither is out."""
        game = builder(players=2).library(0, [BEAR, ISLAND]).build()
        _, decision = boromir(game, any_of=[{"types": ["Creature"]}, {"subtypes": ["Forest"]}])
        assert len(decision.options) == 1

    def test_a_union_on_the_battlefield_is_unchanged(self, builder):
        """The zone every shipped `any_of` uses. Inheriting must not move it."""
        game = builder(players=2).battlefield(0, [BEAR, FOREST]).build()
        ctx = EffectContext(state=game.state, controller=0)
        gen = choose_objects(
            ctx,
            {"controller": "you", "count": "all", "any_of": [{"types": ["Creature"]}]},
            "Choose",
            "choose",
        )
        try:
            next(gen)
        except StopIteration as stop:
            assert len(stop.value) == 1
        else:  # pragma: no cover - `count: "all"` never asks
            raise AssertionError("'all' asked a question")


class TestTheLoaderGuards:
    def test_an_optional_integer_count_is_accepted(self):
        validate_selector({"controller": "you", "count": 1, "optional": True}, "test")

    def test_an_optional_value_expression_is_accepted(self):
        validate_selector({"controller": "you", "count": {"const": 2}, "optional": True}, "test")

    def test_optional_without_a_count_is_refused(self):
        """`count` defaults to `"all"`, so this would be an inert key on a card
        whose whole point is that the pick is declinable."""
        with pytest.raises(DslError, match="numeric count"):
            validate_selector({"controller": "you", "optional": True}, "test")

    @pytest.mark.parametrize("count", ["all", "any"], ids=["all", "any"])
    def test_optional_on_a_string_count_is_refused(self, count):
        """"All, or none" is not a printed sentence, and `"any"` already reaches
        zero -- so on either the key would be silently ignored."""
        with pytest.raises(DslError, match="numeric count"):
            validate_selector({"controller": "you", "count": count, "optional": True}, "test")

    @pytest.mark.parametrize(
        "extra", [{"random": True}, {"chooser": "none"}], ids=["random", "no-chooser"]
    )
    def test_optional_without_somebody_to_decline_is_refused(self, extra):
        """Both resolve the pool without asking, which deletes the "you may"."""
        with pytest.raises(DslError):
            validate_selector(
                {"controller": "you", "count": 1, "optional": True, **extra}, "test"
            )

    def test_a_selector_without_optional_is_unaffected(self):
        validate_selector({"controller": "you", "count": 1, "random": True}, "test")
