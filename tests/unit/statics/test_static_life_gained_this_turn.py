""""You may cast this card from your graveyard if you gained life this turn."

Oathsworn Vampire. The permission is Gravecrawler's shape -- a
`cast_from_graveyard` static with ``active_zones: ["graveyard"]`` -- and its
condition asks the turn ledger how much life the card's owner has gained,
`{"cmp": ">", "left": {"life_gained_this_turn": "you"}, "right": {"const": 0}}`.
The leaf already existed on the effect side (Witch of the Moors's
intervening-if); a static could not read it, and the near misses are worse
cards: `graveyard_cost` is the permission with no condition, and a life total
compared with the starting one asks whether you are *up*, not whether you
gained (a player who gained 3 and lost 5 gained life this turn; 119.9).

A static condition is read continuously (611.3a), and a static inside the
characteristic pipeline is cached per `char_version`. `primitives.gain_life`
bumps that version as the life moves, *before* LIFE_GAINED reaches
`GameState._tally` and the ledger is written, so the fold bumps again after
writing -- otherwise an answer read between the two would outlive the gain
(`TestTheCacheSeesTheGain`). The tally is written only by that fold and emptied
only by the cleanup step, never by a layer, so reading it inside the pipeline
stays acyclic (ADR 0001).
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player_statics import own_graveyard_cast_permission
from commanderblitz.engine.primitives import gain_life, lose_life
from tests.conftest import only_oid, pass_until, pt, settle_to_priority

VAMPIRE = "t_lg_graveyard_vampire"  # Oathsworn Vampire's permission, {1}{B} 2/2
ANTHEM = "t_lg_anthem"  # as long as you gained life this turn, your creatures get +1/+1
BEAR = "t_bear"  # {1}{G} 2/2


def position(builder, *, mine=(), graveyard=(VAMPIRE,)):
    game = (
        builder(players=2)
        .active(0)
        .battlefield(0, ["swamp"] * 4 + list(mine))
        .battlefield(1, ["plains"])
        .graveyard(0, list(graveyard))
        # A land to play keeps seat 0 from auto-passing out of its own main
        # phase while it has nothing else to do.
        .hand(0, ["swamp"])
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def in_graveyard(game, card_id: str, seat: int = 0) -> int:
    found = [o for o in game.state.players[seat].graveyard if game.state.objects[o].def_id == card_id]
    assert len(found) == 1
    return found[0]


def casts(game, oid: int) -> list:
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


class TestTheCondition:
    def test_not_castable_before_any_gain(self, builder):
        """The control: without the condition this is `graveyard_cost`'s card."""
        game = position(builder)
        assert not casts(game, in_graveyard(game, VAMPIRE))

    def test_castable_once_you_gain_life(self, builder):
        game = position(builder)
        vampire = in_graveyard(game, VAMPIRE)
        gain_life(game.state, 0, 1)
        assert casts(game, vampire)

    def test_an_opponents_gain_does_not_count(self, builder):
        game = position(builder)
        gain_life(game.state, 1, 5)
        assert not casts(game, in_graveyard(game, VAMPIRE))

    def test_a_gain_that_was_then_lost_still_counts(self, builder):
        """Gained, not up: the ledger, not the life total."""
        game = position(builder)
        vampire = in_graveyard(game, VAMPIRE)
        gain_life(game.state, 0, 2)
        lose_life(game.state, 0, 5)
        assert casts(game, vampire)

    def test_the_cast_resolves_onto_the_battlefield(self, builder):
        game = position(builder)
        vampire = in_graveyard(game, VAMPIRE)
        gain_life(game.state, 0, 1)
        game.apply(casts(game, vampire)[0])
        settle_to_priority(game)
        while game.state.stack:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
            settle_to_priority(game)
        assert game.state.objects[vampire].zone is Zone.BATTLEFIELD


class TestItWearsOff:
    def test_the_next_turn_takes_the_permission_away(self, builder):
        """Asked of the permission itself: on seat 1's turn seat 0 could not
        cast a creature anyway, so the legal actions would prove nothing."""
        game = position(builder)
        vampire = in_graveyard(game, VAMPIRE)
        gain_life(game.state, 0, 1)
        assert own_graveyard_cast_permission(game.state, 0, vampire)
        pass_until(game, lambda g: g.state.active_player == 1)
        assert game.state.turn_ledger.life_gained == {}
        assert not own_graveyard_cast_permission(game.state, 0, vampire)


class TestTheCacheSeesTheGain:
    def test_an_anthem_switches_on_with_the_gain(self, builder):
        game = position(builder, mine=[ANTHEM, BEAR], graveyard=())
        bear = only_oid(game, BEAR, 0)
        assert pt(game, bear) == (2, 2)  # warm the cache
        gain_life(game.state, 0, 1)
        assert pt(game, bear) == (3, 3)

    def test_the_fold_bumps_after_writing(self, builder):
        """`gain_life` bumps before the ledger is written; the fold bumps again."""
        game = position(builder, mine=[ANTHEM, BEAR], graveyard=())
        state = game.state
        version = state.char_version
        gain_life(state, 0, 1)
        assert state.char_version > version + 1

    def test_and_off_with_the_turn(self, builder):
        game = position(builder, mine=[ANTHEM, BEAR], graveyard=())
        bear = only_oid(game, BEAR, 0)
        gain_life(game.state, 0, 1)
        assert pt(game, bear) == (3, 3)
        assert game.state.active_player == 0
        pass_until(game, lambda g: g.state.active_player == 1)
        assert pt(game, bear) == (2, 2)


def model(left) -> CardModel:
    text = "You may cast this card from your graveyard if you gained life this turn."
    return CardModel.model_validate(
        {
            "id": "x",
            "name": "X",
            "oracle_text": text,
            "mana_cost": "{1}{B}",
            "types": ["Creature"],
            "power": 2,
            "toughness": 2,
            "abilities": [
                {
                    "kind": "static",
                    "text": text,
                    "effect": "cast_from_graveyard",
                    "affects_player": "you",
                    "active_zones": ["graveyard"],
                    "condition": {"cmp": ">", "left": left, "right": {"const": 0}},
                }
            ],
        }
    )


class TestTheLoader:
    def test_the_shape_loads(self):
        compile_card(model({"life_gained_this_turn": "you"}))

    def test_an_unknown_player_spec_is_refused(self):
        with pytest.raises(DslError, match="life_gained_this_turn"):
            compile_card(model({"life_gained_this_turn": "active_player"}))

    def test_a_non_spec_is_refused(self):
        with pytest.raises(DslError, match="life_gained_this_turn"):
            compile_card(model({"life_gained_this_turn": {"player": "you"}}))
