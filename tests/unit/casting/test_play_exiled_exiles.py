"""A spell cast free from exile that is exiled again instead of graveyarded.

    Power Pack -- "At the beginning of your next upkeep, you may cast that card
    without paying its mana cost. If that spell would be put into your
    graveyard, exile it instead."

The second sentence is a replacement on the **spell** (614.1a), the one
`cast_card`'s ``exiles`` already puts on a paid cast (Helmut Zemo): it rides on
the stack item (`StackItem.exiles_instead`), so it holds however the spell
leaves the stack for a graveyard. Without it the free spell would land in the
graveyard and could be exiled and recast by the next hit -- a strictly better
card. `cast_card` is the near miss and pays the mana cost; `play_exiled` is the
free cast, and ``exiles`` is the same rider on it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.stack import resolve_top
from commanderblitz.engine.zones import move_object

SPELL = "t_draw_spell"  # Draw two cards.


def position(builder):
    """Seat 0 with ``SPELL`` in exile and no mana. Returns ``(game, oid)``."""
    game = (
        builder(players=2)
        .graveyard(0, [SPELL])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    oid = game.state.players[0].graveyard[0]
    move_object(game.state, oid, Zone.EXILE, to_player=0, cause="test")
    return game, oid


def resolve(game) -> None:
    """Resolve the top of the stack; a draw spell asks nothing."""
    for _ in resolve_top(game.state):
        raise AssertionError("this spell chooses nothing")


def play(game, oid: int, **extra) -> None:
    ctx = EffectContext(
        state=game.state, controller=0, source_oid=None, targets={}, bindings={"it": [oid]}
    )
    list(execute(ctx, [{"op": "play_exiled", "objects": {"binding": "it"}, **extra}]))


class TestTheRider:
    def test_with_exiles_it_returns_to_exile(self, builder):
        game, oid = position(builder)
        hand = len(game.state.players[0].hand)

        play(game, oid, exiles=True)
        assert game.state.stack and game.state.stack[-1].exiles_instead
        resolve(game)

        assert len(game.state.players[0].hand) == hand + 2  # it resolved
        assert game.state.objects[oid].zone is Zone.EXILE
        assert oid not in game.state.players[0].graveyard

    def test_without_it_the_spell_goes_to_the_graveyard(self, builder):
        game, oid = position(builder)

        play(game, oid)
        assert not game.state.stack[-1].exiles_instead
        resolve(game)

        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_it_is_still_free(self, builder):
        """No lands and no pool: the cast happened, so it charged nothing."""
        game, oid = position(builder)

        play(game, oid, exiles=True)

        assert game.state.objects[oid].zone is Zone.STACK


class TestTheLoader:
    def test_a_non_boolean_is_refused(self):
        model = CardModel.model_validate(
            {
                "id": "t_pee_probe",
                "name": "Exiles Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "play_exiled", "exiles": "false"}],
            }
        )
        with pytest.raises(DslError, match="exiles"):
            compile_card(model)
