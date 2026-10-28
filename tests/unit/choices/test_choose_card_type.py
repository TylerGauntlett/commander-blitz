""""Choose a card type", and keeping the answer on the permanent.

    "As Serra's Emissary enters, choose a card type. You and creatures you
    control have protection from the chosen card type."  -- Serra's Emissary

`choose_type` asked about two axes: creature types, surveyed from the pool, and
the six **permanent** types of 110.4a. Neither is the question this card asks.
Rule 205.2a lists nine card types, and the three a permanent-type list leaves
out -- Instant, Sorcery and Kindred -- are legal answers; "instant" is the one
most tables name. A card offered six of the nine would be a weaker card than
the printed one, so the third axis is ``{"of": "card_type"}``.

It writes the same slot as the permanent-type axis, `chosen_card_type`, and is
read back the same way, by ``{"chosen_card_type_of": "self"}``: a permanent type
*is* a card type, so every reader of the slot reads either answer, and the
creature-type slot stays untouched.

Kindred is offered although no card in this engine carries the type: it is a
legal answer, and naming it matches what it would match here -- nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader.effects import _validate_effect
from commanderblitz.engine.effects.ops_control import (
    CARD_TYPE_CHOICES,
    PERMANENT_TYPE_CHOICES,
)
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import hand_ids, pass_until

RECALL = "t_cct_recall"  # choose a card type, return those cards
HERALD = "t_cct_herald"  # as this enters, choose a card type

BOLT = "t_cct_bolt"  # Instant
PONDER = "t_cct_ponder"  # Sorcery
BEAR = "t_cct_bear"  # Creature


def position(builder, spell: str, graveyard=()):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 6)
        .graveyard(0, list(graveyard))
        .library(0, ["forest"] * 10)
        .hand(0, [spell])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def _cast(game, card_id: str) -> None:
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)


def _offered(game) -> list[str]:
    pass_until(game, lambda g: g.pending() is not None and g.pending().kind is not DecisionKind.PRIORITY)
    return [o.label for o in game.pending().options]


def _answer(game, label: str) -> None:
    pending = game.pending()
    choice = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CHOOSE and pending.options[a.choice].label == label
    )
    game.apply(choice)
    pass_until(
        game,
        lambda g: not g.state.stack
        and not g.state.pending_triggers
        and (g.pending() is None or g.pending().kind is DecisionKind.PRIORITY),
    )


def _herald(game) -> int:
    return next(
        oid for oid in game.state.battlefield if game.state.objects[oid].def_id == HERALD
    )


class TestTheOptionsAreTheNineCardTypes:
    def test_the_list_is_205_2a(self):
        assert CARD_TYPE_CHOICES == (
            "Artifact",
            "Battle",
            "Creature",
            "Enchantment",
            "Instant",
            "Kindred",
            "Land",
            "Planeswalker",
            "Sorcery",
        )

    def test_it_is_wider_than_the_permanent_types(self):
        """Every permanent type is a card type, and the three extra are the
        nonpermanent ones -- the answers the narrower axis could not give."""
        assert set(PERMANENT_TYPE_CHOICES) < set(CARD_TYPE_CHOICES)
        assert set(CARD_TYPE_CHOICES) - set(PERMANENT_TYPE_CHOICES) == {
            "Instant",
            "Kindred",
            "Sorcery",
        }

    def test_they_are_offered(self, builder):
        game = position(builder, RECALL)
        _cast(game, RECALL)
        assert _offered(game) == list(CARD_TYPE_CHOICES)


class TestTheChoiceIsReadBack:
    def test_a_nonpermanent_type_is_an_answer(self, builder):
        game = position(builder, RECALL, [BOLT, PONDER, BEAR])
        _cast(game, RECALL)
        _offered(game)
        _answer(game, "Instant")
        hand = hand_ids(game)
        assert BOLT in hand
        assert PONDER not in hand
        assert BEAR not in hand

    def test_a_different_choice_returns_a_different_card(self, builder):
        """The control. A constant would have passed the test above."""
        game = position(builder, RECALL, [BOLT, PONDER, BEAR])
        _cast(game, RECALL)
        _offered(game)
        _answer(game, "Sorcery")
        hand = hand_ids(game)
        assert PONDER in hand
        assert BOLT not in hand

    def test_kindred_matches_nothing_here(self, builder):
        game = position(builder, RECALL, [BOLT, PONDER, BEAR])
        _cast(game, RECALL)
        _offered(game)
        _answer(game, "Kindred")
        assert not {BOLT, PONDER, BEAR} & set(hand_ids(game))


class TestTheChoiceStaysOnThePermanent:
    def test_the_enters_trigger_writes_chosen_card_type(self, builder):
        game = position(builder, HERALD)
        _cast(game, HERALD)
        assert _offered(game) == list(CARD_TYPE_CHOICES)
        _answer(game, "Instant")
        obj = game.state.objects[_herald(game)]
        assert obj.chosen_card_type == "Instant"

    def test_and_leaves_the_creature_type_slot_alone(self, builder):
        game = position(builder, HERALD)
        _cast(game, HERALD)
        _offered(game)
        _answer(game, "Sorcery")
        assert game.state.objects[_herald(game)].chosen_type is None


class TestTheLoaderNamesTheAxis:
    def test_card_type_loads(self):
        _validate_effect({"op": "choose_type", "of": "card_type"}, "test", {})

    def test_a_near_miss_axis_is_refused(self):
        """Unrefused it would fall through to the creature-type branch and
        offer Vampire on a card that prints "choose a card type"."""
        with pytest.raises(DslError, match="card_type"):
            _validate_effect({"op": "choose_type", "of": "cardtype"}, "test", {})
