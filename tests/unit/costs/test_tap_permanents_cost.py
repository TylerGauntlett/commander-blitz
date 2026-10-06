"""Tapping *other* permanents to pay for an ability.

    Captivating Vampire — "Tap five untapped Vampires you control: Gain control
    of target creature. It becomes a Vampire in addition to its other types."

`tap` was the only tapping a cost could do, and it is the `{T}` symbol: it taps
the source and nothing else. Paying this with the `tap` **op** instead would be
two failures at once — the taps would land on resolution rather than on
activation, and the ability could be activated with no untapped Vampires at all,
which makes it free.

What separates it from `sacrifice` and `return_to_hand`, whose shape it
otherwise copies exactly, is that the permanents *stay*. They untap on the next
untap step, so a cost of this shape is repeatable in a way neither of those is —
which is precisely why it has to be charged at activation and cannot be
approximated by anything cheaper.

**Summoning sickness does not apply.** Rule 302.6 restricts the `{T}` symbol in
a permanent's own cost; this taps other permanents. Captivating Vampire's ruling
says so explicitly, and getting it backwards would make the card unplayable on
the turn it matters.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.carddef import Cost
from automtg.engine.costs import can_pay
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import only_oid

#: "Tap two untapped Bears you control: Draw a card." Captivating Vampire's cost
#: with smaller numbers and the test pool's subtype.
TAPPER = {
    "id": "t_tapper",
    "name": "Test Tapper",
    "oracle_text": "Tap two untapped Bears you control: Draw a card.",
    "mana_cost": "{2}{B}",
    "types": ["Creature"],
    "subtypes": ["Vampire"],
    "power": 2,
    "toughness": 2,
    "abilities": [
        {
            "kind": "activated",
            "text": "Tap two untapped Bears you control: Draw a card.",
            "cost": {"tap_permanents": {"subtypes": ["Bear"], "count": 2}},
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
    ],
}

COST = {"tap_permanents": {"subtypes": ["Bear"], "count": 2}}


def board(builder, *, bears: int, **kwargs):
    game = (
        builder(players=2)
        .battlefield(0, ["t_tapper"])
        .battlefield(0, ["t_bear"] * bears, **kwargs)
        .library(0, ["island"] * 20)
        .build()
    )
    return game, only_oid(game, "t_tapper")


class TestWhatItCosts:
    def test_enough_untapped_permanents_makes_it_payable(self, builder):
        game, source = board(builder, bears=2)
        assert can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_one_short_makes_it_unpayable(self, builder):
        """Not payable-and-discounted. A cost of five that settles for four is a
        cheaper card than the printed one."""
        game, source = board(builder, bears=1)
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_already_tapped_permanents_do_not_count(self, builder):
        """"…five **untapped** Vampires". Without this the cost is free after
        the first activation, because the same permanents pay for it again."""
        game, source = board(builder, bears=2, tapped=True)
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_the_selector_narrows_it(self, builder):
        """The printed clause names a subtype; a creature of another does not pay."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_tapper", "t_flyer", "t_flyer"])
            .library(0, ["island"] * 20)
            .build()
        )
        source = only_oid(game, "t_tapper")
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_it_does_not_reach_an_opponents_permanents(self, builder):
        """`controller` defaults to "you", as it does for every other cost pool."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_tapper"])
            .battlefield(1, ["t_bear"] * 3)
            .library(0, ["island"] * 20)
            .build()
        )
        source = only_oid(game, "t_tapper")
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_a_summoning_sick_permanent_still_pays(self, builder):
        """Rule 302.6 is about the `{T}` symbol in a permanent's *own* cost.
        Captivating Vampire's ruling: a Vampire that just arrived may be tapped
        for it."""
        game, source = board(builder, bears=2, sick=True)
        assert can_pay(game.state, 0, Cost.from_spec(COST), source)


class TestPayingIt:
    def test_activating_taps_the_permanents(self, builder):
        game, _ = board(builder, bears=2)
        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE), None
        )
        assert action is not None, "the ability was not offered"
        game.apply(action)

        # Charged at activation, before the ability has resolved -- which is the
        # difference between a cost and the `tap` op.
        tapped = [
            oid
            for oid in game.state.battlefield
            if game.state.objects[oid].def_id == "t_bear" and game.state.objects[oid].tapped
        ]
        assert len(tapped) == 2

    def test_the_permanents_are_still_on_the_battlefield(self, builder):
        """Not sacrificed and not bounced -- they untap next turn, which is what
        makes this cost repeatable."""
        game, _ = board(builder, bears=2)
        before = len(game.state.battlefield)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE))
        assert len(game.state.battlefield) == before

    def test_with_nothing_to_tap_the_ability_is_not_offered(self, builder):
        game, _ = board(builder, bears=0)
        assert not any(a.kind is ActionKind.ACTIVATE for a in game.legal_actions())


class TestItIsNotATapOnlyCost:
    def test_the_mana_solver_will_not_treat_it_as_a_source(self):
        """`is_tap_only` decides what the payment solver may tap for mana. Left
        out of that check, a Springleaf Drum would make mana without ever
        tapping the creature it is supposed to."""
        assert not Cost.from_spec({"tap": True, **COST}).is_tap_only()
        assert Cost.from_spec({"tap": True}).is_tap_only()


class TestLoadTimeGuards:
    def test_the_card_loads_and_describes_itself(self):
        card = compile_card(CardModel.model_validate(TAPPER))
        assert "Tap 2 untapped permanents" in card.abilities[0].cost.describe()

    def test_a_bad_selector_key_is_refused(self):
        import copy

        card = copy.deepcopy(TAPPER)
        card["abilities"][0]["cost"]["tap_permanents"] = {"subtyps": ["Bear"]}
        with pytest.raises(DslError, match="unknown selector keys"):
            compile_card(CardModel.model_validate(card))

    def test_spelling_tapped_is_refused_rather_than_overridden(self):
        """The pool forces `tapped: False`. A card that sets it would read as a
        knob that works and would be silently ignored."""
        import copy

        card = copy.deepcopy(TAPPER)
        card["abilities"][0]["cost"]["tap_permanents"] = {
            "subtypes": ["Bear"],
            "count": 2,
            "tapped": True,
        }
        with pytest.raises(DslError, match="'tapped' is implied"):
            compile_card(CardModel.model_validate(card))
