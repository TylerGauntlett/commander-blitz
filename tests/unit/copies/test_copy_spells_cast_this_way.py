""""You may cast up to one target instant card and/or up to one target sorcery
card from your graveyard … If X is 10 or more, copy each of those spells
twice."                                              -- Finale of Promise

Two gaps in one sentence. `cast_from_hand` cast for free and recorded nothing,
so "those spells" named nothing; and `copy_spell` copied one spell, named by a
stack id, a target or the trigger's own spell. So `cast_from_hand` records the
cards it actually cast under ``as`` -- accumulating, because the instant and the
sorcery are two ops over two targets and one sentence about both -- and
`copy_spell` takes ``spells``, a pool, copying each of them still on the stack.

The controls: a declined offer casts nothing and so copies nothing, and the
Finale's own spell (which is on the stack too, resolving) is not "those
spells".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import _default_answer

FINALE = "t_finale"  # {U}{R}: cast t1 (instant) and t2 (sorcery) free, copy each twice
BOLT = "lightning_bolt"  # 3 damage to any target
VISIONS = "serum_visions"  # draw a card, scry 2


def position(builder, graveyard):
    return (
        builder(players=2)
        .battlefield(0, ["island", "mountain"])
        .graveyard(0, list(graveyard))
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .hand(0, [FINALE, "island"])
        .build()
    )


def resolve_finale(game, *, accept: bool = True) -> None:
    """Cast the Finale at everything it can target, and say yes or no to each
    free cast it offers; every other question gets the passive answer."""
    lines = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FINALE
    ]
    cast = max(lines, key=lambda a: len(a.targets))
    game.apply(cast)
    for _ in range(300):
        decision = game.pending()
        if decision is None:
            return
        # A resolving spell is off the stack while it asks, so an empty stack
        # alone is not "done": priority with nothing left to resolve is.
        if (
            decision.kind is DecisionKind.PRIORITY
            and not game.state.stack
            and not game.state.pending_triggers
        ):
            return
        if decision.context.get("purpose") == "cast_from_hand" and accept:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the Finale never finished resolving")


def life_lost(game) -> int:
    return sum(40 - p.life for p in game.state.players)


class TestEachOfThoseSpellsIsCopied:
    def test_an_instant_cast_this_way_is_copied_twice(self, builder):
        """One Bolt cast and two copies: nine damage in all."""
        game = position(builder, [BOLT])
        resolve_finale(game)

        assert life_lost(game) == 9

    def test_both_spells_are_copied(self, builder):
        """The binding accumulates across the two casts: three Bolts and three
        Serum Visions, each Visions a card."""
        game = position(builder, [BOLT, VISIONS])
        hand = len(game.state.players[0].hand)
        resolve_finale(game)

        assert life_lost(game) == 9
        # The Finale left the hand, and three Visions drew three.
        assert len(game.state.players[0].hand) == hand - 1 + 3

    def test_the_cast_card_is_exiled_and_the_copies_are_gone(self, builder):
        game = position(builder, [BOLT])
        bolt = game.state.players[0].graveyard[0]
        resolve_finale(game)

        assert game.state.objects[bolt].zone is Zone.EXILE
        assert not game.state.stack


class TestNothingCastIsNothingCopied:
    def test_declining_copies_nothing(self, builder):
        game = position(builder, [BOLT])
        resolve_finale(game, accept=False)

        assert life_lost(game) == 0


class TestTheLoaderPlacesIt:
    def _card(self, effect):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Copy target instant spell.",
                "types": ["Instant"],
                "targets": [{"id": "t1", "kind": "spell", "count": 1, "selector": {}}],
                "spell_effects": [effect],
            }
        )

    def test_spells_replaces_target(self):
        with pytest.raises(DslError, match="replaces 'sid' and 'target'"):
            compile_card(
                self._card({"op": "copy_spell", "target": "t1", "spells": {"binding": "cast"}})
            )
