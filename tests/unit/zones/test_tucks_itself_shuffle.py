""""Shuffle <this card> into its owner's library." -- `tucks_itself: "shuffle"`

    Black Sun's Zenith -- "Put X -1/-1 counters on each creature. **Shuffle
    Black Sun's Zenith into its owner's library.**"

The shuffle form of the `tucks_itself` rider on the destination
`stack._place_after_resolution` picks. 608.2n puts a resolved instant or
sorcery into its owner's graveyard unless the card says otherwise; this one
says the library, and then 701.24a: the whole library is randomized *with the
card in it*.

**It could not be `tucks_itself: "bottom"` plus a `shuffle` op.** The op runs in
`spell_effects`, while the card is still on the stack, so the library would be
shuffled without it and the card would then land on the bottom -- where its
owner knows to the turn when it comes back. Nor a `shuffle` op alone: the card
would go to the graveyard regardless.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from tests.conftest import _default_answer, action_for_card

SHUFFLE = "t_tucks_itself_shuffle"  # sorcery: gain 2 life. Shuffle it into its owner's library.
BOTTOM = "t_tucks_itself_bottom"  # the bottom form, for the contrast
LIBRARY = ["forest"] * 20


def board(builder, card_id: str, library=LIBRARY, seed: int = 0):
    return (
        builder(players=2, seed=seed)
        .battlefield(0, ["plains"] * 8)
        .hand(0, [card_id])
        .library(0, list(library))
        .library(1, ["forest"] * 20)
        .active(0)
        .build()
    )


def cast_and_settle(game, card_id: str) -> int:
    action = action_for_card(game, ActionKind.CAST, card_id)
    oid = action.source
    game.apply(action)
    for _ in range(100):
        decision = game.pending()
        if decision is None or not game.state.stack:
            break
        game.apply(_default_answer(game, decision))
    assert oid is not None
    return oid


class TestWhereItGoes:
    def test_it_ends_in_its_owners_library(self, builder):
        game = board(builder, SHUFFLE)
        oid = cast_and_settle(game, SHUFFLE)
        assert game.state.objects[oid].zone is Zone.LIBRARY
        assert oid in game.state.players[0].library
        assert oid not in game.state.players[0].graveyard
        assert len(game.state.players[0].library) == len(LIBRARY) + 1

    def test_it_still_did_what_it_said(self, builder):
        game = board(builder, SHUFFLE)
        life = game.state.players[0].life
        cast_and_settle(game, SHUFFLE)
        assert game.state.players[0].life == life + 2

    def test_it_is_the_only_card_of_an_empty_library(self, builder):
        """The boundary: nothing to shuffle it among, and still the library."""
        game = board(builder, SHUFFLE, library=[])
        oid = cast_and_settle(game, SHUFFLE)
        assert game.state.players[0].library == [oid]

    def test_the_opponents_library_is_left_alone(self, builder):
        game = board(builder, SHUFFLE)
        theirs = list(game.state.players[1].library)
        cast_and_settle(game, SHUFFLE)
        # Whatever they have drawn since came off the top; the rest is in order.
        now = game.state.players[1].library
        assert now == theirs[len(theirs) - len(now):]


class TestTheLibraryIsShuffledWithIt:
    def _positions(self, builder, card_id: str) -> set[int]:
        seen = set()
        for seed in range(12):
            game = board(builder, card_id, seed=seed)
            oid = cast_and_settle(game, card_id)
            seen.add(game.state.players[0].library.index(oid))
        return seen

    def test_where_it_lands_varies_with_the_shuffle(self, builder):
        """701.24a: randomized with the card in it, so no fixed position."""
        assert len(self._positions(builder, SHUFFLE)) > 1

    def test_the_rest_of_the_library_is_reordered_too(self, builder):
        """The whole library is shuffled, not the card inserted at random."""
        game = board(builder, SHUFFLE)
        before = list(game.state.players[0].library)
        oid = cast_and_settle(game, SHUFFLE)
        after = [o for o in game.state.players[0].library if o != oid]
        assert sorted(after) == sorted(before)
        assert after != before

    def test_the_bottom_form_is_still_the_bottom(self, builder):
        """The near miss: "bottom" never moves, whatever the seed."""
        assert self._positions(builder, BOTTOM) == {len(LIBRARY)}

    def test_the_shuffle_is_the_games_seeded_rng(self, builder):
        """Determinism: the same seed puts it in the same place."""
        first = board(builder, SHUFFLE, seed=3)
        second = board(builder, SHUFFLE, seed=3)
        cast_and_settle(first, SHUFFLE)
        cast_and_settle(second, SHUFFLE)
        assert first.state.players[0].library == second.state.players[0].library


class TestTheLoader:
    def _card(self, **extra):
        return CardModel.model_validate(
            {
                "id": "t_bad_tucks_itself_shuffle",
                "name": "Bad Tucks Itself Shuffle",
                "oracle_text": "Bad.",
                "mana_cost": "{W}",
                "colors": ["W"],
                "color_identity": ["W"],
                "types": ["Sorcery"],
                "spell_effects": [{"op": "gain_life", "amount": {"const": 1}}],
                **extra,
            }
        )

    def test_shuffle_loads(self):
        assert compile_card(self._card(tucks_itself="shuffle")).tucks_itself == "shuffle"

    def test_a_permanent_carrying_it_is_refused(self):
        """It replaces the graveyard, and a permanent never reaches the rider."""
        with pytest.raises(Exception, match="tucks_itself"):
            compile_card(
                self._card(
                    types=["Creature"], power=1, toughness=1, spell_effects=[],
                    tucks_itself="shuffle",
                )
            )
