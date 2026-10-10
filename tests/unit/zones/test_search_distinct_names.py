"""Tiamat: two name constraints on one search, and they are not the same constraint.

"When Tiamat enters, if you cast it, search your library for up to five Dragon
cards **not named Tiamat** that each have **different names**, reveal them, put
them into your hand, then shuffle."

The two halves fail differently and have to be kept apart.

*Not named Tiamat* is a filter on each card by itself, so it is a selector
clause -- `not_name`, the negation twin the `not_*` family was missing.
`exclude_self` is the near miss and asks a different question: it excludes *this
object*, and the card being excluded here is a second copy of Tiamat sitting in
the library, which `exclude_self` never sees.

*Each have different names* is a relation among the picks, which no selector can
state: every clause in `_matches_in_zone` is evaluated against one candidate in
isolation, so `subtypes: ["Dragon"]` says "each of these is a Dragon" and can
never say "these five differ". `shares_a_name_with` is the relation wanted --
positive, and against an object already bound, while nothing binds a card the
same search is still choosing. So the choice is staged, like `share_subtype`,
but narrowed after *every* pick rather than only after the first.

A library where every Dragon already has a unique name would pass the second
claim while proving nothing about it, so the library here holds two copies of
one Dragon and a second copy of the searcher itself. Splitting the search into
three one-card searches is the other tempting shortcut and is a different card:
three independent "up to one" counts, three shuffles, and no pick able to see
the names the earlier ones took.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card

#: Two Scarlet Wyrms, so "different names" has something to refuse; a second
#: copy of the searcher, so `not_name` has something to exclude; and a non-Dragon
#: to keep the ordinary subtype filter honest.
LIBRARY = [
    "t_wyrm_scarlet",
    "t_wyrm_scarlet",
    "t_wyrm_cobalt",
    "t_wyrm_ashen",
    "t_wyrm_ancestor",
    "t_wyrm_herder",
]


def board(builder, card="t_wyrm_ancestor", library=None):
    return (
        builder(players=2)
        .battlefield(0, ["forest"])
        .hand(0, [card])
        .library(0, list(LIBRARY if library is None else library))
        .build()
    )


def run(game, picks, card="t_wyrm_ancestor"):
    """Cast it, then take `picks[n]` cards at the nth distinct search prompt.

    Copied in shape from `test_search_shared_type.run`: a `max_count` of 1
    auto-completes the moment a card is chosen, so a FINISH_DECLARATION applied
    unconditionally after picking would answer the *next* question with zero.
    Stages are told apart by the options they offer, which is also what this
    test is reading.
    """
    game.apply(action_for_card(game, ActionKind.CAST, card))
    prompts: list[list[str]] = []
    current: tuple[str, ...] | None = None
    remaining = 0
    for _ in range(300):
        decision = game.pending()
        if decision is None:
            break
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            offered = tuple(o.label for o in decision.options)
            if offered != current:
                current = offered
                prompts.append(list(offered))
                remaining = picks[len(prompts) - 1] if len(prompts) <= len(picks) else 0
            choose = next((a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None)
            if remaining > 0 and choose is not None:
                remaining -= 1
                game.apply(choose)
                continue
            done = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION),
                None,
            )
            game.apply(done or _default_answer(game, decision))
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return prompts


def fetched(game):
    """What the search put into hand, by definition id."""
    return sorted(game.state.objects[oid].def_id for oid in game.state.players[0].hand)


class TestNotNamedIsAFilterOnEachCard:
    def test_the_searchers_own_name_is_never_offered(self, builder):
        """The claim. A second Test Wyrm Ancestor is a Dragon card in the library."""
        game = board(builder)
        prompts = run(game, [0])

        assert prompts, "the search should ask"
        assert "Test Wyrm Ancestor" not in prompts[0], (
            "'not named Test Wyrm Ancestor' excludes the other copy in the library; "
            "`exclude_self` cannot, because that copy is not this object"
        )

    def test_the_other_copy_is_a_dragon_that_would_otherwise_qualify(self, builder):
        """Without the clause it is just another Dragon -- drop it and it appears."""
        game = board(builder)
        prompts = run(game, [0])
        assert set(prompts[0]) == {"Test Scarlet Wyrm", "Test Cobalt Wyrm", "Test Ashen Wyrm"}

    def test_a_non_dragon_is_still_filtered_out(self, builder):
        """`not_name` composes with the other clauses rather than replacing them."""
        game = board(builder)
        prompts = run(game, [0])
        assert "Test Wyrm Herder" not in prompts[0]

    def test_the_excluded_name_is_never_fetched(self, builder):
        game = board(builder)
        run(game, [1, 1, 1])
        assert "t_wyrm_ancestor" not in fetched(game)

    def test_a_list_excludes_every_name_in_it(self, builder):
        """"…not named Test Scarlet Wyrm or Test Cobalt Wyrm" -- one selector, two names."""
        game = board(builder, card="t_wyrm_caller")
        prompts = run(game, [0], card="t_wyrm_caller")
        assert set(prompts[0]) == {"Test Wyrm Ancestor", "Test Ashen Wyrm"}, (
            "both listed names are excluded, and nothing else is -- the searcher's "
            "own name is not on this card's list, so its copy stays in the pool"
        )


class TestDifferentNamesIsAConstraintBetweenThePicks:
    def test_a_duplicate_of_the_first_pick_is_not_offered_second(self, builder):
        """The claim, and the reason the library holds two Scarlet Wyrms."""
        game = board(builder)
        prompts = run(game, [1, 0])

        assert len(prompts) >= 2, "the search should ask again"
        assert prompts[0][0] == "Test Scarlet Wyrm", "the first pick is the first option"
        assert "Test Scarlet Wyrm" not in prompts[1], (
            "the second Scarlet Wyrm is a legal Dragon card and an illegal second "
            "pick -- this is the sentence 'each have different names' exists to say"
        )
        assert set(prompts[1]) == {"Test Cobalt Wyrm", "Test Ashen Wyrm"}

    def test_every_pick_narrows_the_rest_not_only_the_first(self, builder):
        """Where this parts company with `share_subtype`, which stages exactly twice."""
        game = board(builder)
        prompts = run(game, [1, 1, 1])

        assert len(prompts) >= 3, "three picks, three questions"
        assert set(prompts[2]) == {"Test Ashen Wyrm"}, (
            "the third menu is narrowed by both earlier picks, not just the lead"
        )

    def test_the_fetched_cards_all_have_different_names(self, builder):
        game = board(builder)
        run(game, [1, 1, 1])
        assert fetched(game) == ["t_wyrm_ashen", "t_wyrm_cobalt", "t_wyrm_scarlet"]

    def test_the_search_stops_when_no_new_name_is_left(self, builder):
        """Three of one Dragon: one is takeable and "up to three" ends there."""
        game = board(builder, library=["t_wyrm_scarlet"] * 3)
        prompts = run(game, [1, 1, 1])
        assert fetched(game) == ["t_wyrm_scarlet"]
        assert len(prompts) == 1, "no second question when nothing can answer it"


class TestUpToThreeMeansZero:
    def test_declining_the_first_pick_takes_nothing(self, builder):
        game = board(builder)
        run(game, [0])
        assert fetched(game) == []

    def test_declining_partway_keeps_what_was_taken(self, builder):
        game = board(builder)
        run(game, [1, 0])
        assert fetched(game) == ["t_wyrm_scarlet"]

    def test_an_empty_pool_asks_nothing(self, builder):
        game = board(builder, library=["t_wyrm_herder", "t_wyrm_ancestor"])
        prompts = run(game, [1])
        assert prompts == []
        assert fetched(game) == []


class TestTheLoaderRefusesNonsense:
    def _card(self, effect, selector_extra=None):
        return CardModel.model_validate(
            {
                "id": "t_bad_distinct",
                "name": "Bad Distinct",
                "oracle_text": "Bad.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "colors": ["G"],
                "color_identity": ["G"],
                "spell_effects": [effect],
            }
        )

    def test_distinct_names_on_another_op_is_a_load_error(self):
        with pytest.raises(DslError, match="distinct_names"):
            compile_card(
                self._card({"op": "draw", "amount": {"const": 1}, "distinct_names": True})
            )

    def test_distinct_names_needs_more_than_one_card(self):
        """One card differs from nothing; the clause would be decoration."""
        with pytest.raises(DslError, match="count"):
            compile_card(
                self._card(
                    {
                        "op": "search_library",
                        "count": 1,
                        "distinct_names": True,
                        "selector": {"types": ["Creature"]},
                    }
                )
            )

    def test_a_non_boolean_is_a_load_error(self):
        with pytest.raises(DslError, match="boolean"):
            compile_card(
                self._card(
                    {
                        "op": "search_library",
                        "count": 2,
                        "distinct_names": "yes",
                        "selector": {"types": ["Creature"]},
                    }
                )
            )

    def test_both_stagings_at_once_are_refused(self):
        """One search stages one way; whichever ran would drop half the sentence."""
        with pytest.raises(DslError, match="both"):
            compile_card(
                self._card(
                    {
                        "op": "search_library",
                        "count": 2,
                        "distinct_names": True,
                        "share_subtype": True,
                        "selector": {"types": ["Creature"]},
                    }
                )
            )

    def test_not_name_must_hold_names(self):
        """A `not_name` that is not a name excludes nothing and looks like it worked."""
        with pytest.raises(DslError, match="not_name"):
            compile_card(
                self._card(
                    {
                        "op": "search_library",
                        "count": 1,
                        "selector": {"types": ["Creature"], "not_name": {"name": "Forest"}},
                    }
                )
            )
