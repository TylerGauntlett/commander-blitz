"""Annihilator and channel: two more rows that needed no engine work.

**Annihilator** was routed as "`attacks` trigger; needs a sacrifice chosen by
the defending player" — and the second half already existed. `choose_objects`
has always taken a `chooser`, and `"owner"` is precisely "whoever owns the
permanent decides", which for `controller: "opponent"` is the defending player
choosing among their own things. The row named a requirement instead of
checking whether the selector language met it.

That detail is the whole card. An annihilator whose *controller* picked the
sacrifices would be strictly better than the printed one, and it is the kind of
wrong that a test asserting "two permanents died" would happily pass.

**Channel** is bloodrush's shape with a different effect on the end: an
activated ability offered from hand whose cost is `discard_self`. Nothing new,
and it is here because the census listed it separately from bloodrush as though
the two were different problems.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, only_oid, pass_until

ANNIHILATOR = "t_annihilator"  # 5/5, annihilator 2
CHANNELER = "t_channeler"  # {3}{G} 3/3; from hand: {1}{G}, discard it -> gain 3
BEAR = "t_bear"
WALL = "t_wall"


def settle(game, limit: int = 30) -> None:
    for _ in range(limit):
        decision = game.pending()
        if decision is not None and decision.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, decision))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            return
        if decision is None:
            game._advance()
        else:
            game.apply(_default_answer(game, decision))
    raise AssertionError("nothing settled")


class TestAnnihilator:
    def position(self, builder, defender_board=(BEAR, BEAR, WALL)):
        game = (
            builder(players=2)
            .battlefield(0, [ANNIHILATOR])
            .battlefield(1, list(defender_board))
            .build()
        )
        return game, only_oid(game, ANNIHILATOR, 0)

    def attack(self, game, oid: int) -> None:
        pass_until(
            game,
            lambda g: g.pending() and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
        )
        game.apply(
            find_action(
                game, ActionKind.ADD_ATTACKER, source=oid, targets=(TargetRef.player(1),)
            )
        )
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))

    def test_the_defending_player_chooses(self, builder):
        """The whole card. An annihilator whose controller picked would be
        strictly better than the printed one, and a test that only counted the
        dead would pass either way."""
        game, oid = self.position(builder)
        self.attack(game, oid)
        decision = game.pending()
        assert decision is not None
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.player == 1, "the defending player, not the attacker"

    def test_it_offers_only_the_defenders_permanents(self, builder):
        game, oid = self.position(builder)
        self.attack(game, oid)
        decision = game.pending()
        assert len(decision.options) == 3, "their three, and not the attacker"

    def test_two_permanents_go(self, builder):
        game, oid = self.position(builder)
        before = len(list(game.state.battlefield_objects(1)))
        self.attack(game, oid)
        settle(game)
        assert len(list(game.state.battlefield_objects(1))) == before - 2

    def test_it_takes_what_is_there_when_that_is_less(self, builder):
        """"Sacrifices two permanents" with one on the board takes the one."""
        game, oid = self.position(builder, defender_board=(BEAR,))
        self.attack(game, oid)
        settle(game)
        assert list(game.state.battlefield_objects(1)) == []

    def test_an_empty_board_is_not_a_crash(self, builder):
        game, oid = self.position(builder, defender_board=())
        self.attack(game, oid)
        settle(game)
        assert list(game.state.battlefield_objects(1)) == []


class TestChannel:
    def position(self, builder, lands=2):
        return (
            builder(players=2)
            .hand(0, [CHANNELER])
            .battlefield(0, ["forest"] * lands)
            .build()
        )

    def lines(self, game) -> list:
        return [a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE]

    def test_it_is_activatable_from_hand(self, builder):
        game = self.position(builder)
        assert self.lines(game)

    def test_it_does_what_it_says(self, builder):
        game = self.position(builder)
        before = game.state.players[0].life
        game.apply(self.lines(game)[0])
        settle(game)
        assert game.state.players[0].life == before + 3

    def test_without_the_mana_it_is_not_offered(self, builder):
        game = self.position(builder, lands=0)
        assert self.lines(game) == []

    def test_the_card_is_gone_afterwards(self, builder):
        """`discard_self` is the cost, and it is also what satisfies the
        loader's guard on abilities offered from hand."""
        game = self.position(builder)
        assert len(game.state.players[0].hand) == 1
        game.apply(self.lines(game)[0])
        settle(game)
        assert game.state.players[0].hand == []
