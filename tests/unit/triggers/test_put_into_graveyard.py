"""The Gitrog Monster, Syr Konrad -- "whenever a card is put into a graveyard
**from anywhere**".

A card arrives in a graveyard from every zone: dying or being sacrificed off
the battlefield, discarded from a hand, milled or surveilled off a library,
countered or resolved off the stack, out of exile. Before
`EventType.PUT_INTO_GRAVEYARD` the trigger vocabulary saw only the first:
`dies` and `leaves_battlefield` are about a permanent leaving play, `discard`
is the hand alone, and nothing watched a library. A Gitrog built on
`leaves_battlefield` draws for a sacrificed land and never for a milled one --
which is the card's whole engine -- and one written as a `discard` trigger
beside a `dies` trigger still misses every mill, and fires twice for one
simultaneous move that takes lands from two zones.

The rule is 603.2 and 603.6a's zone-change trigger, with three narrowings the
printed lines need:

* "a land **card**" (111.1): a token is not a card, so a dying token fires
  nothing -- that is `dies`'s job, and Syr Konrad's first clause.
* "from anywhere **other than the battlefield**" (Syr Konrad): `from_zones`.
* "**one or more** land cards" (603.2c): `batched`, one firing per effect op,
  cost payment or discard, with every matching card in the batch bound as
  `moved` so "put one of **them** onto the battlefield" (Colossal
  Grave-Reaver) chooses among exactly those cards and never one already
  sitting in the graveyard.

A replacement that sends the card elsewhere (Rest in Peace, the commander's
903.9a) means it was never put into a graveyard, and fires nothing.

`t_greedy_land_drinker` is the counterfactual without `batched`, so the
batching claim is measured against the card that lacks it.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import discard_cards, mill_cards
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid, settle_completely

DRINKER = "t_land_drinker"
GREEDY = "t_greedy_land_drinker"
PINGER = "t_grave_pinger"
REAVER = "t_grave_reaver"
RETURNER = "t_grave_returner"
BEAR = "t_bear"


def resolve(game) -> None:
    """Put the queued triggers on the stack and let them resolve.

    Nothing queued is nothing to do: advancing a frozen board with no trigger
    waiting would auto-pass into later turns and their draws.
    """
    if not game.state.pending_triggers and not game.state.stack:
        return
    game._advance()
    settle_completely(game)


def one_op(game) -> None:
    """Open a fresh simultaneous group, as an effect op does."""
    game.state.event_batch += 1


def hand_size(game, pid: int = 0) -> int:
    return len(game.state.players[pid].hand)


def drinker_board(builder, watcher: str = DRINKER, *, library=(), hand=(), mine=()):
    game = (
        builder(players=2)
        .battlefield(0, [watcher, *mine])
        .library(0, [*library, BEAR, BEAR, BEAR, BEAR])
        .hand(0, list(hand))
        .library(1, ["forest", BEAR, BEAR])
        .build(advance=False)
    )
    return game, only_oid(game, watcher)


class TestEveryZoneIsHeard:
    def test_a_milled_land_draws(self, builder):
        game, _ = drinker_board(builder, library=["forest"])
        before = hand_size(game)
        one_op(game)
        mill_cards(game.state, 0, 1)
        resolve(game)
        assert hand_size(game) == before + 1

    def test_a_discarded_land_draws(self, builder):
        game, _ = drinker_board(builder, hand=["forest"])
        before = hand_size(game)
        one_op(game)
        discard_cards(game.state, 0, list(game.state.players[0].hand))
        resolve(game)
        assert hand_size(game) == before  # one discarded, one drawn

    def test_a_sacrificed_land_draws(self, builder):
        game, _ = drinker_board(builder, mine=["forest"])
        land = only_oid(game, "forest", 0)
        before = hand_size(game)
        one_op(game)
        move_object(game.state, land, Zone.GRAVEYARD, cause="sacrificed")
        resolve(game)
        assert hand_size(game) == before + 1

    def test_a_card_from_exile_draws(self, builder):
        game, _ = drinker_board(builder, library=["forest"])
        land = game.state.players[0].library[0]
        move_object(game.state, land, Zone.EXILE, cause="test")
        before = hand_size(game)
        one_op(game)
        move_object(game.state, land, Zone.GRAVEYARD, to_player=0, cause="test")
        resolve(game)
        assert hand_size(game) == before + 1

    def test_the_event_carries_the_origin_and_the_owner(self, builder):
        game, _ = drinker_board(builder, library=["forest"])
        one_op(game)
        mill_cards(game.state, 0, 1)
        events = [e for e in game.state.events if e.type == EventType.PUT_INTO_GRAVEYARD]
        assert len(events) == 1
        assert events[0].player == 0
        assert events[0].data["from_zone"] == "library"


class TestTheFilterAndTheController:
    def test_a_nonland_card_does_not_draw(self, builder):
        game, _ = drinker_board(builder)
        before = hand_size(game)
        one_op(game)
        mill_cards(game.state, 0, 2)
        resolve(game)
        assert hand_size(game) == before

    def test_an_opponents_graveyard_is_not_yours(self, builder):
        """"…into **your** graveyard": the actor is the graveyard's owner."""
        game, _ = drinker_board(builder)
        before = hand_size(game)
        one_op(game)
        mill_cards(game.state, 1, 1)
        resolve(game)
        assert hand_size(game) == before

    def test_a_token_is_not_a_card(self, builder):
        """111.1: a dying token fires `dies`, never this."""
        game, _ = drinker_board(builder)
        token = game.state.battlefield[-1]
        game.state.objects[token].is_token = True
        one_op(game)
        move_object(game.state, token, Zone.GRAVEYARD, cause="test")
        assert not [e for e in game.state.events if e.type == EventType.PUT_INTO_GRAVEYARD]


