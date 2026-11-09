"""The Gitrog Monster -- "Whenever one or more land cards are put into your
graveyard **from anywhere**…".

Rule 700.4 and 400.3: a card put into a graveyard goes to its owner's, from
whatever zone it was in, and a trigger that says "from anywhere" hears every
road in -- a death or sacrifice, a discard, a mill or surveil, a spell leaving
the stack. Every trigger the engine had saw one road: `dies` and
`leaves_battlefield` the battlefield, `discard` the hand, and none of them a
mill, which is what Turntimber Sower, Skola Grovedancer and Crawling Sensation
are built around. Two of them side by side still miss the library and fire
twice for one move.

`put_into_graveyard` is fired from `zones.move_object`, the one funnel, beside
`leaves_graveyard` and for its reason: `ZONE_CHANGE` stays off the trigger bus.
The claims, each measured against the card that lacks the clause:

* **Every road in**, into **your** graveyard (the owner's, 400.3), and never a
  token, which is not a card (111.1).
* **"One or more"** (603.2c) is `batched`: a mill of three lands is one Plant
  (Turntimber Sower), where the per-card form gains three (Skola Grovedancer).
* **"For the first time each turn"** (Crawling Sensation) is `nth: 1`, counted
  off the turn ledger, so a land milled *before* the enchantment entered was the
  first time. `max_per_turn: 1` (Sand Scout's "triggers only once each turn")
  is the near miss and fires there.
* **"From anywhere other than the battlefield"** (Disa the Restless, Syr
  Konrad) is `from_zones`; a death is then not one.
* **"Put one of them"** (Colossal Grave-Reaver) is the group's matching cards,
  bound as `moved`.
* **"When this card is put into a graveyard"** (Worldspine Wurm) works from
  the graveyard, and a permanent dying looks back in time (603.10a).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import mill_cards
from commanderblitz.engine.zones import move_object
from tests.conftest import only_oid
from tests.conftest import settle as settle_stack

SOWER = "t_sower"
GROVEDANCER = "t_grovedancer"
SENSATION = "t_sensation"
CAPPED = "t_capped_sower"
KONRAD = "t_konrad"
REAVER = "t_reaver"
WURM = "t_wurm"
LAND_CREATURE = "t_land_creature"
BEAR = "t_bear"


def board(builder, watcher: str, *, library=(), theirs=(), hand=(), battlefield=()):
    """The watcher on player 0's battlefield, with an exact library top."""
    game = (
        builder(players=2)
        .battlefield(0, [watcher, *battlefield])
        .library(0, list(library) + ["island"] * 5)
        .library(1, list(theirs) + ["island"] * 5)
        .hand(0, list(hand))
        .build(advance=False)
    )
    return game, only_oid(game, watcher)


def settle(game) -> None:
    """Resolve what the move queued, from a board built without advancing.

    Only when something queued: advancing an idle frozen board auto-passes into
    the next turn, which would clear the very ledger these tests read.
    """
    if not game.state.pending_triggers:
        return
    game._advance()
    settle_stack(game)


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


def mill(game, pid: int, count: int) -> None:
    """One effect op's worth of milling: one simultaneous group."""
    game.state.event_batch += 1
    mill_cards(game.state, pid, count)


def to_graveyard(game, oid: int, *, cause: str = "test") -> None:
    """One card put into its owner's graveyard, as its own group."""
    game.state.event_batch += 1
    move_object(game.state, oid, Zone.GRAVEYARD, cause=cause)


class TestEveryRoadIn:
    def test_a_milled_land_triggers(self, builder):
        game, _ = board(builder, GROVEDANCER, library=["forest"])
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 1

    def test_a_discarded_land_triggers(self, builder):
        game, _ = board(builder, GROVEDANCER, hand=["forest"])
        before = life(game)
        to_graveyard(game, game.state.players[0].hand[0], cause="discard")
        settle(game)
        assert life(game) == before + 1

    def test_a_land_dying_triggers(self, builder):
        """The road `dies` already saw, heard here too."""
        game, _ = board(builder, GROVEDANCER, battlefield=["forest"])
        before = life(game)
        to_graveyard(game, only_oid(game, "forest"), cause="sacrificed")
        settle(game)
        assert life(game) == before + 1

    def test_a_nonland_does_not(self, builder):
        game, _ = board(builder, GROVEDANCER, library=[BEAR])
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before

    def test_an_opponents_graveyard_does_not(self, builder):
        """"Your graveyard" is the owner's (400.3)."""
        game, _ = board(builder, GROVEDANCER, theirs=["forest"])
        before = life(game)
        mill(game, 1, 1)
        settle(game)
        assert life(game) == before

    def test_a_move_a_replacement_sent_elsewhere_does_not(self, builder):
        """The final destination: a card exiled instead never arrived."""
        game, _ = board(builder, GROVEDANCER, library=["forest"])
        before = life(game)
        game.state.event_batch += 1
        move_object(game.state, game.state.players[0].library[0], Zone.EXILE, cause="test")
        settle(game)
        assert life(game) == before


