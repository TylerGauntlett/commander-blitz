"""Entering with additional counters: Oath of Gideon (614.1c).

    Oath of Gideon: "Each planeswalker you control enters with an additional
    loyalty counter on it."

A replacement on the **arrival** (614.1c): the planeswalker is never on the
battlefield without the extra counter, and nothing else about loyalty changes.

What was wrong without this: the nearest shape, `replace_counters` with
``counter: "loyalty"`` and ``counter_addend: 1``, replaces every *placement* of
a loyalty counter -- so it would also turn each +1 loyalty cost into +2, which
the printed card never does. `enters_tapped` is the only static about somebody
else's arrival, and it carries no counters. The new static is its shape with a
quantity, read in `zones._enter_battlefield` and put on with the arriving
card's own "enters with" counters as one placement (122.6), in the order 616.1
lets the controller take (`zones._entering_counters`).

Witness: Oath of Gideon. `t_oath` is its second line.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import DslError, compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.zones import move_object
from tests.conftest import action_for_card, only_oid, pass_until

OATH = "t_oath"
WALKER = "t_walker"  # {2}{B}, loyalty 4, "+1: gain 2 life"
BEAR = "t_bear"


def position(builder, *, oaths: int = 1, theirs=(), hand=(WALKER,)):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 6 + ["plains"] * 3 + [OATH] * oaths)
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .library(0, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def settle(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def cast_walker(game) -> int:
    game.apply(action_for_card(game, ActionKind.CAST, WALKER))
    settle(game)
    return only_oid(game, WALKER, 0)


class TestTheArrivalGetsOneMore:
    def test_a_cast_walker_enters_with_one_more(self, builder):
        game = position(builder)
        walker = cast_walker(game)
        assert game.state.objects[walker].counter("loyalty") == 5

    def test_without_the_oath_it_is_the_printed_number(self, builder):
        """The control."""
        game = position(builder, oaths=0)
        walker = cast_walker(game)
        assert game.state.objects[walker].counter("loyalty") == 4

    def test_put_onto_the_battlefield_it_still_applies(self, builder):
        """"Enters" is every arrival, not only a cast one."""
        game = position(builder)
        oid = next(
            o.oid for o in game.state.objects.values()
            if o.def_id == WALKER and o.zone is Zone.HAND
        )
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0)
        assert game.state.objects[oid].counter("loyalty") == 5

    def test_two_oaths_add_two(self, builder):
        game = position(builder, oaths=2)
        walker = cast_walker(game)
        assert game.state.objects[walker].counter("loyalty") == 6

    def test_nothing_is_queued(self, builder):
        """A replacement, not a trigger."""
        game = position(builder)
        game.apply(action_for_card(game, ActionKind.CAST, WALKER))
        pass_until(game, lambda g: not g.state.stack)
        walker = only_oid(game, WALKER, 0)
        assert game.state.objects[walker].counter("loyalty") == 5


class TestOnlyTheArrival:
    """The reason this is not `replace_counters` with an addend."""

    def test_a_plus_one_is_still_plus_one(self, builder):
        game = position(builder)
        walker = cast_walker(game)
        game.apply(
            next(
                a for a in game.legal_actions()
                if a.kind is ActionKind.ACTIVATE and a.source == walker
                and a.ability_index == 0
            )
        )
        assert game.state.objects[walker].counter("loyalty") == 6

    def test_a_creature_gets_nothing(self, builder):
        game = position(builder, hand=(BEAR,))
        bear = next(
            o.oid for o in game.state.objects.values()
            if o.def_id == BEAR and o.zone is Zone.HAND
        )
        move_object(game.state, bear, Zone.BATTLEFIELD, to_player=0)
        assert not game.state.objects[bear].counters

    def test_an_opponents_walker_gets_nothing(self, builder):
        """"you control"."""
        game = position(builder, theirs=[WALKER])
        theirs = only_oid(game, WALKER, 1)
        move_object(game.state, theirs, Zone.EXILE)
        move_object(game.state, theirs, Zone.BATTLEFIELD, to_player=1)
        assert game.state.objects[theirs].counter("loyalty") == 4


class TestWithCompleated:
    def test_the_controller_orders_all_three(self, builder):
        """3 loyalty, both {W/P} paid with life (two fewer each, so four).

        The starting loyalty (306.5b), the Oath and compleated are three
        replacements on the one arrival, and 616.1e-f lets the controller apply
        any applicable one, then any that is applicable *now*, until none is
        left. Compleated is not applicable to an arrival with no loyalty yet;
        after the Oath's one counter it is, and takes that one to zero; the
        printed three then land. Three -- the most any order leaves, which is
        the order a player picks (`zones._entering_counters`).

        It used to be one: compleated was pinned straight after the printed
        loyalty and the Oath after that, which is *an* order the controller
        may choose and not the best one."""
        game = position(builder, hand=("t_twice_compleated",))
        action = next(
            a for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.phyrexian == 2
            and game.state.objects[a.source].def_id == "t_twice_compleated"
        )
        game.apply(action)
        settle(game)
        assert game.state.objects[action.source].zone is Zone.BATTLEFIELD
        assert game.state.objects[action.source].counter("loyalty") == 3


class TestTheLoaderChecksIt:
    def _card(self, **static) -> CardModel:
        ability = {
            "kind": "static",
            "text": "Each planeswalker you control enters with an additional loyalty counter on it.",
            "effect": "enters_with_additional_counters",
            "affects": {"controller": "you", "types": ["Planeswalker"]},
            "counter": "loyalty",
            "amount": 1,
        }
        ability.update(static)
        ability = {k: v for k, v in ability.items() if v is not None}
        return CardModel.model_validate(
            {
                "id": "t_bad_oath",
                "name": "Test Bad Oath",
                "mana_cost": "{2}{W}",
                "types": ["Enchantment"],
                "oracle_text": ability["text"],
                "abilities": [ability],
            }
        )

    def test_the_form(self):
        compile_card(self._card())

    def test_affects_is_required(self):
        with pytest.raises(DslError, match="affects"):
            compile_card(self._card(affects=None))

    def test_counter_is_required(self):
        with pytest.raises(DslError, match="counter"):
            compile_card(self._card(counter=None))

    @pytest.mark.parametrize("amount", [None, 0])
    def test_amount_is_a_positive_number(self, amount):
        with pytest.raises(DslError, match="amount"):
            compile_card(self._card(amount=amount))
