"""Bitter Triumph — "discard a card **or** pay 3 life".

A `Cost`'s entries are **conjunctive**. Writing `discard` and `pay_life` on one
cost charges the player both, which is a strictly worse card; writing either
alone silently drops half the printed line. `additional_optional` is the nearest
existing thing and only makes one fixed price skippable — a yes/no on paying it,
not a choice between two prices. And `choose_mode` runs at resolution, so it can
neither be a cost nor decide whether the spell is castable at all.

So the branches are a list, and legality offers **one cast line per payable
branch** — exactly as emerge offers one per sacrificeable creature and kicker
offers the spell twice: the player is choosing, and the choice changes the price.
An unpayable branch is not a price on offer, so it is withheld rather than
offered and rewound.

`t_bitter_both` is the counterfactual: the same two prices on one conjunctive
cost, which is what the DSL could say before this existed, and it charges both.

One thing deliberately *not* asserted here: what happens with an empty hand. The
card being cast is still in hand when legality prices the cost, so it counts as
fodder for its own discard — a pre-existing defect
and a different capability from this one. Every test below holds a real spare
card, so none of them depends on it.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind, DecisionKind

BITTER = "t_bitter"
BOTH = "t_bitter_both"


def board(builder, card_id: str, *, life: int = 40, spare: int = 1):
    return (
        builder(players=2)
        .hand(0, [card_id, *["forest"] * spare])
        .battlefield(0, ["swamp"] * 4)
        .battlefield(1, ["t_bear"])
        .life(0, life)
        .library(0, ["forest"] * 20)
        .build()
    )


def cast_lines(game, card_id: str):
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def pay_branch(game, card_id: str, choice: int):
    """Cast on the given branch and answer a discard prompt if one comes."""
    action = next(a for a in cast_lines(game, card_id) if a.additional_choice == choice)
    game.apply(action)
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
    return game


def graveyard_ids(game, pid: int = 0):
    state = game.state
    return [state.card_of(state.objects[o]).id for o in state.players[pid].graveyard]


class TestBothPricesAreOffered:
    def test_two_lines_one_per_branch(self, builder):
        game = board(builder, BITTER)
        choices = sorted(a.additional_choice for a in cast_lines(game, BITTER))
        assert choices == [0, 1]

    def test_each_line_says_what_it_costs(self, builder):
        """Two identical rows would make the player pick blind."""
        labels = [a.label for a in cast_lines(board(builder, BITTER), BITTER)]
        assert any("Discard 1" in label for label in labels)
        assert any("Pay 3 life" in label for label in labels)


class TestAnUnpayableBranchIsWithheld:
    def test_at_two_life_only_the_discard_branch_is_offered(self, builder):
        game = board(builder, BITTER, life=2)
        choices = sorted(a.additional_choice for a in cast_lines(game, BITTER))
        assert choices == [0]

    def test_at_exactly_three_life_the_life_branch_survives(self, builder):
        """118.4: a player may pay life down to exactly 0."""
        game = board(builder, BITTER, life=3)
        choices = sorted(a.additional_choice for a in cast_lines(game, BITTER))
        assert choices == [0, 1]


class TestOnlyTheChosenBranchIsCharged:
    """The whole point: one price, not both, and not the wrong one."""

    def test_the_discard_branch_costs_no_life(self, builder):
        game = board(builder, BITTER)
        before = game.state.players[0].life
        pay_branch(game, BITTER, 0)
        assert game.state.players[0].life == before
        assert "forest" in graveyard_ids(game)

    def test_the_life_branch_costs_no_card(self, builder):
        game = board(builder, BITTER)
        before = game.state.players[0].life
        hand_before = len(game.state.players[0].hand)
        pay_branch(game, BITTER, 1)
        assert game.state.players[0].life == before - 3
        # -1 for the spell leaving hand, and nothing discarded on top of it
        assert len(game.state.players[0].hand) == hand_before - 1
        assert "forest" not in graveyard_ids(game)

    def test_the_conjunctive_counterfactual_charges_both(self, builder):
        """What one `Cost` with both entries actually does -- the wrong card."""
        game = board(builder, BOTH)
        before = game.state.players[0].life
        action = next(iter(cast_lines(game, BOTH)))
        game.apply(action)
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE)
            )
        assert game.state.players[0].life == before - 3
        assert "forest" in graveyard_ids(game)


class TestTheLoaderRefusesNonsense:
    def _card(self, **extra):
        from commanderblitz.cards.schema import CardModel

        return CardModel.model_validate(
            {
                "id": "t_bad_modal",
                "name": "Test Bad Modal",
                "oracle_text": "Destroy target creature.",
                "mana_cost": "{1}{B}",
                "types": ["Instant"],
                "spell_effects": [{"op": "draw", "player": "you"}],
                **extra,
            }
        )

    def test_one_branch_is_not_a_choice(self):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="at least two"):
            compile_card(self._card(additional_cost_options=[{"discard": 1}]), source="t")

    def test_it_does_not_combine_with_a_single_additional_cost(self):
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="not both"):
            compile_card(
                self._card(
                    additional_cost={"discard": 1},
                    additional_cost_options=[{"discard": 1}, {"pay_life": 3}],
                ),
                source="t",
            )

    def test_it_does_not_combine_with_repeatable(self):
        """One line per branch and one line per number paid disagree."""
        from commanderblitz.cards.loader import compile_card
        from commanderblitz.engine.errors import DslError

        with pytest.raises(DslError, match="additional_repeatable"):
            compile_card(
                self._card(
                    additional_cost_options=[{"discard": 1}, {"pay_life": 3}],
                    additional_repeatable=True,
                ),
                source="t",
            )
