"""`maximum_hand_size` — 402.2 and 514.1 with a number other than seven.

"**Your maximum hand size is twenty.**" (Twenty-Toed Toad.) Rule 402.2 makes
seven the *normal* maximum and lets effects change it; 514.1 has the active
player discard down to whatever it is at cleanup. Before this static the
cleanup step compared the hand with the constant `MAX_HAND_SIZE`, so the only
way to write the Toad was `no_hand_limit` -- a strictly better card that never
discards past twenty.

**Which effect wins.** A hand-size effect changes a game rule, not an object,
and 613.11 applies those in timestamp order, so the newest applicable one
decides: a set number arriving after Reliquary Tower's "no maximum" sets the
number, and a Tower arriving after it lifts the limit. The one-shot
`no_maximum_hand_size` (Sea Gate Restoration) takes its timestamp from when it
resolved. A shared timestamp goes to the larger maximum, no maximum being the
largest -- 613.7e's active-player choice is not modelled, and that reading never
discards a card the other would keep.

The claims below: the hand is trimmed to the set number, not seven; only the
named player is; it ends when the permanent leaves; the timestamp rule against
both `no_hand_limit` and the one-shot; the prompt names the number; and the
loader refuses the near misses.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.player import MAX_HAND_SIZE
from commanderblitz.engine.player_statics import maximum_hand_size, player_has_no_hand_limit
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until

NINE = "t_hand_size_nine"  # {0} artifact: your maximum hand size is nine
TWO = "t_opponents_hand_size_two"  # {0} artifact: each opponent's maximum hand size is two
SEA_GATE = "t_sea_gate"  # {U} sorcery: you have no maximum hand size for the rest of the game
TOWER = "reliquary_tower"
BEAR = "t_bear"


def position(builder, *, mine: int = 12, theirs: int = 12, board=(), extra=()):
    """Player 0 in their first main phase; ``mine`` and ``theirs`` are hand sizes.

    Every hand holds a Lightning Bolt, counted in the size, for
    `test_no_maximum_hand_size.position`'s reason: never cast, it keeps a
    priority window open in every step so passing stops where it is told to.
    ``board`` is player 0's permanents beside an Island and a Mountain, put
    there in order, so the later one has the newer timestamp. ``extra`` is
    player 0's castable cards, *not* counted in ``mine``.
    """
    return (
        builder(players=2)
        .hand(0, [*extra, "lightning_bolt", *[BEAR] * (mine - 1)])
        .hand(1, ["lightning_bolt", *[BEAR] * (theirs - 1)])
        .library(0, [BEAR] * 10)
        .library(1, [BEAR] * 10)
        .battlefield(0, ["island", "mountain", *board])
        .battlefield(1, ["mountain"])
        .active(0)
        .turn(1)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )


def cast(game, card_id: str) -> int:
    """Cast ``card_id`` from player 0's hand and pass until it has resolved."""
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    )
    game.apply(action)
    pass_until(game, lambda g: not g.state.stack)
    return action.source


def on_battlefield(game, card_id: str) -> int:
    return next(oid for oid in game.state.battlefield if game.state.objects[oid].def_id == card_id)


def until_turn(game, turn: int) -> None:
    pass_until(game, lambda g: g.state.turn == turn, limit=3000)


def hand_size(game, pid: int) -> int:
    return len(game.state.players[pid].hand)


class TestCleanupTrimsToTheNumber:
    def test_twelve_cards_go_down_to_nine(self, builder):
        game = position(builder, board=[NINE])
        assert maximum_hand_size(game.state, 0) == 9
        until_turn(game, 2)
        assert hand_size(game, 0) == 9, "514.1 discards to the set number, not seven"

    def test_nine_cards_are_kept(self, builder):
        """The boundary: a hand exactly at the maximum discards nothing."""
        game = position(builder, mine=9, board=[NINE])
        until_turn(game, 2)
        assert hand_size(game, 0) == 9

    def test_without_it_cleanup_discards_to_seven(self, builder):
        game = position(builder)
        until_turn(game, 2)
        assert hand_size(game, 0) == MAX_HAND_SIZE

    def test_the_prompt_names_the_number(self, builder):
        game = position(builder, board=[NINE])
        pass_until(game, lambda g: g.state.step is Step.CLEANUP and g.pending() is not None)
        decision = game.pending()
        assert decision.player == 0
        assert decision.prompt == "Discard down to 9 cards"

    def test_a_number_below_seven_bites_harder(self, builder):
        game = position(builder, board=[TWO])
        until_turn(game, 3)
        assert hand_size(game, 1) == 2, "twelve, plus their draw, down to two"