class TestOneOrMore:
    def test_two_milled_lands_draw_once(self, builder):
        game, _ = drinker_board(builder, library=["forest", "forest"])
        before = hand_size(game)
        one_op(game)
        mill_cards(game.state, 0, 2)
        resolve(game)
        assert hand_size(game) == before + 1

    def test_without_batched_the_same_mill_draws_twice(self, builder):
        """The counterfactual: identical trigger, no `batched`."""
        game, _ = drinker_board(builder, GREEDY, library=["forest", "forest"])
        before = hand_size(game)
        one_op(game)
        mill_cards(game.state, 0, 2)
        resolve(game)
        assert hand_size(game) == before + 2

    def test_two_separate_mills_draw_twice(self, builder):
        """Not `max_per_turn: 1`: a second, separate move fires again.

        The first draw takes the Bear between the two Forests.
        """
        game, _ = drinker_board(builder, library=["forest", BEAR, "forest"])
        before = hand_size(game)
        for _ in range(2):
            one_op(game)
            mill_cards(game.state, 0, 1)
            resolve(game)
        assert hand_size(game) == before + 2


class TestFromZones:
    """Syr Konrad's "from anywhere other than the battlefield"."""

    def pinger(self, builder, *, mine=()):
        game = (
            builder(players=2)
            .battlefield(0, [PINGER, *mine])
            .library(0, [BEAR, "forest"])
            .library(1, [BEAR])
            .build(advance=False)
        )
        return game

    def test_a_milled_creature_card_pings_either_graveyard(self, builder):
        game = self.pinger(builder)
        life = game.state.players[1].life
        one_op(game)
        mill_cards(game.state, 0, 1)
        one_op(game)
        mill_cards(game.state, 1, 1)
        resolve(game)
        assert game.state.players[1].life == life - 2

    def test_a_creature_dying_is_not_this_clause(self, builder):
        game = self.pinger(builder, mine=[BEAR])
        bear = only_oid(game, BEAR, 0)
        life = game.state.players[1].life
        one_op(game)
        move_object(game.state, bear, Zone.GRAVEYARD, cause="destroyed")
        resolve(game)
        assert game.state.players[1].life == life

    def test_a_creature_card_off_the_stack_pings(self, builder):
        game = self.pinger(builder)
        card = game.state.players[0].library[0]
        game.state.players[0].library.remove(card)
        game.state.objects[card].zone = Zone.STACK
        life = game.state.players[1].life
        one_op(game)
        move_object(game.state, card, Zone.GRAVEYARD, to_player=0, cause="countered")
        resolve(game)
        assert game.state.players[1].life == life - 1


