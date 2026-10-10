"""Espers to Magicite — "…**except it's an artifact and it loses all other card
types**."

    Exile each opponent's graveyard. When you do, choose up to one target
    creature card exiled this way. Create a token that's a copy of that card,
    except it's an artifact and it loses all other card types.

`copy_permanent`'s `except_` already carried embalm's "…except it's a white
Zombie Angel with no mana cost", and the shape of the clause is the same one.
What it could not say was a **card type**: `colors` repaints, `add_subtypes`
adds, and neither reaches `types`.

**A replacement, not an addition**, and the printed line is what decides. "It's
an artifact **and it loses all other card types**" leaves a token that is an
Artifact and nothing else; a union would leave it a creature as well, and a
creature can attack, block and die — a strictly better card than the one
printed, and one that looks right on the board.

**Card types only.** The subtypes are the copied card's and stay, which is also
what the printing says: the token loses its card types and is not told to lose
its creature types.

Applied to the printed face before any layer, where the rest of `copy_overrides`
is applied, because the exception is part of what the object *is* rather than an
effect on it — so an animate afterwards layers on top exactly as it would on a
printed artifact.

`t_plain_token` is the counterfactual: the same copy without the clause.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError

RETYPED = "t_magicite_token"
PLAIN = "t_plain_token"
BEAR = "t_bear"  # a green Bear creature


def board(builder, card: str):
    return (
        builder(players=2)
        .hand(0, [card, "forest"])
        .battlefield(0, ["swamp"] * 4)
        .graveyard(1, [BEAR])
        .library(0, ["forest"] * 10)
        .build()
    )


def cast(game, card: str):
    state = game.state
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and state.card(a.source).id == card
    )
    game.apply(action)
    for _ in range(20):
        decision = game.pending()
        if decision is None or decision.kind is DecisionKind.PRIORITY:
            break
        actions = game.legal_actions()
        if not actions:
            break
        game.apply(actions[0])
    return game


def token(game):
    state = game.state
    oid = next(o.oid for o in state.battlefield_objects(0) if o.is_token)
    return state, oid


class TestTheCopyIsRetyped:
    def test_it_is_an_artifact(self, builder):
        state, oid = token(cast(board(builder, RETYPED), RETYPED))
        assert "Artifact" in chars(state, oid).types

    def test_it_loses_the_creature_type(self, builder):
        """"…and it **loses all other card types**" -- the half a union would
        drop, and the half that decides whether it can attack."""
        state, oid = token(cast(board(builder, RETYPED), RETYPED))
        assert "Creature" not in chars(state, oid).types

    def test_without_the_clause_it_is_still_a_creature(self, builder):
        """The counterfactual: the same copy, one key different."""
        state, oid = token(cast(board(builder, PLAIN), PLAIN))
        assert "Creature" in chars(state, oid).types
        assert "Artifact" not in chars(state, oid).types

    def test_it_keeps_the_copied_card_s_subtypes(self, builder):
        """Card types are replaced; creature types are not mentioned by the
        printing and are not touched."""
        state, oid = token(cast(board(builder, RETYPED), RETYPED))
        printed = state.registry.get(BEAR)
        assert set(printed.subtypes) <= set(chars(state, oid).subtypes)

    def test_it_is_still_a_copy_of_that_card(self, builder):
        state, oid = token(cast(board(builder, RETYPED), RETYPED))
        assert state.card_of(state.objects[oid]).id == BEAR


def _copy(**overrides):
    return CardModel.model_validate(
        {
            "id": "t_bad_copy",
            "name": "Test Bad Copy",
            "oracle_text": "Create a token that's a copy of target creature.",
            "mana_cost": "{2}{U}",
            "types": ["Sorcery"],
            "targets": [
                {
                    "id": "t1",
                    "kind": "permanent",
                    "count": 1,
                    "selector": {"types": ["Creature"]},
                }
            ],
            "spell_effects": [
                {
                    "op": "copy_permanent",
                    "objects": {"target": "t1"},
                    "except_": overrides,
                }
            ],
        }
    )


class TestTheLoaderChecksIt:
    def test_a_real_type_loads(self):
        compile_card(_copy(types=["Artifact"]), source="test")

    def test_an_unknown_type_is_refused(self):
        with pytest.raises(DslError, match="unknown card type"):
            compile_card(_copy(types=["Artefact"]), source="test")

    def test_an_empty_list_is_refused(self):
        """It replaces rather than adds, so an empty list is a permanent with
        no card type at all -- which no printing says."""
        with pytest.raises(DslError, match="empty list"):
            compile_card(_copy(types=[]), source="test")

    def test_a_misspelled_key_is_still_refused(self):
        """The reason the key list is a list: a dropped exception is a plain
        copy, and a plain copy looks identical until somebody reads it."""
        with pytest.raises(DslError, match="unsupported keys"):
            compile_card(_copy(card_types=["Artifact"]), source="test")
