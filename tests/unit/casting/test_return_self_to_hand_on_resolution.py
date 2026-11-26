""""Return <this card> to its owner's hand." -- `return_self_to_hand_on_resolution`

    Haunting Imitation -- "... **If no creature cards were revealed this way,
    return Haunting Imitation to its owner's hand.**"

608.2n puts a resolved instant or sorcery into its owner's graveyard as the
last step of its resolution. This card's own instruction, when its condition
holds, puts it into its owner's hand instead, and is carried out as part of
the same resolution (608.2c): the condition is judged where the card prints it,
after the effects before it have happened.

**The near misses.** A `return_to_hand` of the card in its own effects reaches
nothing -- the spell is already popped off the stack -- and
`_place_after_resolution` bins it a moment later. `buyback` is the same hand
gated on a paid additional cost. Hence an op that marks the resolving spell and
a branch in `stack._place_after_resolution` that reads the mark.

**Only on resolution.** A spell whose every target is gone does not resolve
(608.2b): none of its instructions happen and it goes to the graveyard.

**Flashback still exiles.** 702.34a exiles a flashback spell "instead of
putting it anywhere else any time it would leave the stack", so the return,
which only beats riders replacing the *graveyard*, does not save it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.zones import move_object
from tests.conftest import _default_answer, keywords, pt

IF_ALONE = "t_return_self_if_alone"  # sorcery: gain 2; return it if you control no creatures
KILL = "t_return_self_kill"  # instant: destroy target creature; return it
EXILES = "t_return_self_exiles"  # sorcery: gain 2; return it; prints exiles_itself
FLASHBACK = "t_return_self_flashback"  # sorcery: gain 2; return it; flashback {W}
BEAR = "grizzly_bears"


def board(builder, card_id: str = IF_ALONE, *, my_creature: bool = False, graveyard: bool = False):
    """Seat 0 holds two copies (or has one in its graveyard) and the mana for them.

    The second copy keeps seat 0 at priority with the first on the stack:
    with nothing left to do, the engine would auto-pass straight through the
    resolution and on into the next turn. Seat 1 has a Bear to target.
    """
    mine = ["plains"] * 4 + ["swamp"] * 4 + ([BEAR] if my_creature else [])
    b = (
        builder(players=2)
        .battlefield(0, mine)
        .battlefield(1, [BEAR])
        .hand(0, [card_id, card_id] if not graveyard else [IF_ALONE])
        .library(0, ["plains"] * 20)
        .library(1, ["forest"] * 20)
        .active(0)
    )
    if graveyard:
        b = b.graveyard(0, [card_id])
    game = b.build()
    p = game.state.players[0]
    return game, (p.graveyard[0] if graveyard else p.hand[0])


def cast(game, oid: int) -> None:
    """Cast that copy, at the opponent's Bear if it takes a target."""
    game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid))


def resolve(game) -> None:
    """Pass until the stack is empty and the table is back at priority."""
    for _ in range(200):
        decision = game.pending()
        if not game.state.stack and decision.kind is DecisionKind.PRIORITY:
            return
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def their_bear(game) -> int:
    return next(o.oid for o in game.state.battlefield_objects(1) if o.def_id == BEAR)


class TestWhenTheConditionHolds:
    def test_it_goes_to_its_owners_hand(self, builder):
        game, oid = board(builder)
        cast(game, oid)
        resolve(game)
        obj = game.state.objects[oid]
        assert obj.zone is Zone.HAND
        assert oid in game.state.players[0].hand
        assert oid not in game.state.players[0].graveyard

    def test_its_effects_still_happened(self, builder):
        game, oid = board(builder)
        life = game.state.players[0].life
        cast(game, oid)
        resolve(game)
        assert game.state.players[0].life == life + 2

    def test_it_can_be_cast_again_from_hand(self, builder):
        game, oid = board(builder)
        cast(game, oid)
        resolve(game)
        assert any(
            a.kind is ActionKind.CAST and a.source == oid for a in game.legal_actions()
        )

    def test_the_mark_does_not_follow_it_into_its_next_life(self, builder):
        """400.7: the card in hand is a new object, unmarked."""
        game, oid = board(builder)
        cast(game, oid)
        resolve(game)
        assert game.state.objects[oid].returns_to_hand_on_resolution is False