class TestThem:
    """Colossal Grave-Reaver: "put one of **them** onto the battlefield"."""

    def test_only_a_card_from_the_batch_can_return(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [REAVER])
            .graveyard(0, ["t_elf"])
            .library(0, [BEAR, "forest", BEAR])
            .build(advance=False)
        )
        buried = game.state.players[0].graveyard[0]
        milled = list(game.state.players[0].library[:3])
        one_op(game)
        mill_cards(game.state, 0, 3)
        pending = [t for t in game.state.pending_triggers]
        assert len(pending) == 1
        assert sorted(pending[0].bindings["moved"]) == sorted(
            oid for oid in milled if game.state.card_of(game.state.objects[oid]).id == BEAR
        )
        resolve(game)
        assert game.state.objects[buried].zone is Zone.GRAVEYARD
        returned = [oid for oid in milled if game.state.objects[oid].zone is Zone.BATTLEFIELD]
        assert len(returned) == 1
        assert game.state.card_of(game.state.objects[returned[0]]).id == BEAR

    def test_a_discarded_creature_is_not_from_your_library(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [REAVER])
            .hand(0, [BEAR])
            .build(advance=False)
        )
        one_op(game)
        discard_cards(game.state, 0, list(game.state.players[0].hand))
        assert not game.state.pending_triggers


class TestFromItsOwnGraveyard:
    """Centaur Vinecrasher: the ability listens while the card is in a graveyard."""

    def test_it_returns_itself_when_a_land_arrives(self, builder):
        game = (
            builder(players=2)
            .graveyard(0, [RETURNER])
            .library(1, ["forest"])
            .build(advance=False)
        )
        oid = game.state.players[0].graveyard[0]
        one_op(game)
        mill_cards(game.state, 1, 1)
        resolve(game)
        assert game.state.objects[oid].zone is Zone.HAND

    def test_it_does_not_listen_from_the_battlefield(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [RETURNER])
            .library(1, ["forest"])
            .build(advance=False)
        )
        one_op(game)
        mill_cards(game.state, 1, 1)
        assert not game.state.pending_triggers


class TestReplacedArrivals:
    def test_rest_in_peace_means_it_never_arrived(self, builder):
        game, _ = drinker_board(builder, library=["forest"], mine=["rest_in_peace"])
        one_op(game)
        mill_cards(game.state, 0, 1)
        assert not [e for e in game.state.events if e.type == EventType.PUT_INTO_GRAVEYARD]
        assert not game.state.pending_triggers


class TestTheLoaderRefuses:
    def card(self, trigger: dict):
        return compile_card(CardModel.model_validate({
            "id": "t_probe",
            "name": "Probe",
            "oracle_text": "",
            "mana_cost": "{1}",
            "types": ["Artifact"],
            "abilities": [
                {
                    "kind": "triggered",
                    "trigger": trigger,
                    "text": "Probe.",
                    "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
                }
            ],
        }))

    def test_a_graveyard_is_not_an_origin(self):
        with pytest.raises(DslError, match="from_zones"):
            self.card({"event": "put_into_graveyard", "from_zones": ["graveyard"]})

    def test_the_battlefield_is_an_origin_here(self):
        card = self.card({"event": "put_into_graveyard", "from_zones": ["battlefield"]})
        assert card.abilities[0].trigger.from_zones == ("battlefield",)

    def test_from_zones_still_means_nothing_on_dies(self):
        with pytest.raises(DslError, match="from_zones"):
            self.card({"event": "dies", "from_zones": ["hand"]})
