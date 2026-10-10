"""A cost reduction that counts an *or* of characteristics.

    "This spell costs {X} less to cast, where X is the total mana value of
    **historic** permanents you control. (Artifacts, legendaries, and Sagas are
    historic.)"                              -- Excalibur, Sword of Eden

A reduction filter ANDs every key it reads, which makes historic unsayable:
`{"types": ["Artifact"], "supertypes": ["Legendary"], "subtypes": ["Saga"]}`
matches only a permanent that is all three at once, and almost nothing is -- the
card would price itself off an empty board for ever, and nothing on a table or
in a test would say so, because a reduction that counts too little just makes a
spell more expensive.

`any_types` is the closest key that already existed and is an or over **types**
alone -- `set(any_types) & card.types` -- so it reaches neither the supertype
Legendary nor the subtype Saga. Three of the words on this one card are out of
its range.

So `any_of`, spelled as the effect-side selector language already spells it
(Lost to Legend's target line is exactly this shape), so one printed word has
one spelling wherever it is written. The mechanism is recursion:
`_object_matches` was split out of `_reduction_matches` precisely so a branch
can be the same filter language asked about the same object.

The ANDed control card is the point of the file. It is the same reduction with
the same three characteristics written the only other way, and it is the board
where the two answers differ.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.cost_reduction import cost_reduction
from commanderblitz.engine.errors import DslError
from tests.conftest import two_seat_board

HISTORIC = "t_rao_historic"  # any_of: Artifact / Legendary / Saga
ANDED = "t_rao_and"  # the same three, ANDed
ARTIFACT = "t_rao_artifact"  # mana value 2
LEGEND = "t_rao_legend"  # mana value 3
SAGA = "t_rao_saga"  # mana value 4
BEAR = "t_rao_bear"  # mana value 5, none of the three
ALL = "t_rao_all"  # mana value 6, all three at once


class TestEachBranchMatchesOnItsOwn:
    def test_the_artifact(self, registry, builder):
        game = two_seat_board(builder, mine=[ARTIFACT])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 2

    def test_the_legendary_creature(self, registry, builder):
        """A supertype, which `any_types` could never have reached."""
        game = two_seat_board(builder, mine=[LEGEND])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 3

    def test_the_saga(self, registry, builder):
        """A subtype, likewise."""
        game = two_seat_board(builder, mine=[SAGA])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 4

    def test_all_three_together(self, registry, builder):
        game = two_seat_board(builder, mine=[ARTIFACT, LEGEND, SAGA])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 9


class TestWhatItDoesNotMatch:
    def test_a_permanent_that_is_none_of_them(self, registry, builder):
        game = two_seat_board(builder, mine=[BEAR])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 0

    def test_and_it_does_not_drag_in_the_rest_of_the_board(self, registry, builder):
        game = two_seat_board(builder, mine=[ARTIFACT, BEAR])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 2

    def test_the_other_keys_still_apply(self, registry, builder):
        """"historic permanents **you control**". `any_of` is one clause among
        the filter's others, not a replacement for them."""
        game = two_seat_board(builder, mine=[ARTIFACT], theirs=[SAGA, LEGEND])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 2

    def test_a_permanent_is_counted_once_however_many_branches_it_matches(
        self, registry, builder
    ):
        """`any_of` is a disjunction, not a tally: a legendary artifact Saga is
        one permanent of mana value 6, not three of them."""
        game = two_seat_board(builder, mine=[ALL])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 6


class TestTheAndedControl:
    """Why the disjunction had to exist."""

    def test_it_matches_only_a_permanent_that_is_all_three(self, registry, builder):
        game = two_seat_board(builder, mine=[ARTIFACT, LEGEND, SAGA])
        assert cost_reduction(game.state, 0, registry.get(ANDED)) == 0

    def test_where_the_disjunction_counts_all_three(self, registry, builder):
        game = two_seat_board(builder, mine=[ARTIFACT, LEGEND, SAGA])
        assert cost_reduction(game.state, 0, registry.get(HISTORIC)) == 9

    def test_it_does_match_the_one_permanent_that_is(self, registry, builder):
        """The ANDed filter is not broken, it is a different sentence."""
        game = two_seat_board(builder, mine=[ALL])
        assert cost_reduction(game.state, 0, registry.get(ANDED)) == 6


class TestTheLoaderPlacesIt:
    def _card(self, filt):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "This spell costs {X} less to cast.",
                "mana_cost": "{9}",
                "types": ["Sorcery"],
                "cost_reduction": {"total_mana_value": filt},
                "spell_effects": [{"op": "draw", "amount": {"const": 1}}],
            }
        )

    def test_a_well_formed_disjunction_loads(self):
        compile_card(
            self._card(
                {
                    "controller": "you",
                    "any_of": [{"types": ["Artifact"]}, {"supertypes": ["Legendary"]}],
                }
            )
        )

    def test_an_empty_list_is_refused(self):
        """A disjunction over nothing matches nothing, and it would load."""
        with pytest.raises(DslError, match="non-empty list"):
            compile_card(self._card({"controller": "you", "any_of": []}))

    def test_a_branch_that_is_not_a_filter_is_refused(self):
        with pytest.raises(DslError, match="must be a filter object"):
            compile_card(self._card({"controller": "you", "any_of": ["Artifact"]}))

    def test_a_branch_key_is_held_to_the_same_language(self):
        """A branch is the same filter asked about the same object, so it may
        only read what the outer filter may -- checked recursively, because the
        engine reads it recursively."""
        with pytest.raises(DslError, match="unsupported filter keys"):
            compile_card(
                self._card({"controller": "you", "any_of": [{"nonsense": True}]})
            )

    def test_a_branch_may_not_name_a_zone(self):
        """The zones are chosen once for the whole filter, so a branch's own
        would be read by nobody: the card would look like it counted two zones
        and count one."""
        with pytest.raises(DslError, match="may not name a 'zone'"):
            compile_card(
                self._card(
                    {"controller": "you", "any_of": [{"zone": "graveyard"}]}
                )
            )

    def test_a_nested_branch_is_checked_too(self):
        with pytest.raises(DslError, match="unsupported filter keys"):
            compile_card(
                self._card(
                    {
                        "controller": "you",
                        "any_of": [{"any_of": [{"nonsense": True}]}],
                    }
                )
            )