class TestWhenTheConditionFails:
    def test_it_goes_to_the_graveyard(self, builder):
        game, oid = board(builder, my_creature=True)
        life = game.state.players[0].life
        cast(game, oid)
        resolve(game)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert game.state.players[0].life == life + 2


class TestOnlyOnResolution:
    def test_a_spell_whose_target_is_gone_goes_to_the_graveyard(self, builder):
        """608.2b: it does not resolve, so its instruction never happens."""
        game, oid = board(builder, KILL)
        bear = their_bear(game)
        cast(game, oid)
        assert game.state.stack, "on the stack, targeting the Bear"
        move_object(game.state, bear, Zone.GRAVEYARD, cause="test")
        resolve(game)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD

    def test_with_its_target_it_destroys_and_returns(self, builder):
        game, oid = board(builder, KILL)
        bear = their_bear(game)
        cast(game, oid)
        resolve(game)
        assert game.state.objects[bear].zone is Zone.GRAVEYARD
        assert game.state.objects[oid].zone is Zone.HAND


class TestAgainstTheOtherRiders:
    def test_it_wins_over_a_rider_that_only_replaces_the_graveyard(self, builder):
        """`exiles_itself` replaces the graveyard; the card never goes there."""
        game, oid = board(builder, EXILES)
        cast(game, oid)
        resolve(game)
        assert game.state.objects[oid].zone is Zone.HAND

    def test_cast_from_hand_a_flashback_card_returns(self, builder):
        game, oid = board(builder, FLASHBACK)
        cast(game, oid)
        resolve(game)
        assert game.state.objects[oid].zone is Zone.HAND

    def test_cast_with_flashback_it_is_exiled(self, builder):
        """702.34a: flashback exiles it wherever else it would go."""
        game, oid = board(builder, FLASHBACK, graveyard=True)
        life = game.state.players[0].life
        cast(game, oid)
        resolve(game)
        assert game.state.players[0].life == life + 2, "cast with flashback and resolved"
        assert game.state.objects[oid].zone is Zone.EXILE


class TestTheLoader:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "t_bad_return_self",
                "name": "Bad Return Self",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "colors": ["W"],
                "color_identity": ["W"],
                "types": ["Sorcery"],
                **extra,
            }
        )

    def test_it_loads_in_spell_effects(self):
        card = compile_card(
            self._card(spell_effects=[{"op": "return_self_to_hand_on_resolution"}])
        )
        assert card.spell_effects[0]["op"] == "return_self_to_hand_on_resolution"

    def test_in_an_ability_it_is_refused(self):
        with pytest.raises(Exception, match="spell_effects"):
            compile_card(
                self._card(
                    types=["Creature"],
                    power=1,
                    toughness=1,
                    abilities=[
                        {
                            "kind": "activated",
                            "cost": {"mana": "{1}"},
                            "effects": [{"op": "return_self_to_hand_on_resolution"}],
                        }
                    ],
                )
            )

    def test_a_key_beside_it_is_refused(self):
        with pytest.raises(Exception, match="takes no keys"):
            compile_card(
                self._card(
                    spell_effects=[{"op": "return_self_to_hand_on_resolution", "player": "you"}]
                )
            )


class TestTheWitness:
    """Haunting Imitation, the shipped card: its condition reads the reveals."""

    def _board(self, builder, my_top: str, their_top: str):
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 4)
            .hand(0, ["haunting_imitation", "haunting_imitation"])
            .library(0, [my_top] + ["plains"] * 10)
            .library(1, [their_top] + ["forest"] * 10)
            .active(0)
            .build()
        )
        return game, game.state.players[0].hand[0]

    def test_no_creature_revealed_returns_it(self, builder):
        game, oid = self._board(builder, "plains", "forest")
        cast(game, oid)
        resolve(game)
        assert game.state.objects[oid].zone is Zone.HAND
        assert not [o for o in game.state.battlefield_objects(0) if o.is_token]

    def test_a_creature_revealed_copies_it_and_bins_the_spell(self, builder):
        game, oid = self._board(builder, "plains", BEAR)
        cast(game, oid)
        resolve(game)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        tokens = [o for o in game.state.battlefield_objects(0) if o.is_token]
        assert [t.def_id for t in tokens] == [BEAR]
        assert pt(game, tokens[0].oid) == (1, 1)
        assert "flying" in keywords(game, tokens[0].oid)
        assert "Spirit" in chars(game.state, tokens[0].oid).subtypes
