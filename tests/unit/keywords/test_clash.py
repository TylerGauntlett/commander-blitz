"""Clash — rule 701.23a, the first effect that compares two players' libraries.

    "Clash with an opponent. (Each of you reveals the top card of your library,
    then puts that card on the top or bottom. A player wins if their card had a
    higher mana value.)"

`reveal` exists, and it is not the missing piece. What is missing is the
**comparison**: every numeric leaf in the value language reads one board, and
`mana_value_of` takes a target or a snapshot, neither of which can name a card
sitting on top of somebody else's library. `top_of_library` comes closest and
reports a boolean about a filter, so it cannot yield a number to compare with —
let alone the two numbers this needs at once.

The outcome is a binding, `clash_won`, and the loader refuses either half
without the other for kicker's reason: a `clash` nothing reads reveals two cards
and does nothing, and a `clash_won` with no clash behind it reads 0 for ever.

The boundary worth pinning is the empty library. "Higher than each other card
revealed this way" is vacuously true against no card, so a real card beats an
empty deck and an empty deck beats nothing — which a `0` sentinel would get
backwards for a card that costs `{0}`.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from tests.conftest import action_for_card, find_action, pass_until

FOREST = "forest"       # mana value 0
BEAR = "t_bear"         # mana value 2
GIANT = "t_big"         # mana value 6


def position(builder, mine: list[str], theirs: list[str], players: int = 2):
    # `advance=False`: every assertion here is about the exact top of two
    # libraries, and advancing runs the engine's auto-pass, which rolls turns
    # forward and draws the cards under test when nobody has anything to do.
    return builder(players=players).library(0, mine).library(1, theirs).build(advance=False)


def run(game, *, bottom: bool = False, opponent: int = 0):
    """Drive the op, answering every "bottom it?" the same way. Returns the ctx."""
    ctx = EffectContext(state=game.state, controller=0)
    gen = OPS["clash"](ctx, {"op": "clash"})
    send = None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return ctx
        if decision.kind is DecisionKind.CHOOSE_PLAYER:
            send = [opponent]
        else:
            send = [0] if bottom else [1]


def pod(builder):
    """Three seats: the Forest opponent is winnable, the Giant one is not."""
    return (
        builder(players=3)
        .library(0, [BEAR])
        .library(1, [FOREST])
        .library(2, [GIANT])
        .build(advance=False)
    )


def library_ids(game, pid: int) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].library]


class TestWhoWins:
    def test_the_higher_mana_value_wins(self, builder):
        game = position(builder, [GIANT, FOREST], [BEAR, FOREST])
        assert run(game).bindings["clash_won"] == 1

    def test_the_lower_mana_value_loses(self, builder):
        game = position(builder, [BEAR, FOREST], [GIANT, FOREST])
        assert run(game).bindings["clash_won"] == 0

    def test_a_tie_is_not_a_win(self, builder):
        """"Higher than", strictly. Nobody wins a tied clash."""
        game = position(builder, [BEAR, FOREST], [BEAR, FOREST])
        assert run(game).bindings["clash_won"] == 0


class TestTheEmptyLibraryBoundary:
    def test_a_zero_cost_card_beats_an_empty_deck(self, builder):
        """The sentinel has to be below {0}, not equal to it."""
        game = position(builder, [FOREST], [])
        assert run(game).bindings["clash_won"] == 1

    def test_revealing_nothing_never_wins(self, builder):
        game = position(builder, [], [FOREST])
        assert run(game).bindings["clash_won"] == 0

    def test_two_empty_libraries_are_a_tie(self, builder):
        game = position(builder, [], [])
        assert run(game).bindings["clash_won"] == 0


class TestWhereTheCardsGo:
    def test_keeping_it_leaves_the_order_alone(self, builder):
        game = position(builder, [GIANT, FOREST, BEAR], [BEAR, FOREST])
        run(game, bottom=False)
        assert library_ids(game, 0) == [GIANT, FOREST, BEAR]
        assert library_ids(game, 1) == [BEAR, FOREST]

    def test_bottoming_moves_both_players_cards(self, builder):
        """Each player decides about their own card — so both answers land."""
        game = position(builder, [GIANT, FOREST, BEAR], [BEAR, FOREST])
        run(game, bottom=True)
        assert library_ids(game, 0) == [FOREST, BEAR, GIANT]
        assert library_ids(game, 1) == [FOREST, BEAR]

    def test_the_result_is_decided_before_anything_is_bottomed(self, builder):
        """Bottoming your own card must not forfeit the clash you just won."""
        game = position(builder, [GIANT, FOREST], [BEAR, FOREST])
        assert run(game, bottom=True).bindings["clash_won"] == 1


class TestWhoIsAsked:
    def test_each_player_answers_for_their_own_card(self, builder):
        game = position(builder, [GIANT, FOREST], [BEAR, FOREST])
        ctx = EffectContext(state=game.state, controller=0)
        gen = OPS["clash"](ctx, {"op": "clash"})
        asked, send = [], None
        while True:
            try:
                decision = gen.send(send)
            except StopIteration:
                break
            asked.append(decision)
            send = [1]
        assert [d.player for d in asked] == [0, 1], "you, then the opponent"

    def test_a_pod_asks_which_opponent_to_clash_with(self, builder):
        game = pod(builder)
        ctx = EffectContext(state=game.state, controller=0)
        gen = OPS["clash"](ctx, {"op": "clash"})
        first = next(gen)
        assert first.kind is DecisionKind.CHOOSE_PLAYER
        assert len(first.options) == 2

    def test_the_chosen_opponent_is_the_one_compared(self, builder):
        """Picking the seat with the small card is how a pod wins a clash."""
        game = pod(builder)
        assert run(game, opponent=0).bindings["clash_won"] == 1, "vs the Forest"
        game = pod(builder)
        assert run(game, opponent=1).bindings["clash_won"] == 0, "vs the Giant"


class TestThroughARealCard:
    def test_winning_the_clash_runs_the_if(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST])
            .hand(0, ["t_clasher"])
            .library(0, [GIANT, BEAR, BEAR])
            .library(1, [FOREST, FOREST])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_clasher"))
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.MAY
        )
        game.apply(find_action(game, ActionKind.NO))   # keep it on top
        pass_until(
            game, lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.MAY
        )
        game.apply(find_action(game, ActionKind.NO))   # the opponent keeps theirs
        pass_until(game, lambda g: len(g.state.players[0].hand) > 0)

        assert library_ids(game, 0) == [BEAR, BEAR], "the Giant was drawn"


IF_WON = {
    "op": "if",
    "condition": {"cmp": ">=", "left": {"binding": "clash_won"}, "right": {"const": 1}},
    "then": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
}


def spell(*effects) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_clash_probe",
            "name": "Clash Probe",
            "mana_cost": "{1}",
            "types": ["Sorcery"],
            "spell_effects": list(effects),
        }
    )


class TestTheLoaderGuards:
    def test_both_halves_together_load(self):
        compile_card(spell({"op": "clash"}, IF_WON))

    def test_a_clash_nobody_reads_is_refused(self):
        """"Clash with an opponent." on its own reveals two cards and stops."""
        with pytest.raises(DslError, match="clash_won"):
            compile_card(spell({"op": "clash"}))

    def test_reading_clash_won_without_clashing_is_refused(self):
        with pytest.raises(DslError, match="never clashes"):
            compile_card(spell(IF_WON))
