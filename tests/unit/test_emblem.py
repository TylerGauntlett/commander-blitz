"""Emblems (114): "Target opponent gets an emblem with 'Whenever a player draws a
card, you lose 2 life.'"

    Ob Nixilis Reignited, -8.

An emblem is an object in the **command zone** with abilities and no other
characteristics (114.1, 114.3), created by an effect and **owned by the player
who gets it** (114.2). Nothing removes one; its abilities work from the command
zone (114.4). Nothing in the DSL could say it, and each near miss is a different
card:

- `delayed_trigger` belongs to the *ability's controller*, so its "you" is Ob
  Nixilis's controller -- the emblem would drain the player who ultimated -- and
  it carries a duration where an emblem lasts the game.
- `grant_ability` hands an ability to a *permanent*, and it goes when the
  permanent does.

So an emblem is its own object. The quoted abilities are written under the
card's `emblems`, compiled by the loader into a `CardDef` of their own with
`active_zones` forced to the command zone, and the `emblem` op puts an object
pointing at that entry into the named player's command zone. `GameState.card_of`
returns the entry, so the existing trigger walk -- which already scans command
zones for Edgar Markov's eminence -- hears it, and "you" is the emblem's owner
because the owner is the controller of an object in the command zone.

**The source is usually gone.** An ultimate takes the last of the loyalty, so the
planeswalker dies to 704.5i before its ability resolves; the op reads the card id
the ability was put on the stack with, never the board.

The witness is `t_emblem_walker` (tests/data/emblem.cards.json): its -3 gives a
target opponent Ob Nixilis Reignited's emblem and takes its last loyalty doing
so, and its +1 gives its own controller the same emblem.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.primitives import draw_cards, give_emblem
from automtg.engine.serialize import card_view
from tests.conftest import only_oid, pass_until

WALKER = "t_emblem_walker"  # loyalty 3; +1 emblem to you, -3 emblem to target opponent
BEAR = "t_bear"  # {1}{G}, kept in hand so player 0 always has a real decision


def board(builder, *, emblems_for=()):
    """Player 0's main phase with the walker, and ``emblems_for`` already given.

    The bear in hand with Forests to cast it is what stops the engine's
    auto-pass rolling the game into somebody's draw step -- which, with a draw
    emblem on the table, would change life totals behind the test's back.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + [WALKER])
        .hand(0, [BEAR])
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )
    for pid in emblems_for:
        give_emblem(game.state, WALKER, 0, pid)
    return game, only_oid(game, WALKER, 0)


def settle(game):
    pass_until(game, lambda g: not g.state.pending_triggers and not g.state.stack)


def activate(game, walker: int, label: str):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.ACTIVATE and a.source == walker and label in (a.label or "")
    )
    game.apply(action)
    settle(game)


def life(game) -> list[int]:
    return [p.life for p in game.state.players]


class TestGettingOne:
    def test_the_target_opponent_gets_it_in_their_command_zone(self, builder):
        game, walker = board(builder)
        activate(game, walker, "Target opponent gets")
        state = game.state
        assert len(state.players[1].command) == 1
        assert state.players[0].command == []
        emblem = state.objects[state.players[1].command[0]]
        assert emblem.zone is Zone.COMMAND
        assert emblem.owner == 1 and emblem.controller == 1

    def test_it_arrives_although_the_ultimate_killed_its_source(self, builder):
        """704.5i puts the walker in the graveyard before its ability resolves."""
        game, walker = board(builder)
        activate(game, walker, "Target opponent gets")
        assert game.state.objects[walker].zone is Zone.GRAVEYARD
        assert len(game.state.players[1].command) == 1

    def test_you_get_it_in_your_command_zone(self, builder):
        game, walker = board(builder)
        activate(game, walker, "You get")
        assert len(game.state.players[0].command) == 1
        assert game.state.players[1].command == []

    def test_it_is_not_a_permanent_a_token_or_a_commander(self, builder):
        game, _ = board(builder, emblems_for=[1])
        oid = game.state.players[1].command[0]
        emblem = game.state.objects[oid]
        assert oid not in game.state.battlefield
        assert not emblem.is_token and not emblem.is_commander

    def test_it_is_never_offered_as_a_cast(self, builder):
        """The command-zone cast walk is for commanders, and an emblem is no card."""
        game, _ = board(builder, emblems_for=[0])
        oid = game.state.players[0].command[0]
        assert not [a for a in game.legal_actions() if a.source == oid]