class TestOneOrMore:
    def test_three_lands_milled_together_fire_once(self, builder):
        game, _ = board(builder, SOWER, library=["forest"] * 3)
        before = life(game)
        mill(game, 0, 3)
        settle(game)
        assert life(game) == before + 1

    def test_the_per_card_form_fires_for_each(self, builder):
        """The counterfactual: Skola Grovedancer's "a land card"."""
        game, _ = board(builder, GROVEDANCER, library=["forest"] * 3)
        before = life(game)
        mill(game, 0, 3)
        settle(game)
        assert life(game) == before + 3

    def test_a_nonland_first_does_not_spend_the_group(self, builder):
        """The filter is asked per card before the group is spent."""
        game, _ = board(builder, SOWER, library=[BEAR, "forest"])
        before = life(game)
        mill(game, 0, 2)
        settle(game)
        assert life(game) == before + 1

    def test_two_separate_mills_fire_twice(self, builder):
        """Not a per-turn cap: a second, separate group fires again."""
        game, _ = board(builder, SOWER, library=["forest", "forest"])
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 2


class TestFirstTimeEachTurn:
    def test_the_first_group_fires(self, builder):
        game, _ = board(builder, SENSATION, library=["forest", "forest"])
        before = life(game)
        mill(game, 0, 2)
        settle(game)
        assert life(game) == before + 1

    def test_a_second_group_the_same_turn_does_not(self, builder):
        game, _ = board(builder, SENSATION, library=["forest", "forest"])
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 1

    def test_a_nonland_group_first_leaves_the_first_time_unspent(self, builder):
        """The run is of groups holding a *land* card."""
        game, _ = board(builder, SENSATION, library=[BEAR, "forest"])
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 1

    def test_an_opponents_land_does_not_spend_it(self, builder):
        game, _ = board(builder, SENSATION, library=["forest"], theirs=["forest"])
        before = life(game)
        mill(game, 1, 1)
        settle(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 1

    def test_a_land_before_it_entered_was_the_first_time(self, builder):
        """The whole difference from `max_per_turn: 1`.

        A land milled before the enchantment existed already happened, and the
        printed ability is about the turn's first such move, not its own first
        firing. Both watchers arrive after the first mill; only the cap fires.
        """
        game = (
            builder(players=2)
            .hand(0, [SENSATION, CAPPED])
            .library(0, ["forest", "forest"] + ["island"] * 5)
            .build(advance=False)
        )
        mill(game, 0, 1)
        settle(game)
        for oid in list(game.state.players[0].hand):
            game.state.event_batch += 1
            move_object(game.state, oid, Zone.BATTLEFIELD, cause="test")
        sensation = only_oid(game, SENSATION)
        capped = only_oid(game, CAPPED)
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 1
        fired = {
            e.source for e in game.state.events if e.type == "ability_triggered"
        }
        assert capped in fired
        assert sensation not in fired

    def test_it_fires_again_next_turn(self, builder):
        game, _ = board(builder, SENSATION, library=["forest", "forest"])
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        game.state.turn_ledger.clear()
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 2


class TestFromZones:
    def test_a_milled_creature_triggers(self, builder):
        game, _ = board(builder, KONRAD, library=[BEAR])
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 1

    def test_any_graveyard_with_controller_any(self, builder):
        game, _ = board(builder, KONRAD, theirs=[BEAR])
        before = life(game)
        mill(game, 1, 1)
        settle(game)
        assert life(game) == before + 1

    def test_a_creature_dying_does_not(self, builder):
        """"Other than the battlefield": a death is `dies`, not this."""
        game, _ = board(builder, KONRAD, battlefield=[BEAR])
        before = life(game)
        to_graveyard(game, only_oid(game, BEAR), cause="destroyed")
        settle(game)
        assert life(game) == before


class TestThem:
    def test_one_of_the_milled_creatures_comes_back(self, builder):
        game, _ = board(builder, REAVER, library=[BEAR, "forest", BEAR])
        mill(game, 0, 3)
        settle(game)
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS
        offered = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
        assert len(offered) == 2, "both milled Bears, and nothing else, are 'them'"
        game.apply(offered[0])
        bears = [
            oid for oid in game.state.battlefield
            if game.state.objects[oid].def_id == BEAR
        ]
        assert len(bears) == 1

    def test_an_earlier_creature_in_the_graveyard_is_not_one_of_them(self, builder):
        """"Them" is this group, not every creature card in the yard.

        `{"zone": "graveyard", "types": ["Creature"]}` is the near miss, and
        it would offer the Bear that was already there as well.
        """
        game = (
            builder(players=2)
            .battlefield(0, [REAVER])
            .graveyard(0, [BEAR])
            .library(0, [BEAR] + ["island"] * 5)
            .build(advance=False)
        )
        earlier = game.state.players[0].graveyard[0]
        mill(game, 0, 1)
        settle(game)
        # One candidate is chosen without asking; either way, it is the new one.
        if game.pending() is not None and game.pending().kind is DecisionKind.CHOOSE_OBJECTS:
            offered = [a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE]
            assert len(offered) == 1
            game.apply(offered[0])
        assert game.state.objects[earlier].zone is Zone.GRAVEYARD
        assert sum(
            1 for oid in game.state.battlefield if game.state.objects[oid].def_id == BEAR
        ) == 1

    def test_a_discarded_creature_is_not_from_the_library(self, builder):
        game, _ = board(builder, REAVER, hand=[BEAR])
        to_graveyard(game, game.state.players[0].hand[0], cause="discard")
        assert not game.state.pending_triggers


class TestItself:
    def test_this_card_milled_triggers_from_the_graveyard(self, builder):
        game = (
            builder(players=2)
            .library(0, [WURM] + ["island"] * 5)
            .build(advance=False)
        )
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before + 1

    def test_another_card_does_not(self, builder):
        game = (
            builder(players=2)
            .graveyard(0, [WURM])
            .library(0, ["forest"] + ["island"] * 5)
            .build(advance=False)
        )
        before = life(game)
        mill(game, 0, 1)
        settle(game)
        assert life(game) == before

    def test_a_permanent_dying_hears_its_own_arrival(self, builder):
        """603.10a: the move is a leaves-the-battlefield event."""
        game, oid = board(builder, LAND_CREATURE)
        before = life(game)
        to_graveyard(game, oid, cause="destroyed")
        settle(game)
        assert life(game) == before + 1


class TestTheLoaderRefuses:
    def _card(self, trigger: dict) -> CardModel:
        return CardModel.model_validate({
            "id": "t_probe", "name": "Probe", "oracle_text": "x", "types": ["Enchantment"],
            "abilities": [{
                "kind": "triggered", "text": "x", "trigger": trigger,
                "effects": [{"op": "gain_life", "player": "you", "amount": {"const": 1}}],
            }],
        })

    def test_nth_without_batched(self):
        with pytest.raises(DslError, match="batched"):
            compile_card(self._card(
                {"event": "put_into_graveyard", "filter": {"types": ["Land"]}, "nth": 1}
            ))

    def test_nth_with_a_board_filter(self):
        with pytest.raises(DslError, match="printed faces"):
            compile_card(self._card({
                "event": "put_into_graveyard", "batched": True, "nth": 1,
                "filter": {"types": ["Land"], "tapped": True},
            }))

    def test_from_the_graveyard(self):
        with pytest.raises(DslError, match="from_zones"):
            compile_card(self._card(
                {"event": "put_into_graveyard", "from_zones": ["graveyard"]}
            ))

    def test_it_loads_with_every_other_zone(self):
        compile_card(self._card({
            "event": "put_into_graveyard",
            "from_zones": ["library", "hand", "stack", "exile", "command"],
        }))
