"""Cloak and Dagger, Entwined — "…until Cloak and Dagger leave the battlefield".

    When Cloak and Dagger enter, choose target opponent and up to one target
    creature they control. They reveal their hand. You may exile a nonland card
    from their hand or the chosen creature until Cloak and Dagger leave the
    battlefield.

One exile with two possible origins, and one return that has to undo whichever
happened: the card taken out of a hand goes back to that hand, the permanent
taken off the battlefield goes back to the battlefield.

**Every neighbouring op hardwires its destination**, which is why none of them
can say this. `return_to_hand` is the hand; `put_onto_battlefield` is the
battlefield; `return_from_graveyard` takes a `destination` but reads its pool
out of a graveyard. Writing it as two ops filtered by origin would be two
sentences where the printing has one — and there was nothing to filter on
either, since only the graveyard kept an arrival record.

So `zones.exile` stamps `exiled_from` on the way out, on every exile route
rather than in one op, and `return_to_origin` reads it back. Read before the
move and written after, because `move_object` runs `reset_permanent_state` in
between — the same order `exiled_by` is written in, for the same reason.

**Owner, on both branches.** A card leaving exile goes to its *owner's* hand,
and 400.7's exceptions do not reach a permanent coming back from an
exile-until effect.

A card with no recorded origin is left where it is, which is the same answer
400.7 gives: nowhere to return it to. Guessing the battlefield would put a card
from somebody's hand onto the board.
"""

from __future__ import annotations

import pytest

from automtg.engine.effects import execute
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import Zone
from automtg.engine.structs import TargetRef
from automtg.engine.zones import exile as exile_object
from tests.conftest import only_oid

CLOAK = "t_cloak"
BEAR = "t_bear"
BOLT = "t_bolt"


def board(builder):
    """They hold a spell and a land, and control a Bear."""
    return (
        builder(players=2)
        .battlefield(0, [CLOAK])
        .battlefield(0, ["swamp"] * 2)
        .battlefield(1, [BEAR])
        .hand(1, [BOLT, "forest"])
        .library(0, ["forest"] * 10)
        .build(advance=False)
    )


def run(game, index: int, *, targets=None, pick: int = 0):
    """Run one of the card's abilities, taking option ``pick`` if asked."""
    state = game.state
    source = only_oid(game, CLOAK)
    ctx = EffectContext(
        state=state, controller=0, source_oid=source, targets=dict(targets or {})
    )
    gen = execute(ctx, state.card_of(state.objects[source]).abilities[index].effects)
    send = None
    while True:
        try:
            gen.send(send)
        except StopIteration:
            return game
        send = [pick]


def take(game, *, creature: bool):
    """Exile either the Bear or the spell in their hand.

    The union offers the hand card first and the targeted creature second,
    because that is the written order of the branches.
    """
    targets = {"who": (TargetRef.player(1),)}
    if creature:
        targets["what"] = (TargetRef.obj(only_oid(game, BEAR)),)
    return run(game, 0, targets=targets, pick=1 if creature else 0)


def leaves(game):
    """Move the permanent off the battlefield and run its leave trigger."""
    state = game.state
    source = only_oid(game, CLOAK)
    state.objects[source].zone = Zone.GRAVEYARD
    return run(game, 1)


def ids(oids, state):
    return sorted(state.card(o).id for o in oids)


class TestACardTakenFromAHand:
    def test_it_is_exiled(self, builder):
        game = take(board(builder), creature=False)
        assert ids(game.state.players[1].exile, game.state) == [BOLT]

    def test_it_goes_back_to_that_hand(self, builder):
        game = leaves(take(board(builder), creature=False))
        assert ids(game.state.players[1].hand, game.state) == ["forest", BOLT]
        assert game.state.players[1].exile == []

    def test_it_does_not_come_back_onto_the_battlefield(self, builder):
        """The failure mode of a hardwired destination, and the reason the
        origin is recorded at all."""
        game = leaves(take(board(builder), creature=False))
        assert ids(
            [o.oid for o in game.state.battlefield_objects(1)], game.state
        ) == [BEAR]


class TestAPermanentTakenFromTheBattlefield:
    def test_it_is_exiled(self, builder):
        game = take(board(builder), creature=True)
        assert ids(game.state.players[1].exile, game.state) == [BEAR]

    def test_it_goes_back_onto_the_battlefield(self, builder):
        game = leaves(take(board(builder), creature=True))
        assert ids(
            [o.oid for o in game.state.battlefield_objects(1)], game.state
        ) == [BEAR]

    def test_it_comes_back_under_its_owners_control(self, builder):
        """The exile was somebody else's doing; the card is still theirs."""
        game = leaves(take(board(builder), creature=True))
        bear = only_oid(game, BEAR)
        assert game.state.objects[bear].controller == 1

    def test_it_does_not_come_back_to_a_hand(self, builder):
        game = leaves(take(board(builder), creature=True))
        assert ids(game.state.players[1].hand, game.state) == ["forest", BOLT]


class TestOnlyWhatThisPermanentExiled:
    def test_a_card_exiled_by_something_else_stays(self, builder):
        """`exiled_with: "self"` -- and the reason `link` records it."""
        game = board(builder)
        stranded = game.state.players[1].hand[1]
        exile_object(game.state, stranded, cause="test")
        take(game, creature=True)
        leaves(game)
        assert ids(game.state.players[1].exile, game.state) == ["forest"]


class TestTheOriginRecord:
    def test_every_exile_route_records_it(self, builder):
        """Written in `zones.exile` rather than in the op, so a card exiled by
        anything at all can be given back."""
        game = board(builder)
        oid = game.state.players[1].hand[0]
        exile_object(game.state, oid, cause="test")
        assert game.state.objects[oid].exiled_from == "hand"

    def test_it_is_cleared_when_the_card_leaves_exile(self, builder):
        game = leaves(take(board(builder), creature=True))
        bear = only_oid(game, BEAR)
        assert game.state.objects[bear].exiled_from is None

    def test_a_card_with_no_origin_is_left_alone(self, builder):
        """400.7 has no answer either, and guessing the battlefield would put a
        card from a hand onto the board."""
        game = take(board(builder), creature=False)
        state = game.state
        exiled = state.players[1].exile[0]
        state.objects[exiled].exiled_from = None
        leaves(game)
        assert state.players[1].exile == [exiled]


class TestTheLoaderChecksIt:
    def test_a_return_with_nothing_to_return_is_refused(self):
        from automtg.cards.loader import compile_card
        from automtg.cards.schema import CardModel
        from automtg.engine.errors import DslError

        with pytest.raises(DslError, match="nothing to return"):
            compile_card(
                CardModel.model_validate(
                    {
                        "id": "t_bad_return",
                        "name": "Test Bad Return",
                        "oracle_text": "Return it.",
                        "mana_cost": "{1}",
                        "types": ["Sorcery"],
                        "spell_effects": [{"op": "return_to_origin"}],
                    }
                ),
                source="test",
            )