class TestYouIsTheOwner:
    def test_the_owner_loses_when_the_other_player_draws(self, builder):
        game, _ = board(builder, emblems_for=[1])
        draw_cards(game.state, 0, 1)
        settle(game)
        assert life(game) == [40, 38]

    def test_the_owner_loses_when_they_draw_themselves(self, builder):
        """ "Whenever **a player** draws a card" -- the owner included."""
        game, _ = board(builder, emblems_for=[1])
        draw_cards(game.state, 1, 1)
        settle(game)
        assert life(game) == [40, 38]

    def test_each_card_drawn_is_a_trigger(self, builder):
        game, _ = board(builder, emblems_for=[1])
        draw_cards(game.state, 0, 3)
        settle(game)
        assert life(game) == [40, 34]

    def test_given_to_you_it_drains_you(self, builder):
        """The same emblem, the other owner: 'you' follows who got it, not who made it."""
        game, walker = board(builder)
        activate(game, walker, "You get")
        draw_cards(game.state, 1, 1)
        settle(game)
        assert life(game) == [38, 40]

    def test_two_emblems_are_two_triggers(self, builder):
        game, _ = board(builder, emblems_for=[1, 1])
        draw_cards(game.state, 0, 1)
        settle(game)
        assert life(game) == [40, 36]

    def test_without_one_a_draw_costs_nothing(self, builder):
        game, _ = board(builder)
        draw_cards(game.state, 0, 1)
        settle(game)
        assert life(game) == [40, 40]


class TestItLastsTheGame:
    def test_it_is_still_there_and_still_working_turns_later(self, builder):
        game, _ = board(builder, emblems_for=[1])
        start = game.state.turn
        pass_until(
            game, lambda g: g.state.turn == start + 2 and g.state.step is Step.PRECOMBAT_MAIN
        )
        assert len(game.state.players[1].command) == 1
        # Player 1's own draw step, then player 0's: two cards, both drain player 1.
        assert life(game) == [40, 36]


class TestHowItIsShown:
    def test_the_view_is_the_emblem_not_the_planeswalker(self, builder):
        game, _ = board(builder, emblems_for=[1])
        view = card_view(game.state, game.state.players[1].command[0])
        assert view["name"] == "Test Emblem Walker Emblem"
        assert view["type_line"] == "Emblem"
        assert view["oracle_text"] == "Whenever a player draws a card, you lose 2 life."
        assert view["types"] == []

    def test_the_snapshot_marks_it(self, builder):
        game, _ = board(builder, emblems_for=[1])
        oid = game.state.players[1].command[0]
        assert game.state.objects[oid].to_dict()["emblem"] == 0
        assert "emblem" not in game.state.objects[game.state.battlefield[0]].to_dict()


DRAIN = {
    "kind": "triggered",
    "text": "Whenever a player draws a card, you lose 2 life.",
    "trigger": {"event": "draw", "controller": "any"},
    "effects": [{"op": "lose_life", "player": "you", "amount": {"const": 2}}],
}


def walker(*, effect=None, emblems=None) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_x",
            "name": "X",
            "types": ["Planeswalker"],
            "loyalty": 3,
            "abilities": [
                {
                    "kind": "activated",
                    "text": "+1: emblem",
                    "cost": {"loyalty": 1},
                    "effects": [
                        effect
                        if effect is not None
                        else {"op": "emblem", "player": "you", "emblem": 0}
                    ],
                }
            ],
            "emblems": emblems if emblems is not None else [{"abilities": [DRAIN]}],
        }
    )


class TestTheLoader:
    def test_the_abilities_work_from_the_command_zone_without_being_told(self):
        card = compile_card(walker())
        (emblem,) = card.emblems
        assert emblem.abilities[0].active_zones == (Zone.COMMAND,)
        assert emblem.name == "X Emblem"
        assert not emblem.types

    def test_a_player_is_required(self):
        with pytest.raises(DslError, match="needs 'player'"):
            compile_card(walker(effect={"op": "emblem", "emblem": 0}))

    def test_an_index_is_required(self):
        with pytest.raises(DslError, match="needs 'emblem'"):
            compile_card(walker(effect={"op": "emblem", "player": "you"}))

    def test_an_emblem_the_card_does_not_write_is_refused(self):
        with pytest.raises(DslError, match="emblems\\[1\\]"):
            compile_card(walker(effect={"op": "emblem", "player": "you", "emblem": 1}))

    def test_an_emblem_nothing_gives_is_refused(self):
        with pytest.raises(DslError, match="no emblem op gives it"):
            compile_card(
                walker(
                    effect={"op": "gain_life", "player": "you", "amount": {"const": 1}}
                )
            )

    def test_an_empty_emblem_is_refused(self):
        with pytest.raises(DslError, match="no abilities"):
            compile_card(walker(emblems=[{"abilities": []}]))

    def test_a_static_emblem_ability_is_refused_rather_than_inert(self):
        static = {
            "kind": "static",
            "text": "Creatures you control get +1/+1.",
            "effect": "buff",
            "affects": {"types": ["Creature"], "controller": "you"},
            "power": 1,
            "toughness": 1,
        }
        with pytest.raises(DslError, match="only triggered abilities"):
            compile_card(walker(emblems=[{"abilities": [static]}]))

    def test_an_emblem_ability_elsewhere_than_the_command_zone_is_refused(self):
        with pytest.raises(DslError, match="command zone"):
            compile_card(
                walker(emblems=[{"abilities": [{**DRAIN, "active_zones": ["graveyard"]}]}])
            )
