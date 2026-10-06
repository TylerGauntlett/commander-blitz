""""Look at the top twenty cards of your library, put any number of land cards
from among them onto the battlefield tapped, then shuffle."

Through the Forest Gate is a gamble, and the depth is the entire reason. Written
with `search_library` — the only op that could previously put a land from a
library onto the battlefield tapped — it would find every land in a ninety-nine
card deck, which is a strictly better card than the one printed and would look
completely normal on screen. `search_library` builds its pool from the whole
library and has no depth clause, so the bound had to be the new thing.

Two consequences fall out of "look at" rather than "search", and both are
asserted here because both are silent when wrong:

- **Nothing shuffles unless the card says so.** Rule 701.19c makes a search of a
  hidden zone end in a shuffle; looking at the top N does not, and the cards you
  declined stay on top in the order they were in. A card that shuffled anyway
  would destroy information the player is entitled to keep.
- **The count is the ordinary selector `count`.** "Any number of land cards from
  among them" is `count: "any"`, the same word it is everywhere else, because
  `pick_from_pool` is shared with `choose_objects`. A second spelling that only
  this op understood would be a place for the two to drift apart.
"""

from __future__ import annotations

import contextlib

import pytest

from automtg.cards.loader.effects import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.errors import DslError

FOREST = "forest"
ISLAND = "island"
BEAR = "t_bear"


def run(game, spec, answer: list[int] | None = None):
    """Run the op to completion. Returns the decision it asked, if any."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = OPS["look_at_top"](ctx, spec)
    try:
        decision = next(gen)
    except StopIteration:
        return None
    with contextlib.suppress(StopIteration):
        gen.send(answer if answer is not None else list(range(len(decision.options))))
    return decision


def zone_of(game, oid) -> Zone:
    return game.state.objects[oid].zone


def library_ids(game, pid: int = 0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].library]


def gate(**extra):
    """Through the Forest Gate's first sentence, at whatever depth."""
    return {
        "op": "look_at_top",
        "amount": {"const": 20},
        "objects": {"types": ["Land"], "count": "any"},
        "destination": "battlefield",
        "tapped": True,
        **extra,
    }


class TestTheDepthIsTheCard:
    def test_a_land_inside_the_window_is_offered(self, builder):
        game = builder(players=2).library(0, [FOREST] + [BEAR] * 5).build()
        decision = run(game, gate(amount={"const": 3}))
        assert decision is not None
        assert len(decision.options) == 1

    def test_a_land_below_the_window_is_not(self, builder):
        """The whole point. `search_library` would find this one."""
        game = builder(players=2).library(0, [BEAR] * 5 + [FOREST]).build()
        forest = game.state.players[0].library[5]
        assert run(game, gate(amount={"const": 3})) is None, "nothing to look at"
        assert zone_of(game, forest) is Zone.LIBRARY, "it was never in reach"

    def test_the_window_counts_cards_not_matches(self, builder):
        """"The top twenty cards", then filter — not "the top twenty lands"."""
        game = builder(players=2).library(0, [BEAR, BEAR, FOREST, FOREST, FOREST]).build()
        decision = run(game, gate(amount={"const": 4}))
        assert len(decision.options) == 2, "two lands sit inside the first four cards"

    def test_a_window_larger_than_the_library_is_fine(self, builder):
        game = builder(players=2).library(0, [FOREST, BEAR]).build()
        decision = run(game, gate(amount={"const": 20}))
        assert len(decision.options) == 1


class TestWhatItTakes:
    def test_it_offers_a_free_subset(self, builder):
        game = builder(players=2).library(0, [FOREST, FOREST, FOREST]).build()
        decision = run(game, gate())
        assert (decision.min_count, decision.max_count) == (0, 3), "any number of them"

    def test_the_chosen_lands_arrive_tapped(self, builder):
        game = builder(players=2).library(0, [FOREST, FOREST]).build()
        run(game, gate())
        battlefield = [game.state.objects[o] for o in game.state.battlefield]
        assert len(battlefield) == 2
        assert all(obj.tapped for obj in battlefield), "'onto the battlefield tapped'"
        assert all(obj.controller == 0 for obj in battlefield)

    def test_taking_none_is_legal_and_moves_nothing(self, builder):
        game = builder(players=2).library(0, [FOREST, FOREST]).build()
        run(game, gate(), answer=[])
        assert len(game.state.battlefield) == 0
        assert library_ids(game) == [FOREST, FOREST]

    def test_a_fixed_count_caps_what_may_be_taken(self, builder):
        game = builder(players=2).library(0, [FOREST] * 4).build()
        decision = run(game, gate(objects={"types": ["Land"], "count": {"const": 2}}))
        assert decision.max_count == 2


class TestWhatIsLeftBehind:
    def test_the_rest_stay_on_top_in_order(self, builder):
        """"Look at" is not "reveal and reorder". Declining must cost nothing."""
        game = builder(players=2).library(0, [BEAR, FOREST, ISLAND, BEAR]).build()
        run(game, gate(amount={"const": 4}), answer=[0])  # take the Forest only
        assert library_ids(game) == [BEAR, ISLAND, BEAR]

    def test_it_does_not_shuffle_by_default(self, builder):
        """Rule 701.19c's shuffle belongs to *searching*. This is not a search."""
        game = builder(players=2).library(0, [BEAR, ISLAND, BEAR, BEAR, BEAR]).build()
        run(game, gate(amount={"const": 2}), answer=[])
        assert library_ids(game) == [BEAR, ISLAND, BEAR, BEAR, BEAR]

    def test_it_shuffles_when_the_card_says_then_shuffle(self, builder):
        """Through the Forest Gate does say it, so the option must exist."""
        game = builder(players=2, seed=7).library(0, [FOREST] + [BEAR] * 12).build()
        before = library_ids(game)
        run(game, gate(amount={"const": 1}, shuffle=True), answer=[])
        after = library_ids(game)
        assert sorted(after) == sorted(before), "no card left or arrived"
        assert after != before, "the order changed"


class TestTheLoaderGuards:
    def test_a_well_formed_effect_loads(self):
        _validate_effect(gate(shuffle=True), "test", {})

    def test_a_missing_amount_is_refused(self):
        """Defaulted to 1 it would silently become a much worse card."""
        spec = gate()
        del spec["amount"]
        with pytest.raises(DslError, match="amount"):
            _validate_effect(spec, "test", {})

    def test_an_unknown_destination_is_refused(self):
        with pytest.raises(DslError, match="destination"):
            _validate_effect(gate(destination="the_moon"), "test", {})
