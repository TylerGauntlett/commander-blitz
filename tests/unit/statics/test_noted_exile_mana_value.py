"""Bell Borca -- a size read off the mana values noted as cards are exiled.

    Note the mana value of each card as it's put into exile.
    Bell Borca's power is equal to the greatest number noted for it this turn.

Two abilities and one record. The `note_exiled_mana_value` static makes its
permanent note, under its own oid on `TurnLedger.exile_mana_values_noted`, the
mana value of every object put into exile while it is on the battlefield --
from any zone, by anyone. The `greatest_noted_exile_mana_value` static value
reads the largest of them back, 0 with none, and the cleanup step forgets them.

The numbers belong to the object (the rulings): a card exiled before Bell Borca
entered was noted for nobody, and a Bell Borca that leaves and comes back is a
new object (400.7) with nothing noted. The near misses are wrong in both
directions: `extreme_value` over the exile zone reads cards still *in* exile,
from any turn, and forgets one that has left; and no trigger can see a card
exiled before the permanent's abilities could trigger.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.loader.vocabulary import GRANTABLE_STATIC_EFFECTS
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import create_token
from commanderblitz.engine.stack import pull_spell_off_stack, push_spell
from commanderblitz.engine.zones import exile, move_object
from tests.conftest import oids_of, only_oid, pass_until, pt, static_probe

NOTER = "t_exile_noter"
BEARS = "grizzly_bears"     # mana value 2
GIANT = "hill_giant"        # mana value 4
ANGEL = "serra_angel"       # mana value 5
BOLT = "lightning_bolt"     # mana value 1


def position(builder, *, noter_in_hand: bool = False):
    """Player 0 with the noter on the battlefield (or in hand), forests to cast
    a Bears, and a card worth exiling in every zone. Returns ``(game, noter)``."""
    b = (
        builder(players=2)
        .battlefield(0, ([] if noter_in_hand else [NOTER]) + ["forest"] * 2)
        .battlefield(1, [ANGEL])
        .hand(0, [BEARS, GIANT] + ([NOTER] if noter_in_hand else []))
        .graveyard(1, [GIANT])
        .library(0, [ANGEL] + ["forest"] * 10)
        .library(1, ["forest"] * 10)
    )
    game = b.build()
    noter = oids_of(game, NOTER, 0)
    if noter_in_hand:
        noter = [o for o in game.state.players[0].hand if game.state.objects[o].def_id == NOTER]
    return game, noter[0]


def in_hand(game, card_id: str, pid: int = 0) -> int:
    return next(o for o in game.state.players[pid].hand if game.state.objects[o].def_id == card_id)


def power(game, oid: int) -> int:
    return pt(game, oid)[0]


def noted(game, oid: int) -> list[int]:
    return game.state.turn_ledger.exile_mana_values_noted.get(oid, [])


class TestEveryZoneIsNoted:
    def test_nothing_noted_is_power_0(self, builder):
        game, noter = position(builder)

        assert pt(game, noter) == (0, 5)

    def test_from_the_library(self, builder):
        game, noter = position(builder)
        top = game.state.players[0].library[0]
        move_object(game.state, top, Zone.EXILE)

        assert power(game, noter) == 5

    def test_from_a_graveyard_an_opponent_owns(self, builder):
        game, noter = position(builder)
        move_object(game.state, game.state.players[1].graveyard[0], Zone.EXILE)

        assert power(game, noter) == 4

    def test_from_the_battlefield(self, builder):
        game, noter = position(builder)
        assert exile(game.state, only_oid(game, ANGEL, 1))

        assert power(game, noter) == 5

    def test_from_the_hand(self, builder):
        game, noter = position(builder)
        move_object(game.state, in_hand(game, BEARS), Zone.EXILE)

        assert power(game, noter) == 2

    def test_from_the_stack(self, builder):
        game, noter = position(builder)
        spell = push_spell(game.state, in_hand(game, BEARS), 0)
        pull_spell_off_stack(game.state, spell.sid, Zone.EXILE)

        assert power(game, noter) == 2

    def test_a_token_is_noted_with_its_mana_value(self, builder):
        game, noter = position(builder)
        token = create_token(game.state, "soldier_1_1_w", 0, 1)[0]
        exile(game.state, token)

        assert noted(game, noter) == [0]
        assert power(game, noter) == 0


class TestTheGreatestWins:
    def test_a_smaller_number_later_does_not_shrink_it(self, builder):
        game, noter = position(builder)
        move_object(game.state, game.state.players[1].graveyard[0], Zone.EXILE)
        move_object(game.state, in_hand(game, BEARS), Zone.EXILE)

        assert noted(game, noter) == [4, 2]
        assert power(game, noter) == 4

    def test_a_larger_number_later_grows_it(self, builder):
        game, noter = position(builder)
        move_object(game.state, in_hand(game, BEARS), Zone.EXILE)
        assert power(game, noter) == 2
        exile(game.state, only_oid(game, ANGEL, 1))

        assert power(game, noter) == 5

    def test_the_number_outlives_the_card_leaving_exile(self, builder):
        game, noter = position(builder)
        giant = game.state.players[1].graveyard[0]
        move_object(game.state, giant, Zone.EXILE)
        move_object(game.state, giant, Zone.HAND)

        assert power(game, noter) == 4


class TestTheNotesBelongToThisObjectThisTurn:
    def test_they_reset_at_cleanup(self, builder):
        game, noter = position(builder)
        exile(game.state, only_oid(game, ANGEL, 1))
        assert power(game, noter) == 5
        turn = game.state.turn

        pass_until(game, lambda g: g.state.turn > turn)

        assert power(game, noter) == 0

    def test_a_card_exiled_before_it_entered_is_not_noted(self, builder):
        game, noter = position(builder, noter_in_hand=True)
        exile(game.state, only_oid(game, ANGEL, 1))
        move_object(game.state, noter, Zone.BATTLEFIELD)

        assert power(game, noter) == 0

    def test_it_notes_nothing_from_the_hand(self, builder):
        game, noter = position(builder, noter_in_hand=True)
        exile(game.state, only_oid(game, ANGEL, 1))

        assert noted(game, noter) == []
        assert power(game, noter) == 0

    def test_leaving_and_returning_starts_fresh(self, builder):
        game, noter = position(builder)
        exile(game.state, only_oid(game, ANGEL, 1))
        assert power(game, noter) == 5

        move_object(game.state, noter, Zone.HAND)
        move_object(game.state, noter, Zone.BATTLEFIELD)
        assert power(game, noter) == 0

        move_object(game.state, in_hand(game, BEARS), Zone.EXILE)
        assert power(game, noter) == 2

    def test_exiling_itself_notes_nothing_for_the_card_in_exile(self, builder):
        game, noter = position(builder)
        exile(game.state, noter)

        assert noted(game, noter) == []
        assert power(game, noter) == 0


class TestTheLoader:
    def test_the_note_takes_no_filter(self):
        with pytest.raises(DslError, match="note_exiled_mana_value"):
            compile_card(
                CardModel.model_validate(
                    static_probe({"effect": "note_exiled_mana_value", "affects": {"self_only": True}})
                )
            )

    def test_the_value_reads_self_only(self):
        with pytest.raises(DslError, match="only spec is 'self'"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "buff",
                            "affects": {"self_only": True},
                            "power": {"greatest_noted_exile_mana_value": "you"},
                        }
                    )
                )
            )

    def test_the_value_needs_the_card_to_note(self):
        with pytest.raises(DslError, match="has none"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "buff",
                            "affects": {"self_only": True},
                            "power": {"greatest_noted_exile_mana_value": "self"},
                        }
                    )
                )
            )

    def test_the_note_cannot_be_granted(self):
        assert "note_exiled_mana_value" not in GRANTABLE_STATIC_EFFECTS
