"""Foreboding Steamboat — "put a card exiled with it into its owner's graveyard".

    When this Vehicle enters, each player chooses two nontoken, non-Vehicle
    creatures they control. Exile them until this Vehicle leaves the
    battlefield.
    Whenever this Vehicle attacks, put a card exiled with it into its owner's
    graveyard. If you do, investigate.

The cards exiled with the Steamboat sit in several players' exiles, because
exile is kept per owner, and the attack takes **one** of them, whoever owns it.
`search_zones` over exile takes its count per player and would take one from
each owner, and may take none; `return_from_graveyard` reads a graveyard. So
`put_exiled_into_graveyard` is one choice over every exile the selector walks,
and each card goes to its owner's graveyard (400.3).

"If you do" is an `if` on the op's `as`, which holds only the cards that
reached a graveyard: under Rest in Peace the card is exiled instead, the
original event never happened (614.6), and there is no Clue.

The leaves-the-battlefield return then gives back only what is still exiled,
because a card that went to a graveyard is a new object with no link (400.7).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy, exile, link_exiled
from tests.conftest import action_for_card, oids_of, only_oid, settle_completely

BOAT = "foreboding_steamboat"
BEAR = "t_bear"
CLUE = "clue_token"
#: The attack trigger, in the card's printed order.
ATTACK = 2


def board(builder, *, mine=(BEAR, BEAR, BEAR), theirs=(BEAR, BEAR), extra=()):
    """The Steamboat on the battlefield, its victims not yet exiled."""
    return (
        builder(players=2)
        .battlefield(0, [BOAT, *mine, *extra])
        .battlefield(1, list(theirs))
        .build(advance=False)
    )


def exile_with_boat(game, *oids):
    boat = only_oid(game, BOAT)
    for oid in oids:
        exile(game.state, oid, by=boat)
        link_exiled(game.state, oid, boat)


def attack_trigger(game, *, pick: int = 0):
    """Resolve the attack trigger, answering any choice with option ``pick``.

    Returns the decisions asked along the way.
    """
    state = game.state
    boat = only_oid(game, BOAT)
    ctx = EffectContext(state=state, controller=0, source_oid=boat)
    gen = execute(ctx, state.card_of(state.objects[boat]).abilities[ATTACK].effects)
    asked = []
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        send = [pick]


def clues(game, pid: int = 0) -> int:
    return len(oids_of(game, CLUE, pid))


def ids(game, oids) -> list[str]:
    return sorted(game.state.objects[o].def_id for o in oids)


class TestOneCardFromAmongEveryExile:
    def test_the_controller_chooses_among_both_owners_cards(self, builder):
        game = board(builder)
        mine = oids_of(game, BEAR, 0)[0]
        theirs = oids_of(game, BEAR, 1)[0]
        exile_with_boat(game, mine, theirs)
        (decision,) = attack_trigger(game)
        assert decision.player == 0
        assert {o.value for o in decision.options} == {mine, theirs}
        assert decision.min_count == decision.max_count == 1

    def test_exactly_one_card_moves(self, builder):
        """`search_zones`' per-player count would have moved one of each."""
        game = board(builder)
        mine = oids_of(game, BEAR, 0)[0]
        theirs = oids_of(game, BEAR, 1)[0]
        exile_with_boat(game, mine, theirs)
        attack_trigger(game, pick=1)
        state = game.state
        assert state.players[1].graveyard == [theirs]
        assert state.players[0].exile == [mine]
        assert state.players[0].graveyard == []

    def test_the_card_goes_to_its_owners_graveyard(self, builder):
        game = board(builder)
        theirs = oids_of(game, BEAR, 1)[0]
        exile_with_boat(game, theirs)
        attack_trigger(game)
        assert game.state.players[1].graveyard == [theirs]
        assert game.state.players[0].graveyard == []

    def test_a_card_something_else_exiled_is_not_offered(self, builder):
        game = board(builder)
        linked = oids_of(game, BEAR, 1)[0]
        stranger = oids_of(game, BEAR, 1)[1]
        exile_with_boat(game, linked)
        exile(game.state, stranger)
        assert attack_trigger(game) == []
        assert game.state.players[1].graveyard == [linked]
        assert game.state.players[1].exile == [stranger]


class TestIfYouDo:
    def test_a_card_moved_investigates(self, builder):
        game = board(builder)
        exile_with_boat(game, oids_of(game, BEAR, 1)[0])
        attack_trigger(game)
        assert clues(game) == 1

    def test_nothing_exiled_with_it_does_not(self, builder):
        game = board(builder)
        exile(game.state, oids_of(game, BEAR, 1)[0])
        attack_trigger(game)
        assert clues(game) == 0

    def test_a_card_rest_in_peace_exiles_instead_does_not(self, builder):
        game = board(builder, extra=("rest_in_peace",))
        theirs = oids_of(game, BEAR, 1)[0]
        exile_with_boat(game, theirs)
        attack_trigger(game)
        assert game.state.players[1].graveyard == []
        assert game.state.players[1].exile == [theirs]
        assert clues(game) == 0


class TestTheWholeCard:
    def cast(self, builder):
        game = (
            builder(players=2)
            .hand(0, [BOAT])
            .battlefield(0, ["swamp"] * 5 + [BEAR] * 3)
            .battlefield(1, [BEAR] * 2)
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, BOAT))
        settle_completely(game)
        return game

    def test_each_player_exiles_two_of_their_creatures(self, builder):
        game = self.cast(builder)
        assert ids(game, game.state.players[0].exile) == [BEAR, BEAR]
        assert ids(game, game.state.players[1].exile) == [BEAR, BEAR]
        assert len(oids_of(game, BEAR, 0)) == 1
        assert oids_of(game, BEAR, 1) == []

    def test_leaving_returns_only_what_is_still_exiled(self, builder):
        game = self.cast(builder)
        attack_trigger(game, pick=0)
        buried = game.state.players[0].graveyard + game.state.players[1].graveyard
        assert len(buried) == 1
        destroy(game.state, only_oid(game, BOAT))
        settle_completely(game)
        assert game.state.players[0].exile == []
        assert game.state.players[1].exile == []
        assert len(oids_of(game, BEAR, 0)) + len(oids_of(game, BEAR, 1)) == 4
        assert buried[0] not in game.state.battlefield


def _card(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_bury_probe",
            "name": "Bury Probe",
            "mana_cost": "{B}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }
    )


class TestTheLoader:
    def test_a_selector_is_required(self):
        with pytest.raises(DslError, match="needs an 'objects' selector"):
            compile_card(_card({"op": "put_exiled_into_graveyard"}))

    @pytest.mark.parametrize("zone", ["battlefield", "graveyard", "hand", "library"])
    def test_a_zone_other_than_exile_is_refused(self, zone):
        with pytest.raises(DslError, match="out of exile"):
            compile_card(
                _card({"op": "put_exiled_into_graveyard", "objects": {"zone": zone}})
            )

    def test_exile_loads(self):
        compile_card(
            _card(
                {
                    "op": "put_exiled_into_graveyard",
                    "as": "buried",
                    "objects": {"zone": "exile", "controller": "any", "count": 1},
                }
            )
        )
