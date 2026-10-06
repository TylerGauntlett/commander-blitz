"""Tribute (702.104): a choice that belongs to somebody else.

The census routes it as "`self_enters` with a choice belonging to an opponent;
`two_piles` proves the shape is reachable" — and it is more than reachable, it
is already spelled. `may` has taken a `player` since Fact or Fiction and an
`else` since the Karoo lands, so tribute is one `may` with both:

    may(player="opponent", effects=[counters], else=[the punishment])

The row cited `two_piles` as *evidence the shape exists*, which was true, and
then stopped short of checking whether `may` already had it.

Two things this test pins down, because both are the card rather than
decoration:

**The opponent is asked.** Tribute is a choice between two bad outcomes offered
to the player who does not want either. A version asking the controller is not
a weaker tribute — it is a strictly better card, and one that counted only the
counters would pass.

**Declining is not free.** The `else` is the whole tension. Without it the
opponent simply always says no and the card is a vanilla 2/2.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind
from tests.conftest import _default_answer, action_for_card, find_action, only_oid

TRIBUTER = "t_tributer"  # 2/2; tribute 2, else each opponent loses 3


def cast_tribute(builder, *, pay: bool):
    game = (
        builder(players=2).hand(0, [TRIBUTER]).battlefield(0, ["swamp"] * 4).build()
    )
    game.apply(action_for_card(game, ActionKind.CAST, TRIBUTER))
    asked: int | None = None
    for _ in range(20):
        decision = game.pending()
        if decision is not None and decision.kind is DecisionKind.MAY:
            asked = decision.player
            game.apply(find_action(game, ActionKind.YES if pay else ActionKind.NO))
            continue
        if decision is not None and decision.kind is not DecisionKind.PRIORITY:
            game.apply(_default_answer(game, decision))
            continue
        if not game.state.stack and not game.state.pending_triggers:
            break
        if decision is None:
            game._advance()
        else:
            game.apply(_default_answer(game, decision))
    return game, only_oid(game, TRIBUTER, 0), asked


class TestWhoDecides:
    def test_the_opponent_is_asked(self, builder):
        """A tribute the *controller* answers is not a weaker card, it is a
        strictly better one -- and a test counting only the counters would
        never notice."""
        _game, _oid, asked = cast_tribute(builder, pay=True)
        assert asked == 1


class TestPayingTribute:
    def test_it_arrives_bigger(self, builder):
        game, oid, _ = cast_tribute(builder, pay=True)
        assert game.state.objects[oid].counter("+1/+1") == 2

    def test_and_nothing_else_happens(self, builder):
        game, _oid, _ = cast_tribute(builder, pay=True)
        assert game.state.players[1].life == 40


class TestDecliningTribute:
    def test_it_arrives_small(self, builder):
        game, oid, _ = cast_tribute(builder, pay=False)
        assert game.state.objects[oid].counter("+1/+1") == 0

    def test_the_punishment_lands(self, builder):
        """The `else` is the whole tension. Without it the opponent always
        says no and the card is a vanilla 2/2."""
        game, _oid, _ = cast_tribute(builder, pay=False)
        assert game.state.players[1].life == 37

    def test_the_controller_is_not_punished(self, builder):
        game, _oid, _ = cast_tribute(builder, pay=False)
        assert game.state.players[0].life == 40


class TestTheCardUsesOnlyShippedVocabulary:
    def test_it_is_one_may_with_a_player_and_an_else(self, registry):
        card = registry.get(TRIBUTER)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        (may,) = ability.effects
        assert may["op"] == "may"
        assert may["player"] == "opponent"
        assert [e["op"] for e in may["effects"]] == ["add_counters"]
        assert [e["op"] for e in may["else"]] == ["lose_life"]
