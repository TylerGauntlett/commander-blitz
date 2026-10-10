"""Which strategy pilots which deck, and that every plan names real cards."""

from __future__ import annotations

import pytest

from commanderblitz.ai.strategy import STRATEGIES, DefaultStrategy, strategy_for
from commanderblitz.cards.registry import default_registry
from tests.cards.test_deck_legality import FIXTURES, PRECONS


def test_every_precon_has_a_strategy_of_its_own():
    assert set(STRATEGIES) == PRECONS


@pytest.mark.parametrize("deck_id", sorted(PRECONS))
def test_a_precon_is_piloted_by_its_plan(deck_id):
    strategy = strategy_for(deck_id)
    assert strategy.plan.deck_id == deck_id
    assert type(strategy) is not DefaultStrategy


@pytest.mark.parametrize("deck_id", sorted(PRECONS))
def test_every_card_a_plan_names_is_in_the_deck(deck_id):
    """A typo in a plan silently turns a bonus off. This turns it into a failure."""
    deck = default_registry().decks[deck_id]
    in_deck = deck.unique_ids() | set(deck.commanders)
    plan = STRATEGIES[deck_id].plan
    named = (
        set(plan.key_cards)
        | plan.win_cons
        | plan.protect
        | plan.commanders
        | {card for combo in plan.combos for card in combo.pieces}
    )
    assert named - in_deck == set()
    assert plan.commanders == frozenset(deck.commanders)


def test_an_import_of_a_known_commander_gets_that_commander_s_plan():
    bruvac = STRATEGIES["bruvac_the_grandiloquent"]
    assert strategy_for("mox_somebody_s_list", ["bruvac_the_grandiloquent"]) is bruvac


@pytest.mark.parametrize("deck_id", ["", "mox_unknown", *sorted(FIXTURES)])
def test_an_unknown_id_gets_the_baseline(deck_id):
    """By id alone. In a game the fixture decks' commanders still find a plan:
    the retired Edgar list is piloted like the new one, which is the point of
    matching on the commander."""
    assert type(strategy_for(deck_id)) is DefaultStrategy
