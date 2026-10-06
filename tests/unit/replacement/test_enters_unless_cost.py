""""As this land enters, you may pay 3 life. If you don't, it enters tapped."

Soporific Springs, the back face of Sink into Stupor, and the shock-land clause
generally. Steam Vents already ships in this pool with the sentence dropped, which
is the version this replaces: a land that always enters tapped is a strictly worse
card, and nothing on the board says so.

The engine had the tapped replacement and no way to put a price on avoiding it.
`unless_cost` is that price, and it takes a whole `Cost` node rather than a life
number, because the rest of the cycle pays with a sacrifice or a discard.

**Where the question is asked is the whole design.** 614 applies enters
replacements *inside* the zone change, and `move_object` is not a generator: it
cannot stop for a decision, and making it one would put a suspend point inside
every zone change in the engine. So the offer is made by whichever path is about
to put the permanent onto the battlefield -- `game._play_land` for a land drop,
`stack._place_after_resolution` for a permanent spell, both already generators --
and the answer is left on the object for the replacement to read a moment later.

That is not an approximation. Nobody receives priority between the question and
the arrival, so there is no window in which the permanent exists with the question
unanswered. It is the same argument `_play_land` already makes for writing
`showing_second_face` before the move rather than during it.

`TestTheOfferIsNotMadeWhenUnaffordable` is the boundary, and it is a real one:
118.4 forbids paying life you do not have, so a player at 2 would otherwise be
shown a question whose "yes" cannot be honoured.
"""

from __future__ import annotations

from automtg.engine.enums import ActionKind, DecisionKind, Step
from tests.conftest import pass_until

SPRINGS = "t_springs"  # "you may pay 3 life"
ALWAYS_TAPPED = "t_springs_always_tapped"  # the same land with the clause dropped


def position(builder, land: str, *, life: int | None = None):
    game = (
        builder(players=2)
        .battlefield(0, ["island"])
        .battlefield(1, ["plains"])
        .library(0, ["forest"] * 20)
        .hand(0, [land])
        .hand(1, ["t_plain_instant"])
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    if life is not None:
        game.state.players[0].life = life
    game._advance()
    return game


def play_the_land(game, land: str, *, pay: bool):
    action = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.PLAY_LAND and game.state.objects[a.source].def_id == land
    )
    oid = action.source
    game.apply(action)
    pending = game.pending()
    if pending is not None and pending.kind is DecisionKind.MAY:
        want = ActionKind.YES if pay else ActionKind.NO
        game.apply(next(a for a in game.legal_actions() if a.kind is want))
    return oid


def offered_a_choice(game) -> bool:
    pending = game.pending()
    return pending is not None and pending.kind is DecisionKind.MAY


class TestPayingTheCost:
    def test_the_land_enters_untapped(self, builder):
        game = position(builder, SPRINGS)
        oid = play_the_land(game, SPRINGS, pay=True)

        assert not game.state.objects[oid].tapped

    def test_and_the_life_is_actually_paid(self, builder):
        game = position(builder, SPRINGS)
        play_the_land(game, SPRINGS, pay=True)

        assert game.state.players[0].life == 37


class TestDecliningIt:
    def test_the_land_enters_tapped(self, builder):
        game = position(builder, SPRINGS)
        oid = play_the_land(game, SPRINGS, pay=False)

        assert game.state.objects[oid].tapped

    def test_and_no_life_is_paid(self, builder):
        game = position(builder, SPRINGS)
        play_the_land(game, SPRINGS, pay=False)

        assert game.state.players[0].life == 40


class TestTheQuestionIsAsked:
    def test_playing_it_offers_the_choice(self, builder):
        game = position(builder, SPRINGS)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND
            and game.state.objects[a.source].def_id == SPRINGS
        )
        game.apply(action)

        assert offered_a_choice(game)

    def test_a_land_with_the_clause_dropped_asks_nothing(self, builder):
        """The card that ships today, kept live: strictly worse and silent."""
        game = position(builder, ALWAYS_TAPPED)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND
            and game.state.objects[a.source].def_id == ALWAYS_TAPPED
        )
        game.apply(action)

        assert not offered_a_choice(game)

    def test_and_that_land_always_enters_tapped(self, builder):
        game = position(builder, ALWAYS_TAPPED)
        oid = play_the_land(game, ALWAYS_TAPPED, pay=True)

        assert game.state.objects[oid].tapped


class TestTheOfferIsNotMadeWhenUnaffordable:
    def test_a_player_at_two_life_is_not_asked(self, builder):
        """118.4 forbids paying life you do not have.

        Asking anyway would be a question whose "yes" cannot be honoured -- and
        the land would then enter untapped or not depending on how the failed
        payment was reported, which is a coin flip the printed card does not
        have.
        """
        game = position(builder, SPRINGS, life=2)
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.PLAY_LAND
            and game.state.objects[a.source].def_id == SPRINGS
        )
        game.apply(action)

        assert not offered_a_choice(game)

    def test_and_the_land_enters_tapped(self, builder):
        game = position(builder, SPRINGS, life=2)
        oid = play_the_land(game, SPRINGS, pay=True)

        assert game.state.objects[oid].tapped
        assert game.state.players[0].life == 2


class TestTheLandStillWorks:
    """The point of paying: the land is usable the turn it arrives.

    Asserted through `available_mana` rather than through `legal_actions`,
    because a plain `{T}: Add {U}` is never offered as a standalone action --
    the payment solver taps it, which is what `costs.offerable_mana_ability`
    says. "Can it be tapped" is therefore a question about the mana it adds to
    the total, and that is the question the card is about too.
    """

    def mana_after(self, builder, *, pay: bool) -> int:
        from automtg.engine.costs import available_mana

        game = position(builder, SPRINGS)
        play_the_land(game, SPRINGS, pay=pay)
        pass_until(
            game,
            lambda g: g.pending() is not None and g.pending().kind is DecisionKind.PRIORITY,
        )
        return available_mana(game.state, 0)

    def test_paying_leaves_the_land_producing_this_turn(self, builder):
        assert self.mana_after(builder, pay=True) == self.mana_after(builder, pay=False) + 1
