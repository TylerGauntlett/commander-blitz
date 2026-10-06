"""Entering with a *counted* number of additional counters: Giada (614.1c).

    Giada, Font of Hope: "Each other Angel you control enters with an
    additional +1/+1 counter on it for each Angel you already control."

Oath of Gideon's static (`enters_with_additional_counters`) with an amount that
is a `count` rather than a number. Still a replacement on the arrival (614.1c,
614.12): the Angel is never on the battlefield at its printed size, nothing
goes on the stack, and nothing can respond between the Angel arriving and its
counters.

What was wrong without this: the amount was a whole number only. The nearest
spelling, a `permanent_enters` trigger running `add_counters`, puts the Angel
down as its base size and grows it later, respondably -- a different card.

"Already" is the load-bearing word. By the time the replacement is applied the
arrival is in ``state.battlefield``, so a plain count would include it; and two
Angels entering in one event (one `create_token` op, one mass reanimation) must
not count each other. So the count leaves out the whole entering group,
`state.event_batch`, and a Giada in that group is not yet a source at all --
the printed rulings for the card say both.

Witness: Giada, Font of Hope, the Choir Practice deck's commander. `t_giada` is
the whole card.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from automtg.engine.zones import move_object
from tests.conftest import action_for_card, oids_of, only_oid, pass_until

GIADA = "t_giada"
ANGEL = "t_angel"  # {W} 1/1 Angel
SQUIRE = "t_squire"  # {W} 1/1 Human
PAIR = "t_angel_pair"  # instant: two 4/4 Angel tokens, one op
RETURN = "t_mass_return"  # sorcery: every creature card in your yard, at once
TOKEN = "angel_4_4_w_flying"


def position(builder, *, mine=(GIADA,), theirs=(), hand=(ANGEL,), yard=(), plains=4):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * plains + list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .graveyard(0, list(yard))
        .library(0, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def cast(game, card_id: str) -> None:
    game.apply(action_for_card(game, ActionKind.CAST, card_id))
    settle(game)


def plus(game, oid: int) -> int:
    return game.state.objects[oid].counter("+1/+1")


def from_hand(game, card_id: str) -> int:
    return next(
        o.oid for o in game.state.objects.values()
        if o.def_id == card_id and o.zone is Zone.HAND
    )


class TestOnePerAngelAlreadyThere:
    def test_giada_alone_gives_one(self, builder):
        """Giada is an Angel you already control -- "each *other* Angel" is
        about who gets the counters, not who is counted."""
        game = position(builder)
        cast(game, ANGEL)
        assert plus(game, only_oid(game, ANGEL, 0)) == 1

    def test_every_angel_already_there_counts(self, builder):
        game = position(builder, mine=(GIADA, ANGEL, ANGEL), hand=(ANGEL,))
        before = set(oids_of(game, ANGEL, 0))
        cast(game, ANGEL)
        (new,) = set(oids_of(game, ANGEL, 0)) - before
        assert plus(game, new) == 3

    def test_the_arrival_does_not_count_itself(self, builder):
        """The boundary: 1, not 2, with Giada the only Angel there."""
        game = position(builder)
        angel = from_hand(game, ANGEL)
        move_object(game.state, angel, Zone.BATTLEFIELD, to_player=0)
        assert plus(game, angel) == 1

    def test_only_angels_are_counted(self, builder):
        game = position(builder, mine=(GIADA, SQUIRE, SQUIRE))
        cast(game, ANGEL)
        assert plus(game, only_oid(game, ANGEL, 0)) == 1

    def test_only_your_angels_are_counted(self, builder):
        game = position(builder, theirs=(ANGEL, ANGEL))
        cast(game, ANGEL)
        assert plus(game, only_oid(game, ANGEL, 0)) == 1

    def test_nothing_is_queued(self, builder):
        """A replacement, not a trigger: the counter is there the moment the
        Angel is, with no trigger pending."""
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, ANGEL))
        pass_until(game, lambda g: not g.state.stack)
        assert not game.state.pending_triggers
        assert plus(game, only_oid(game, ANGEL, 0)) == 1


class TestWhoGetsThem:
    def test_a_non_angel_gets_nothing(self, builder):
        game = position(builder, hand=(SQUIRE,))
        cast(game, SQUIRE)
        assert not game.state.objects[only_oid(game, SQUIRE, 0)].counters

    def test_giada_herself_gets_nothing(self, builder):
        """"Each **other** Angel": entering onto a board of Angels, Giada is
        the source and not an object it affects."""
        game = position(builder, mine=(ANGEL, ANGEL), hand=(GIADA,))
        cast(game, GIADA)
        assert not game.state.objects[only_oid(game, GIADA, 0)].counters

    def test_an_opponents_angel_gets_nothing(self, builder):
        game = position(builder, theirs=(ANGEL,))
        theirs = only_oid(game, ANGEL, 1)
        move_object(game.state, theirs, Zone.EXILE)
        move_object(game.state, theirs, Zone.BATTLEFIELD, to_player=1)
        assert not game.state.objects[theirs].counters


class TestEnteringTogether:
    def test_two_tokens_from_one_effect_each_see_only_giada(self, builder):
        """One op is one event: neither token is an Angel the other's
        controller "already" controlled. 1 and 1, not 1 and 2."""
        game = position(builder, hand=(PAIR,))
        cast(game, PAIR)
        tokens = oids_of(game, TOKEN, 0)
        assert len(tokens) == 2
        assert [plus(game, t) for t in tokens] == [1, 1]

    def test_two_separate_events_do_see_each_other(self, builder):
        """The control: cast one at a time, the second counts the first."""
        game = position(builder, hand=(ANGEL, ANGEL))
        cast(game, ANGEL)
        cast(game, ANGEL)
        assert sorted(plus(game, oid) for oid in oids_of(game, ANGEL, 0)) == [1, 2]

    def test_giada_entering_alongside_an_angel_does_not_apply_to_it(self, builder):
        """614.12: Giada was not on the battlefield when the Angel's entry was
        decided, whichever order the engine happens to move them in."""
        game = position(builder, mine=(), hand=(RETURN,), yard=(GIADA, ANGEL))
        cast(game, RETURN)
        assert not game.state.objects[only_oid(game, ANGEL, 0)].counters
        assert not game.state.objects[only_oid(game, GIADA, 0)].counters

    def test_an_angel_made_while_a_spell_waited_counts_for_it(self, builder):
        """A resolving spell is its own event. Two Angel tokens made in response
        to an Angel spell are already there when it resolves: Giada plus two."""
        game = position(builder, hand=(ANGEL, PAIR))
        game.apply(action_for_card(game, ActionKind.CAST, ANGEL))
        game.apply(action_for_card(game, ActionKind.CAST, PAIR))
        settle(game)
        assert plus(game, only_oid(game, ANGEL, 0)) == 3


class TestWearingOff:
    def test_without_giada_an_angel_enters_as_printed(self, builder):
        game = position(builder, mine=(ANGEL,), hand=(ANGEL,))
        before = set(oids_of(game, ANGEL, 0))
        cast(game, ANGEL)
        (new,) = set(oids_of(game, ANGEL, 0)) - before
        assert not game.state.objects[new].counters

    def test_once_giada_has_left_it_stops(self, builder):
        game = position(builder)
        move_object(game.state, only_oid(game, GIADA, 0), Zone.GRAVEYARD)
        cast(game, ANGEL)
        assert not game.state.objects[only_oid(game, ANGEL, 0)].counters

    def test_counters_already_placed_stay(self, builder):
        """A replacement on the entering, not a continuous effect: the counter
        is the Angel's own once it has arrived."""
        game = position(builder)
        cast(game, ANGEL)
        move_object(game.state, only_oid(game, GIADA, 0), Zone.GRAVEYARD)
        assert plus(game, only_oid(game, ANGEL, 0)) == 1


