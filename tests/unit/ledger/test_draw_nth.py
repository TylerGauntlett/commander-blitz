"""The *ordinal* of a draw, settled where the ability queues.

    Prince Imrahil the Fair — "Whenever you draw your second card each turn,
    create a 1/1 white Human Soldier creature token."

Forty-seven cards in the authoring queue print this clause, in all three
polarities: "you draw your second card", "an opponent draws their second card"
(Faerie Mastermind, Black Widow) and "a player draws their second card" (Ian
Malcolm). One question stands behind all of them, and it is not a question about
the board — it is a question about *which draw this was*.

The near miss is a plain `draw` trigger carrying the intervening-if
`{"cmp": "==", "left": {"cards_drawn_this_turn": "you"}, "right": {"const": 2}}`,
and it reads correctly at the moment it queues: `primitives.draw_cards` bumps the
tally immediately *before* it fires the event, so what `triggers._matches` reads
is exactly this draw's ordinal. It fails at the other end. Rule 603.4 re-checks
an intervening-if when the ability resolves, and `stack.resolve_top` does, by
which point the tally has moved:

    draw step               tally 1
    Divination resolves     tally 2  -> the trigger queues
                            tally 3
    the trigger resolves    re-check reads 3, skipped="condition"

So Prince Imrahil plus Brainstorm, Divination, or any multi-card draw — the
card's ordinary line of play, not an edge — silently makes no token. Written with
`>=` and `max_per_turn: 1` instead, the ability survives the re-check and is
right everywhere except one place: a permanent that enters *after* its
controller has already drawn two cards fires on the next draw, where the printed
card is silent for the rest of the turn. Both encodings are here, as
`t_nth_draw_condition` and `t_nth_draw_atleast`, and both failures are asserted
rather than described — they are what `nth` exists to avoid.

`nth` is therefore a restriction on the trigger and not a condition, which is the
same standing `counter` and `mana_ability` have: asked once, where the ability
queues, and never re-asked. `draw_cards` writes the ordinal onto the DRAW event
because that is the only place it is knowable — an ordinal is a fact about the
event, and the tally it came from is a fact about the turn.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.primitives import draw_cards
from tests.conftest import action_for_card, only_oid, pass_until

#: The shipped witness: nothing but this trigger, so anything wrong with the
#: ordinal is the whole card being wrong.
PRINCE = "prince_imrahil_the_fair"

#: The same trigger written the four other ways worth pinning.
OPPONENT = "t_nth_draw_opponent"  # "an opponent draws their second card"
ANY = "t_nth_draw_any"  # "a player draws their second card"
FIRST = "t_nth_draw_first"  # nth: 1, so the ordinal is an ordinal
CONDITION = "t_nth_draw_condition"  # the `== 2` intervening-if
AT_LEAST = "t_nth_draw_atleast"  # the `>= 2` plus `max_per_turn: 1`

DRAW_TWO = "t_draw_spell"  # {2}{U} sorcery, "Draw two cards."
TOKEN = "human_soldier_1_1_w"


def position(builder, card_id: str = PRINCE, *, drawn: int = 0, hand: list[str] | None = None):
    """``(game, oid)`` for the watcher on player 0's battlefield.

    ``drawn`` is applied *after* the position is built, so the watcher is
    already there to see those draws -- which is the case the card is about.
    Lands enough to cast a draw spell, and libraries for both players, because
    the opponent polarity needs somebody else to draw.
    """
    game = (
        builder(players=2)
        .battlefield(0, [card_id, "island", "island", "island"])
        .hand(0, list(hand or []))
        .library(0, ["island"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build()
    )
    draw_cards(game.state, 0, drawn)
    return game, only_oid(game, card_id, 0)


def queued(game) -> int:
    """How many triggers are waiting to go on the stack."""
    return len(game.state.pending_triggers)


def settle(game) -> None:
    """Put every queued trigger on the stack and resolve it."""
    game._advance()
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def tokens(game, pid: int = 0) -> int:
    return sum(1 for obj in game.state.battlefield_objects(pid) if obj.def_id == TOKEN)


def skipped_for_condition(game) -> int:
    """Abilities that resolved as nothing because 603.4 re-asked their if."""
    return sum(
        1
        for event in game.state.events
        if event.type == EventType.ABILITY_RESOLVED and event.data.get("skipped") == "condition"
    )


class TestOnlyTheSecondCardFiresIt:
    def test_the_first_draw_is_silent(self, builder):
        """The draw step's card, which is most turns' only one."""
        game, _ = position(builder, drawn=1)
        assert queued(game) == 0

    def test_the_second_draw_fires_it(self, builder):
        game, _ = position(builder, drawn=2)
        assert queued(game) == 1

    def test_the_third_and_fourth_draws_are_silent(self, builder):
        """"Your second card" is one card, not "two or more"."""
        game, _ = position(builder, drawn=4)
        assert queued(game) == 1, "one draw out of four was the second one"

    def test_a_failed_draw_does_not_advance_the_ordinal(self, builder):
        """Rule 104.3c: an empty library records the attempt and draws nothing.

        The boundary that a tally-based encoding also gets right and that an
        event-based one could easily get wrong, since `draw_cards` breaks out of
        its loop before firing anything.
        """
        game = (
            builder(players=2)
            .battlefield(0, [PRINCE])
            .library(0, ["island"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        draw_cards(game.state, 0, 3)
        assert game.state.players[0].attempted_draw_from_empty
        assert queued(game) == 0, "only one card was there to draw, so none was the second"


class TestADrawTwoSpellFiresItExactlyOnce:
    """The reader's failure, and the reason this is not a `condition`.

    The position is the one every game reaches: the draw step has happened, so
    the tally is at 1, and then a spell draws two. The first of those cards is
    the second card of the turn.
    """

    def test_the_token_is_created(self, builder):
        game, _ = position(builder, drawn=1, hand=[DRAW_TWO])
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_TWO))
        settle(game)
        assert game.state.cards_drawn_this_turn[0] == 3, "the spell drew two on top of the step's"
        assert tokens(game) == 1

    def test_nothing_was_skipped_on_resolution(self, builder):
        """603.4 has nothing to re-ask, which is the point of the restriction."""
        game, _ = position(builder, drawn=1, hand=[DRAW_TWO])
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_TWO))
        settle(game)
        assert skipped_for_condition(game) == 0

    def test_the_condition_encoding_makes_nothing(self, builder):
        """The same spell against the intervening-if, which is the bug.

        Not a hypothetical: this card loads, its trigger matches, and it resolves
        into silence. Nothing in the log says the token was owed.
        """
        game, _ = position(builder, CONDITION, drawn=1, hand=[DRAW_TWO])
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_TWO))
        settle(game)
        assert skipped_for_condition(game) == 1, "the re-check read a tally of 3"
        assert tokens(game) == 0, "Prince Imrahil plus Divination made no token"

    def test_the_at_least_encoding_survives_the_recheck(self, builder):
        """Why `>=` with `max_per_turn: 1` is tempting: here it is correct."""
        game, _ = position(builder, AT_LEAST, drawn=1, hand=[DRAW_TWO])
        game.apply(action_for_card(game, ActionKind.CAST, DRAW_TWO))
        settle(game)
        assert tokens(game) == 1


class TestEnteringAfterTwoDrawsIsSilent:
    """The other encoding's failure, and the reason `>=` was not shipped.

    The permanent is cast with the tally already at 2, so every remaining draw
    this turn is the third or later. The printed card does nothing for the rest
    of the turn.
    """

    def battlefield_after_two_draws(self, builder, card_id: str):
        game = (
            builder(players=2)
            .battlefield(0, ["plains", "island"])
            .hand(0, [card_id])
            .library(0, ["island"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build()
        )
        draw_cards(game.state, 0, 2)
        game.apply(action_for_card(game, ActionKind.CAST, card_id))
        pass_until(game, lambda g: not g.state.stack)
        assert only_oid(game, card_id, 0) is not None, "the watcher is on the battlefield"
        return game

    def test_the_ordinal_form_does_not_fire(self, builder):
        game = self.battlefield_after_two_draws(builder, PRINCE)
        draw_cards(game.state, 0, 1)
        settle(game)
        assert game.state.cards_drawn_this_turn[0] == 3
        assert tokens(game) == 0, "the third card is not your second card"

    def test_the_at_least_form_fires_and_is_wrong(self, builder):
        """The divergence that had this filed as a gap rather than shipped.

        No gate would catch it -- the card loads, plays, and makes a token the
        printed card does not. Pinned here so that the two encodings cannot
        quietly swap places later.
        """
        game = self.battlefield_after_two_draws(builder, AT_LEAST)
        draw_cards(game.state, 0, 1)
        settle(game)
        assert tokens(game) == 1, "the `>=` encoding makes a token off the third card"


class TestBothPolarities:
    def test_an_opponents_second_card_fires_the_opponent_watcher(self, builder):
        """Faerie Mastermind's half of the clause, on 47 queue entries' other side."""
        game, _ = position(builder, OPPONENT)
        draw_cards(game.state, 1, 2)
        assert queued(game) == 1
        settle(game)
        assert tokens(game, 0) == 1, "the watcher's controller gets the token"
        assert tokens(game, 1) == 0

    def test_your_own_second_card_leaves_it_silent(self, builder):
        game, _ = position(builder, OPPONENT, drawn=2)
        assert queued(game) == 0

    def test_the_you_watcher_ignores_an_opponents_draws(self, builder):
        game, _ = position(builder, PRINCE)
        draw_cards(game.state, 1, 2)
        assert queued(game) == 0

    @pytest.mark.parametrize("who", [0, 1])
    def test_any_player_fires_the_any_watcher(self, builder, who):
        """Ian Malcolm, Chaotician: "whenever a player draws their second card"."""
        game, _ = position(builder, ANY)
        draw_cards(game.state, who, 2)
        assert queued(game) == 1

    def test_the_any_watcher_fires_once_per_player(self, builder):
        game, _ = position(builder, ANY)
        draw_cards(game.state, 0, 2)
        draw_cards(game.state, 1, 2)
        assert queued(game) == 2, "each player has a second card of their own"


class TestTheOrdinalIsAnOrdinal:
    def test_nth_one_is_the_first_card(self, builder):
        """`nth` is a number, not a hardcoded "second"."""
        game, _ = position(builder, FIRST, drawn=1)
        assert queued(game) == 1

    def test_nth_one_does_not_fire_again(self, builder):
        game, _ = position(builder, FIRST, drawn=3)
        assert queued(game) == 1


class TestItIsScopedToTheTurn:
    def test_the_next_turn_fires_it_again(self, builder):
        """"Each turn" -- so the second card of every turn, not of the game.

        The tally clears in the untap step (`turn.py`) and the ordinal is read
        off it, so nothing separate has to be reset. Read on the opponent's turn
        because a player draws on other players' turns too.
        """
        game, _ = position(builder, drawn=2)
        settle(game)
        assert tokens(game) == 1
        pass_until(game, lambda g: g.state.turn == 2 and g.state.step is Step.PRECOMBAT_MAIN)
        assert game.state.cards_drawn_this_turn.get(0, 0) == 0
        draw_cards(game.state, 0, 2)
        settle(game)
        assert tokens(game) == 2, "the second card of the new turn is a second card too"


def watcher(**trigger) -> dict:
    """The card as raw JSON, for the load-time guards below."""
    return {
        "id": "t_nth_probe",
        "name": "Test Nth Probe",
        "oracle_text": "Whenever you draw your second card each turn, create a token.",
        "mana_cost": "{W}{U}",
        "types": ["Creature"],
        "subtypes": ["Noble"],
        "power": 2,
        "toughness": 2,
        "abilities": [
            {
                "kind": "triggered",
                "text": "Whenever you draw your second card each turn, create a token.",
                "trigger": {"event": "draw", "controller": "you", **trigger},
                "effects": [{"op": "create_token", "token": TOKEN}],
            }
        ],
    }


class TestItIsRefusedWhereItCannotApply:
    def test_the_draw_trigger_itself_loads(self):
        compile_card(CardModel.model_validate(watcher(nth=2)))

    def test_on_another_event_it_is_a_load_error(self):
        """Only `draw` carries an ordinal.

        The same precedent `not_cause`, `counter` and `mana_ability` set, and it
        matters more on a trigger than on a selector: a restriction that never
        applies is an ability that fires on *every* event of its kind, so a
        card written this way is strictly better than the printed one.
        """
        card = watcher(nth=2)
        card["abilities"][0]["trigger"]["event"] = "discard"
        with pytest.raises(DslError, match="only means anything on a draw or spell_cast trigger"):
            compile_card(CardModel.model_validate(card))

    @pytest.mark.parametrize("nth", [0, -1])
    def test_a_zeroth_card_is_a_load_error(self, nth):
        """Draws are ordinalled from 1, so this would never fire."""
        with pytest.raises(DslError, match="'nth' is an ordinal from 1"):
            compile_card(CardModel.model_validate(watcher(nth=nth)))

    def test_the_condition_form_still_loads(self):
        """`nth` narrows what a `draw` trigger can say; it removes nothing.

        Isperia's "whenever an opponent draws a card" carries no ordinal and must
        keep firing on every draw.
        """
        compile_card(CardModel.model_validate(watcher()))
