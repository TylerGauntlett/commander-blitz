"""Cloak and Dagger, Entwined — "a nonland card from their **hand or** the
chosen creature".

    You may exile a nonland card from their hand or the chosen creature until
    Cloak and Dagger leave the battlefield.

One choice, offered across two zones at once. Every selector in the language
gathers from a single zone and then filters, so the pool this sentence asks for
could not be assembled: `zone` takes one name.

**`any_of` is the near miss and is a filter.** It narrows the pool the outer
selector already gathered — which is why `validate_selector` refuses a `zone`
inside one of its branches, "put 'zone' on the outer selector; a branch filters
the pool it already chose". A card choosing from a hand *or* the battlefield has
no one zone to gather from, so there is nothing for `any_of` to narrow.

`union` assembles instead: each branch is resolved in its own right, so each may
name its own zone, and one `count`/`chooser` then asks across the lot. Written
order, and duplicates dropped — a branch overlapping another is one card offered
once, not twice.

**Only the pool-shaping keys may sit beside it.** A characteristic clause
written outside would have to mean one thing for a card in a hand and another
for a permanent on the battlefield, and `matches` reads derived characteristics
for the one and printed ones for the other. Whatever it was meant to narrow
belongs in a branch.

`t_hand_grab` is the counterfactual: the same line narrowed to the one zone a
selector could name before.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.effects.selectors import validate_selector
from automtg.engine.errors import DslError

UNION = "t_union_grab"
HAND = "t_hand_grab"
OVERLAP = "t_overlap_grab"
BEAR = "t_bear"
BOLT = "t_bolt"


def board(builder):
    """A creature on the battlefield, a spell and a land in hand."""
    return (
        builder(players=2)
        .battlefield(0, [BEAR])
        .battlefield(0, ["swamp"] * 2)
        .hand(0, [BOLT, "forest"])
        .library(0, ["forest"] * 10)
        .build(advance=False)
    )


def offered(game, card: str):
    """What the exile op puts on the menu, as card ids.

    Run directly rather than cast: this is about the pool the selector
    assembles, and casting would also spend the choice. Every fixture writes
    "you may", which is both the printed word and what keeps the question from
    being skipped: `pick_from_pool` hands back a pool it does not have to ask
    about, and a one-card menu would otherwise never be shown.
    """
    state = game.state
    effects = state.registry.get(card).spell_effects
    ctx = EffectContext(state=state, controller=0, source_oid=None)
    gen = execute(ctx, effects)
    decision = gen.send(None)
    gen.close()
    return sorted(
        state.card(option.ref.id).id
        for option in decision.options
        if option.ref is not None
    )


class TestOnePoolFromTwoZones:
    def test_both_zones_are_offered_at_once(self, builder):
        game = board(builder)
        assert offered(game, UNION) == [BEAR, BOLT]

    def test_the_land_in_hand_is_still_filtered_out(self, builder):
        """The branch keeps its own clauses -- "a **nonland** card"."""
        game = board(builder)
        assert "forest" not in offered(game, UNION)

    def test_the_single_zone_version_offers_only_the_hand(self, builder):
        """The counterfactual, and what a selector could say before."""
        game = board(builder)
        assert offered(game, HAND) == [BOLT]

    def test_an_overlapping_branch_offers_a_card_once(self, builder):
        """Two branches that both match the Bear are one card on the menu."""
        game = board(builder)
        assert offered(game, OVERLAP) == [BEAR]


class TestTheLoaderChecksIt:
    def test_two_branches_load(self):
        validate_selector(
            {
                "union": [
                    {"zone": "hand", "not_types": ["Land"]},
                    {"zone": "battlefield", "types": ["Creature"]},
                ],
                "count": 1,
                "optional": True,
            },
            "test",
        )

    def test_one_branch_is_refused(self):
        """A union of one is a selector wearing a hat."""
        with pytest.raises(DslError, match="at least two selectors"):
            validate_selector({"union": [{"zone": "hand"}]}, "test")

    def test_a_characteristic_clause_outside_is_refused(self):
        """It would have to mean one thing for a card in a hand and another for
        a permanent, and `matches` reads the two off different layers."""
        with pytest.raises(DslError, match="belong inside a branch"):
            validate_selector(
                {
                    "union": [{"zone": "hand"}, {"zone": "battlefield"}],
                    "types": ["Creature"],
                },
                "test",
            )

    def test_the_pool_shaping_keys_are_allowed_outside(self):
        """One `count` asking across the lot is the entire point."""
        validate_selector(
            {
                "union": [{"zone": "hand"}, {"zone": "battlefield"}],
                "count": 1,
                "chooser": "controller",
                "optional": True,
                "random": False,
            },
            "test",
        )

    def test_a_branch_is_validated_in_its_own_right(self):
        with pytest.raises(DslError, match="unknown zone"):
            validate_selector(
                {"union": [{"zone": "nowhere"}, {"zone": "battlefield"}]}, "test"
            )

    def test_a_branch_may_name_a_zone(self):
        """The clause `any_of` refuses, and the whole difference between them."""
        with pytest.raises(DslError, match="put 'zone' on the outer selector"):
            validate_selector(
                {"any_of": [{"zone": "hand"}, {"zone": "battlefield"}]}, "test"
            )