class TestTheManaAbility:
    def test_it_pays_for_an_angel(self, builder):
        game = position(builder, plains=0)
        cast(game, ANGEL)
        assert game.state.objects[only_oid(game, ANGEL, 0)].zone is Zone.BATTLEFIELD
        assert game.state.objects[only_oid(game, GIADA, 0)].tapped

    def test_it_does_not_pay_for_anything_else(self, builder):
        game = position(builder, plains=0, hand=(SQUIRE,))
        assert not any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SQUIRE
            for a in game.legal_actions()
        )


class TestTheLoaderChecksIt:
    def _card(self, amount) -> CardModel:
        ability = {
            "kind": "static",
            "text": "Each other Angel you control enters with an additional +1/+1 counter on it for each Angel you already control.",
            "effect": "enters_with_additional_counters",
            "affects": {"controller": "you", "subtypes": ["Angel"]},
            "counter": "+1/+1",
            "amount": amount,
        }
        return CardModel.model_validate(
            {
                "id": "t_bad_giada",
                "name": "Test Bad Giada",
                "mana_cost": "{1}{W}",
                "types": ["Creature"],
                "subtypes": ["Angel"],
                "power": 2,
                "toughness": 2,
                "oracle_text": ability["text"],
                "abilities": [ability],
            }
        )

    def test_a_count_loads(self):
        compile_card(self._card({"count": {"controller": "you", "subtypes": ["Angel"]}}))

    @pytest.mark.parametrize(
        "amount",
        [
            {"count": {"controller": "you"}, "const": 1},
            {"times": [{"count": {"controller": "you"}}, {"const": 2}]},
            {"max_life_of": "each_opponent"},
        ],
    )
    def test_nothing_but_a_count(self, amount):
        with pytest.raises(DslError, match="amount"):
            compile_card(self._card(amount))

    def test_the_count_is_over_the_battlefield(self):
        with pytest.raises(DslError, match="battlefield"):
            compile_card(self._card({"count": {"zone": "graveyard", "types": ["Creature"]}}))

    def test_the_filter_is_checked(self):
        with pytest.raises(DslError):
            compile_card(self._card({"count": {"controller": "you", "no_such_key": True}}))