class TestOnlyThePlayerNamed:
    def test_the_opponent_still_discards_to_seven(self, builder):
        game = position(builder, board=[NINE])
        assert maximum_hand_size(game.state, 1) == MAX_HAND_SIZE
        until_turn(game, 3)
        assert hand_size(game, 1) == MAX_HAND_SIZE

    def test_an_opponent_static_spares_its_controller(self, builder):
        game = position(builder, board=[TWO])
        assert maximum_hand_size(game.state, 0) == MAX_HAND_SIZE
        assert maximum_hand_size(game.state, 1) == 2
        until_turn(game, 2)
        assert hand_size(game, 0) == MAX_HAND_SIZE


class TestItEndsWithThePermanent:
    def test_leaving_restores_seven(self, builder):
        game = position(builder, board=[NINE])
        move_object(game.state, on_battlefield(game, NINE), Zone.GRAVEYARD)
        assert maximum_hand_size(game.state, 0) == MAX_HAND_SIZE
        until_turn(game, 2)
        assert hand_size(game, 0) == MAX_HAND_SIZE


class TestTheNewestEffectWins:
    """613.11: rules-changing effects apply in timestamp order."""

    def test_a_number_after_a_tower_sets_the_number(self, builder):
        game = position(builder, board=[TOWER, NINE])
        assert maximum_hand_size(game.state, 0) == 9
        assert not player_has_no_hand_limit(game.state, 0)
        until_turn(game, 2)
        assert hand_size(game, 0) == 9

    def test_a_tower_after_a_number_lifts_the_limit(self, builder):
        game = position(builder, board=[NINE, TOWER])
        assert maximum_hand_size(game.state, 0) is None
        until_turn(game, 2)
        assert hand_size(game, 0) == 12

    def test_the_older_one_returns_when_the_newer_leaves(self, builder):
        game = position(builder, board=[NINE, TOWER])
        move_object(game.state, on_battlefield(game, TOWER), Zone.GRAVEYARD)
        assert maximum_hand_size(game.state, 0) == 9

    def test_a_one_shot_after_the_number_lifts_the_limit(self, builder):
        game = position(builder, board=[NINE], extra=[SEA_GATE])
        cast(game, SEA_GATE)
        assert maximum_hand_size(game.state, 0) is None
        until_turn(game, 2)
        assert hand_size(game, 0) == 12

    def test_a_number_after_the_one_shot_sets_the_number(self, builder):
        """Sea Gate Restoration's effect is for the rest of the game, but a
        newer effect is applied after it and overwrites it."""
        game = position(builder, extra=[SEA_GATE, NINE])
        cast(game, SEA_GATE)
        cast(game, NINE)
        assert game.state.players[0].has_no_maximum_hand_size
        assert maximum_hand_size(game.state, 0) == 9
        until_turn(game, 2)
        assert hand_size(game, 0) == 9

    def test_a_shared_timestamp_goes_to_the_larger_maximum(self, builder):
        game = position(builder, board=[NINE, TOWER])
        nine, tower = on_battlefield(game, NINE), on_battlefield(game, TOWER)
        game.state.objects[nine].timestamp = game.state.objects[tower].timestamp
        assert maximum_hand_size(game.state, 0) is None


def probe(static):
    return CardModel.model_validate(
        {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{0}",
            "types": ["Artifact"],
            "abilities": [{"kind": "static", **static}],
        }
    )


class TestTheLoaderGuardsIt:
    def test_the_printed_line_compiles(self):
        compile_card(probe({"effect": "maximum_hand_size", "affects_player": "you", "amount": 20}))

    def test_zero_compiles(self):
        compile_card(probe({"effect": "maximum_hand_size", "affects_player": "you", "amount": 0}))

    def test_amount_is_required(self):
        """Read as 0, a missing number would discard the whole hand."""
        with pytest.raises(DslError, match="maximum_hand_size needs an 'amount'"):
            compile_card(probe({"effect": "maximum_hand_size", "affects_player": "you"}))

    @pytest.mark.parametrize("amount", [-1, {"const": -1}])
    def test_a_negative_number_is_refused(self, amount):
        with pytest.raises(DslError, match="a maximum hand size is 0 or more"):
            compile_card(
                probe({"effect": "maximum_hand_size", "affects_player": "you", "amount": amount})
            )

    def test_affects_player_is_required(self):
        with pytest.raises(DslError, match="maximum_hand_size needs 'affects_player'"):
            compile_card(probe({"effect": "maximum_hand_size", "amount": 20}))

    def test_a_permanent_filter_is_refused(self):
        with pytest.raises(DslError, match="no 'affects'"):
            compile_card(
                probe(
                    {
                        "effect": "maximum_hand_size",
                        "affects_player": "you",
                        "amount": 20,
                        "affects": {"types": ["Creature"]},
                    }
                )
            )
