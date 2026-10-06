"""Myriad Landscape: two cards constrained against each other, not against a filter.

"{2}, {T}, Sacrifice this land: Search your library for **up to two basic land
cards that share a land type**, put them onto the battlefield tapped, then
shuffle."

Every clause in `_matches_in_zone` is evaluated against one candidate at a time,
so `supertypes: ["Basic"]` can say "each of these is a basic land" and can never
say "these two match one another". `shares_a_type_with` is the near miss: it
compares a candidate against an object already in `ctx.bindings`, and nothing
binds a card the same search is still in the middle of choosing.

The two shortcuts both make a different card. Hardcoding `subtypes: ["Forest"]`
takes a choice the printed card gives the player. Splitting it into two
`search_library` ops shuffles twice, is two search events, and leaves the second
pick unconstrained by the first — which is the one thing the printed sentence
exists to say.

So the *choice* is staged rather than the filter widened: pick one from the whole
pool, then be offered only what shares a subtype with it.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from tests.conftest import _default_answer, action_for_card


def board(builder, library):
    return (
        builder(players=2)
        .battlefield(0, ["forest"])
        .hand(0, ["t_share_a_type"])
        .library(0, list(library))
        .build()
    )


def run(game, picks):
    """Cast it, then take `picks[n]` cards at the nth distinct search prompt.

    A `max_count` of 1 auto-completes the moment a card is chosen, so applying
    FINISH_DECLARATION unconditionally after picking would answer the *next*
    question with zero. Stages are told apart by the options they offer.
    """
    game.apply(action_for_card(game, ActionKind.CAST, "t_share_a_type"))
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
            choose = next(
                (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
            )
            if remaining > 0 and choose is not None:
                remaining -= 1
                game.apply(choose)
                continue
            done = next(
                (
                    a
                    for a in game.legal_actions()
                    if a.kind is ActionKind.FINISH_DECLARATION
                ),
                None,
            )
            game.apply(done or _default_answer(game, decision))
            continue
        if decision.kind is DecisionKind.PRIORITY and not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    return prompts


def lands_fetched(game):
    return sorted(
        game.state.objects[oid].def_id
        for oid in game.state.battlefield
        if game.state.objects[oid].def_id in {"island", "swamp", "mountain"}
    )


class TestTheSecondPickIsConstrained:
    def test_only_cards_sharing_a_type_are_offered_second(self, builder):
        """The claim. After an Island, a Swamp must not be on the menu."""
        game = board(builder, ["island", "island", "swamp", "swamp"])
        prompts = run(game, [1, 1])

        assert len(prompts) >= 2, "the search should ask twice"
        assert set(prompts[0]) == {"Island", "Swamp"}, "the first pick is free"
        assert set(prompts[1]) == {"Island"}, (
            "after taking an Island, only Islands share a land type with it -- "
            "a Swamp on this menu is the bug the printed sentence forbids"
        )

    def test_both_fetched_lands_share_a_type(self, builder):
        game = board(builder, ["island", "island", "swamp", "swamp"])
        run(game, [1, 1])
        assert lands_fetched(game) == ["island", "island"]

    def test_a_lone_match_asks_only_once(self, builder):
        """One Island in the deck: there is no legal second pick to offer."""
        game = board(builder, ["island", "swamp", "swamp"])
        prompts = run(game, [1, 1])
        assert lands_fetched(game) == ["island"]
        assert len(prompts) == 1, "no second question when nothing can answer it"


class TestUpToTwoMeansZero:
    def test_declining_the_first_pick_takes_nothing(self, builder):
        game = board(builder, ["island", "island"])
        run(game, [0])
        assert lands_fetched(game) == []

    def test_taking_only_one_is_allowed(self, builder):
        game = board(builder, ["island", "island", "swamp"])
        run(game, [1, 0])
        assert lands_fetched(game) == ["island"]


class TestTheLoaderRefusesNonsense:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "t_bad_share",
                "name": "Bad Share",
                "oracle_text": "Bad.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "colors": ["G"],
                "color_identity": ["G"],
                "spell_effects": [effect],
            }
        )

    def test_share_subtype_on_another_op_is_a_load_error(self):
        with pytest.raises(DslError, match="share_subtype"):
            compile_card(
                self._card({"op": "draw", "amount": {"const": 1}, "share_subtype": True})
            )

    def test_share_subtype_needs_more_than_one_card(self):
        """One card shares a type with itself; the clause would be decoration."""
        with pytest.raises(DslError, match="count"):
            compile_card(
                self._card(
                    {
                        "op": "search_library",
                        "count": 1,
                        "share_subtype": True,
                        "selector": {"types": ["Land"]},
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
                        "share_subtype": "yes",
                        "selector": {"types": ["Land"]},
                    }
                )
            )
