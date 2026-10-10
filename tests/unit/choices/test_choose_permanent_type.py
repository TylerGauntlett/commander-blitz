""""Choose a permanent type", and reading it back.

    "Choose a permanent type. Return all cards of the chosen type from your
    graveyard to your hand."                        -- Creeping Renaissance

`choose_type` already asked "pick one of these labels" and recorded the answer;
what it could only ask about was **creature** types, because its options come
from `CardRegistry.creature_types()` and its answer lands in
`GameObject.chosen_type`, whose one reader substitutes into a filter's
`subtypes`. So a card naming a *card* type had no way to say either half.

It is a parameter rather than a second op — `{"of": "permanent_type"}` — because
the decision, the prompt, the storage and the read-back all have the same shape
on both axes, and two ops would be two copies of them.

But it writes a **separate slot**. `chosen_type` holds a creature type and
`chosen_card_type` a card type; one field would make "of the chosen type"
ambiguous at every reader, and the reader that guessed wrong would match nothing
— silently, which is the failure this engine is built to refuse. The two are
asserted independent below.

The options are a fixed list of the six types rule 110.4a calls permanent types,
for `COLOR_CHOICES`' reason: every one is always a legal answer, so there is
nothing for the board to narrow, and a fixed order keeps a replay picking the
same type from the same index. Battle and Planeswalker are listed although
neither is modelled — they are legal answers at a real table, and a list that
quietly held four would make a card that offers the wrong choices.

A source that has chosen nothing yet matches **nothing**, the same answer
`resolve_chosen_subtypes` gives: "all cards of the chosen type" before a type is
chosen returns nothing, not the whole graveyard.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.ops_control import PERMANENT_TYPE_CHOICES
from commanderblitz.engine.effects.selectors import validate_selector
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step
from commanderblitz.engine.errors import DslError
from tests.conftest import hand_ids, pass_until

RENAISSANCE = "t_cpt_renaissance"  # choose a permanent type, return those cards
CREATURE_CHOOSER = "t_cpt_creature_chooser"  # the other axis

BEAR = "t_cpt_bear"  # Creature
RELIC = "t_cpt_relic"  # Artifact
CHARM = "t_cpt_charm"  # Enchantment

CHOSEN = {"chosen_card_type_of": "self"}

#: What the resolver substitutes when nothing has been chosen: a name no
#: card has, so the filter matches nothing rather than everything. Built
#: here rather than spelled out, so the test cannot drift from the code.
NO_MATCH = "\0" + "none"


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


def cast_choosing(game, card_id: str, label: str) -> None:
    """Cast ``card_id`` and answer its type choice with ``label``."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    pending = game.pending()
    assert pending is not None, "the spell asked nothing"
    options = [o.label for o in pending.options]
    assert label in options, f"{label!r} not offered; got {options}"
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


class TestTheOptionsAreTheSixPermanentTypes:
    def test_the_list_is_110_4a(self):
        assert PERMANENT_TYPE_CHOICES == (
            "Artifact",
            "Battle",
            "Creature",
            "Enchantment",
            "Land",
            "Planeswalker",
        )

    def test_they_are_offered(self, builder):
        game = position(builder, RENAISSANCE, [BEAR])
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == RENAISSANCE
        )
        game.apply(action)
        pending = game.pending()
        assert [o.label for o in pending.options] == list(PERMANENT_TYPE_CHOICES)


class TestTheChoiceIsReadBack:
    def test_it_returns_the_chosen_type(self, builder):
        game = position(builder, RENAISSANCE, [BEAR, RELIC, CHARM])
        cast_choosing(game, RENAISSANCE, "Artifact")
        assert RELIC in hand_ids(game)

    def test_and_leaves_the_others_in_the_graveyard(self, builder):
        """The whole point of reading the choice: one type, not all of them."""
        game = position(builder, RENAISSANCE, [BEAR, RELIC, CHARM])
        cast_choosing(game, RENAISSANCE, "Artifact")
        hand = hand_ids(game)
        assert BEAR not in hand
        assert CHARM not in hand

    def test_a_different_choice_returns_a_different_card(self, builder):
        """The control. A constant would have passed the test above."""
        game = position(builder, RENAISSANCE, [BEAR, RELIC, CHARM])
        cast_choosing(game, RENAISSANCE, "Enchantment")
        hand = hand_ids(game)
        assert CHARM in hand
        assert RELIC not in hand

    def test_it_returns_every_card_of_that_type(self, builder):
        game = position(builder, RENAISSANCE, [BEAR, BEAR, RELIC])
        cast_choosing(game, RENAISSANCE, "Creature")
        assert hand_ids(game).count(BEAR) == 2

    def test_nothing_of_that_type_returns_nothing(self, builder):
        game = position(builder, RENAISSANCE, [BEAR])
        cast_choosing(game, RENAISSANCE, "Land")
        assert BEAR not in hand_ids(game)


class TestTheTwoAxesAreSeparate:
    def test_the_card_type_reader_ignores_a_creature_type(self):
        """One field for both would make "the chosen type" ambiguous, and the
        reader that guessed wrong would match nothing -- silently.

        Asserted at the resolver rather than on a resolved spell: the slots are
        cleared by `reset_permanent_state` as the sorcery reaches the graveyard,
        which is right and also means there is nothing left to read afterwards.
        """
        from commanderblitz.engine.effects.selectors import _resolve_chosen_card_type

        class Source:
            chosen_type = "Vampire"  # the *creature* type axis
            chosen_card_type = None

        resolved = _resolve_chosen_card_type({"types": [CHOSEN]}, Source())
        assert resolved["types"] == [NO_MATCH], (
            "a creature type must not answer a card-type question"
        )

    def test_the_card_type_reader_uses_its_own_slot(self):
        from commanderblitz.engine.effects.selectors import _resolve_chosen_card_type

        class Source:
            chosen_type = "Vampire"
            chosen_card_type = "Artifact"

        assert _resolve_chosen_card_type({"types": [CHOSEN]}, Source())["types"] == [
            "Artifact"
        ]

    def test_a_creature_type_choice_leaves_chosen_card_type_alone(self, builder):
        game = position(builder, CREATURE_CHOOSER)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == CREATURE_CHOOSER
        )
        game.apply(action)
        pending = game.pending()
        assert "Artifact" not in [o.label for o in pending.options], (
            "the creature-type axis must not offer card types"
        )


class TestTheLoaderPlacesTheLeaf:
    def test_the_chosen_card_type_loads_in_types(self):
        validate_selector({"zone": "graveyard", "types": [CHOSEN]}, "test")

    def test_a_near_miss_spelling_is_refused(self):
        """Unrefused it would freeze into a name no card has and match nothing
        for ever -- the quiet direction."""
        with pytest.raises(DslError, match="chosen_card_type_of"):
            validate_selector(
                {"zone": "graveyard", "types": [{"chosen_card_type_of": "other"}]}, "test"
            )

    def test_it_is_refused_outside_types(self):
        with pytest.raises(DslError, match="only appear in 'types'"):
            validate_selector(
                {"zone": "graveyard", "any_types": [CHOSEN, "Land"]}, "test"
            )
