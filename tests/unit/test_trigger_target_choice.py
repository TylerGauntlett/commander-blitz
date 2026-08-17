"""A triggered ability's controller chooses its targets (603.3d).

    Bojuka Bog — "When this land enters, exile target player's graveyard."

The targeting *selector* shipped already: `{"zone": "graveyard", "player":
{"target": "t1"}, "count": "all"}` empties exactly the named player's
graveyard, `tests/unit/test_target_player_zone.py` is the witness, and Bojuka
Bog compiled and passed all six authoring gates. What was wrong was **who got
named**.

`push_triggered_ability` enumerated with `limit=1` and took `options[0]`. For a
`kind: "player"` target the enumeration order is `state.alive()` — seat order —
so the ability always named seat 0, which is its own controller in every game
this card is played in. Bojuka Bog exiled its own graveyard, every time, and
nothing on the board said so: the trigger did fire, did resolve, and did exile
a graveyard.

That is not a weaker Bojuka Bog. It is a card nobody would play, and it was
indistinguishable from the real one at the level the gates can see.

Two structural consequences, both load-bearing:

**The push is a generator.** A choice made as the ability goes on the stack is
a decision like any other, so `drain_to_stack` and the `_advance` branch that
calls it became generators too.

**`pending_triggers` empties one trigger at a time**, after each lands on the
stack rather than all at once up front. Mid-drain the game is neither settled
nor finished, and clearing the list first made it look like both — "empty stack
and no pending triggers", which is how the engine's auto-pass check and most of
this suite ask whether the board has come to rest, was true while a player
still owed an answer.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Zone
from tests.conftest import only_oid

BOG = "t_bog"
BEAR = "t_bear"


def board(builder):
    """A graveyard on each side, so "whose" is a question with two answers."""
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 3)
        .graveyard(0, [BEAR] * 2)
        .graveyard(1, [BEAR] * 3)
        .hand(0, [BOG])
        .library(0, ["swamp"] * 20)
        .active(0)
        .build()
    )


def play_the_bog(game):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND
        and game.state.objects[a.source].def_id == BOG
    )
    game.apply(action)


def yard(game, pid: int) -> int:
    return len(game.state.players[pid].graveyard)


def settle(game, limit: int = 40) -> None:
    """Pass priority without ever answering a choice."""
    for _ in range(limit):
        decision = game.pending()
        if decision is None or decision.kind is not DecisionKind.PRIORITY:
            return
        game.apply(
            next(a for a in game.legal_actions() if a.kind is ActionKind.PASS)
        )


class TestTheChoiceIsAsked:
    def test_playing_it_stops_on_a_choice(self, builder):
        game = board(builder)
        play_the_bog(game)
        settle(game)

        decision = game.pending()
        assert decision is not None
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.player == 0, "the trigger's controller chooses"

    def test_both_players_are_offered(self, builder):
        game = board(builder)
        play_the_bog(game)
        settle(game)

        labels = [o.label for o in game.pending().options]
        assert len(labels) == 2, labels

    def test_the_ability_is_still_on_the_stack_underneath(self, builder):
        """The choice happens as it goes on the stack, not as it resolves."""
        game = board(builder)
        play_the_bog(game)
        settle(game)

        assert not game.state.stack, "it has not been pushed yet"
        assert game.state.pending_triggers, "and it has not been lost either"


class TestTheAnswerIsObeyed:
    def answer(self, game, seat: int) -> None:
        settle(game)
        decision = game.pending()
        index = next(
            i
            for i, option in enumerate(decision.options)
            if option.ref is not None and option.ref.id == seat
        )
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CHOOSE and a.choice == index
            )
        )
        settle(game)

    def test_choosing_the_opponent_exiles_theirs(self, builder):
        game = board(builder)
        play_the_bog(game)
        self.answer(game, 1)

        assert yard(game, 1) == 0
        assert yard(game, 0) == 2, "the controller's own graveyard is untouched"

    def test_choosing_yourself_exiles_your_own(self, builder):
        """The old behaviour, now reachable only by asking for it."""
        game = board(builder)
        play_the_bog(game)
        self.answer(game, 0)

        assert yard(game, 0) == 0
        assert yard(game, 1) == 3

    def test_the_cards_go_to_exile_and_not_nowhere(self, builder):
        game = board(builder)
        play_the_bog(game)
        self.answer(game, 1)

        exiled = [
            o
            for o in game.state.objects.values()
            if o.zone is Zone.EXILE and o.def_id == BEAR
        ]
        assert len(exiled) == 3


class TestWhatIsNotAsked:
    def kinds_seen(self, game, limit: int = 40) -> list:
        """Every decision the game stops on, answered passively."""
        seen = []
        for _ in range(limit):
            if not game.state.stack and not game.state.pending_triggers and seen:
                break
            decision = game.pending()
            if decision is None:
                break
            seen.append(decision.kind)
            if decision.kind is DecisionKind.PRIORITY:
                action = next(
                    a for a in game.legal_actions() if a.kind is ActionKind.PASS
                )
            else:
                action = game.legal_actions()[0]
            game.apply(action)
        return seen

    def test_a_trigger_with_no_targets_asks_nothing(self, builder):
        """Most triggers. A decision with one button is not a decision."""
        game = (
            builder(players=2)
            .battlefield(0, ["island"] * 3)  # t_etb_draw is {2}{U}
            .hand(0, ["t_etb_draw"])
            .library(0, ["island"] * 20)
            .active(0)
            .build()
        )
        hand = len(game.state.players[0].hand)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST
                and game.state.objects[a.source].def_id == "t_etb_draw"
            )
        )
        seen = self.kinds_seen(game)

        assert DecisionKind.CHOOSE_OBJECTS not in seen
        assert len(game.state.players[0].hand) == hand, "cast one, drew one"


class TestTheOptionsTrackTheBoard:
    def test_a_third_seat_is_a_third_option(self, builder):
        """Fixed at one was the bug; fixed at two would be the same bug with a
        larger constant."""
        game = (
            builder(players=3)
            .battlefield(0, ["swamp"] * 3)
            .graveyard(1, [BEAR])
            .graveyard(2, [BEAR])
            .hand(0, [BOG])
            .library(0, ["swamp"] * 20)
            .active(0)
            .build()
        )
        play_the_bog(game)
        settle(game)

        assert len(game.pending().options) == 3
        assert only_oid(game, BOG)
