"""Untapping *other* permanents to pay for an ability.

    Halo Fountain — "{W}, {T}, Untap a tapped creature you control: Create a
    1/1 green and white Citizen creature token." / "{W}{W}, {T}, Untap two
    tapped creatures you control: Draw a card." / "{W}{W}{W}{W}{W}, {T}, Untap
    fifteen tapped creatures you control: You win the game."

`untap` was the only untapping a cost could do, and it is the `{Q}` symbol
(rule 107.6): it untaps the source and nothing else. Halo Fountain's cost
carries **both** — it taps *itself* with `{T}` and untaps *other* creatures — so
`tap: true` plus `untap: true` on one cost taps the Fountain, untaps the
Fountain, and touches no creature at all. The two halves have to name different
permanents.

Paying with the `untap` **op** instead is two failures at once, exactly as it
would be for `tap_permanents`: the untaps would land on resolution rather than
on activation, and the ability could be activated with no tapped creatures at
all. On this card that is not a rounding error, it is the whole card — Halo
Fountain is a combo engine whose only constraint is that the board must be bent
before it can be unbent, and a third line that reads "{W}{W}{W}{W}{W}, {T}: You
win the game" is not the card that was printed.

The mirror of `tap_permanents` in every respect, and the pool is where that
matters most: `tap_permanents` forces `tapped: False` into its selector because
"untapped" is in every printed line of *its* shape; this forces `tapped: True`
for the same reason, and for the same consequence if it did not — a cost that
could "untap" an already-untapped creature is free.
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.carddef import Cost
from automtg.engine.costs import can_pay
from automtg.engine.enums import ActionKind, DecisionKind
from automtg.engine.errors import DslError
from tests.conftest import only_oid

#: "{T}, Untap two tapped Bears you control: Draw a card." Halo Fountain's
#: second line with smaller numbers and the test pool's subtype — and it keeps
#: the `{T}`, because "taps itself, untaps others" is the shape the card is.
UNTAPPER = {
    "id": "t_untapper",
    "name": "Test Untapper",
    "oracle_text": "{T}, Untap two tapped Bears you control: Draw a card.",
    "mana_cost": "{2}{W}",
    "types": ["Creature"],
    "subtypes": ["Citizen"],
    "power": 2,
    "toughness": 2,
    "abilities": [
        {
            "kind": "activated",
            "text": "{T}, Untap two tapped Bears you control: Draw a card.",
            "cost": {
                "tap": True,
                "untap_permanents": {"subtypes": ["Bear"], "count": 2},
            },
            "effects": [{"op": "draw", "player": "you", "amount": {"const": 1}}],
        }
    ],
}

#: The untap half alone, for the pool questions — the `{T}` is a separate cost
#: and answering "is the pool big enough" through it would test two things.
COST = {"untap_permanents": {"subtypes": ["Bear"], "count": 2}}


def board(builder, *, bears: int, tapped: bool = True, **kwargs):
    """The Untapper and `bears` Bears, tapped unless a test says otherwise."""
    game = (
        builder(players=2)
        .battlefield(0, ["t_untapper"])
        .battlefield(0, ["t_bear"] * bears, tapped=tapped, **kwargs)
        .library(0, ["island"] * 20)
        .build()
    )
    return game, only_oid(game, "t_untapper")


def bear_oids(game, *, tapped: bool):
    state = game.state
    return [
        oid
        for oid in state.battlefield
        if state.objects[oid].def_id == "t_bear" and state.objects[oid].tapped is tapped
    ]


class TestWhatItCosts:
    def test_enough_tapped_permanents_makes_it_payable(self, builder):
        game, source = board(builder, bears=2)
        assert can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_one_short_makes_it_unpayable(self, builder):
        """Not payable-and-discounted. A cost of fifteen that settles for
        fourteen is a cheaper card than the printed one — and on Halo Fountain
        the cheaper card simply wins the game."""
        game, source = board(builder, bears=1)
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_the_boundary_is_exactly_the_count(self, builder):
        """One below refuses, exactly the count pays. Asserted as a pair so an
        off-by-one cannot pass by moving the whole line."""
        short, source = board(builder, bears=1)
        assert not can_pay(short.state, 0, Cost.from_spec(COST), source)
        exact, source = board(builder, bears=2)
        assert can_pay(exact.state, 0, Cost.from_spec(COST), source)

    def test_untapped_permanents_do_not_count(self, builder):
        """"…two **tapped** creatures you control". This is the mirror of
        `tap_permanents`' forced `tapped: False`, and without it the cost is
        free on any board with two Bears standing up."""
        game, source = board(builder, bears=2, tapped=False)
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_a_half_tapped_board_counts_only_the_tapped_half(self, builder):
        """Three Bears, one of them tapped, is one payment short of two."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_untapper"])
            .battlefield(0, ["t_bear"], tapped=True)
            .battlefield(0, ["t_bear", "t_bear"], tapped=False)
            .library(0, ["island"] * 20)
            .build()
        )
        source = only_oid(game, "t_untapper")
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_the_selector_narrows_it(self, builder):
        """The printed clause names what may be untapped; another creature type
        does not pay."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_untapper"])
            .battlefield(0, ["t_flyer", "t_flyer"], tapped=True)
            .library(0, ["island"] * 20)
            .build()
        )
        source = only_oid(game, "t_untapper")
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_it_does_not_reach_an_opponents_permanents(self, builder):
        """"…you control". `controller` defaults to "you", as it does for every
        other cost pool — and untapping an opponent's board is not a cost at
        all, it is a drawback they would thank you for."""
        game = (
            builder(players=2)
            .battlefield(0, ["t_untapper"])
            .battlefield(1, ["t_bear"] * 3, tapped=True)
            .library(0, ["island"] * 20)
            .build()
        )
        source = only_oid(game, "t_untapper")
        assert not can_pay(game.state, 0, Cost.from_spec(COST), source)

    def test_a_summoning_sick_permanent_still_pays(self, builder):
        """Rule 302.6 restricts the `{T}` symbol in a permanent's *own* cost;
        this reaches other permanents. `tap_permanents` reads the same way, and
        it matters here for a reason of the card's own: Halo Fountain's first
        line makes a Citizen, and a Citizen that arrived tapped is fodder for
        the second."""
        game, source = board(builder, bears=2, sick=True)
        assert can_pay(game.state, 0, Cost.from_spec(COST), source)


class TestPayingIt:
    def test_activating_untaps_the_permanents(self, builder):
        game, _ = board(builder, bears=2)
        assert len(bear_oids(game, tapped=True)) == 2

        action = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE), None
        )
        assert action is not None, "the ability was not offered"
        game.apply(action)

        # Charged at activation, before the ability has resolved -- which is the
        # difference between a cost and the `untap` op.
        assert len(bear_oids(game, tapped=False)) == 2
        assert bear_oids(game, tapped=True) == []

    def test_it_untaps_others_and_still_taps_the_source(self, builder):
        """The whole reason `untap: true` cannot stand in. `{T}` and this cost
        are on the same line and name different permanents: the Fountain ends
        tapped, the creatures end untapped."""
        game, source = board(builder, bears=2)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE))
        assert game.state.objects[source].tapped
        assert len(bear_oids(game, tapped=False)) == 2

    def test_the_player_picks_which_ones(self, builder):
        """Three tapped Bears and a cost of two is a real choice, so the
        payment stops and asks -- exactly two, out of the three that are
        tapped. With two on the board it is forced and never asked."""
        game, _ = board(builder, bears=3)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE))
        decision = game.pending()
        assert decision is not None
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.player == 0
        assert decision.min_count == decision.max_count == 2
        assert len(decision.options) == 3

    def test_it_untaps_exactly_the_count_and_no_more(self, builder):
        """Three tapped Bears, a cost of two: the third stays tapped. A cost
        that took everything it could would be a strictly better card."""
        game, _ = board(builder, bears=3)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE))
        for _ in range(2):
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
        assert len(bear_oids(game, tapped=False)) == 2
        assert len(bear_oids(game, tapped=True)) == 1

    def test_the_permanents_are_still_on_the_battlefield(self, builder):
        """Not sacrificed and not bounced -- they stay, which is what makes a
        cost of this shape repeatable."""
        game, _ = board(builder, bears=2)
        before = len(game.state.battlefield)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE))
        assert len(game.state.battlefield) == before

    def test_with_nothing_to_untap_the_ability_is_not_offered(self, builder):
        """The gating is the point of the card. Halo Fountain with an empty
        board must not be offered its win condition."""
        game, _ = board(builder, bears=0)
        assert not any(a.kind is ActionKind.ACTIVATE for a in game.legal_actions())

    def test_an_untapped_board_does_not_offer_it_either(self, builder):
        """Two Bears are present and neither is tapped: nothing to spend."""
        game, _ = board(builder, bears=2, tapped=False)
        assert not any(a.kind is ActionKind.ACTIVATE for a in game.legal_actions())

    def test_it_wears_off_the_moment_the_pool_is_spent(self, builder):
        """Activated once, the Bears are standing up, so the ability is not
        offered a second time. The cost is not repeatable on a board it has
        already unbent -- which is the mirror image of `tap_permanents`, whose
        payment lasts until the next untap step."""
        game, _ = board(builder, bears=2)
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE))
        assert not any(a.kind is ActionKind.ACTIVATE for a in game.legal_actions())


class TestItIsNotATapOnlyCost:
    def test_the_mana_solver_will_not_treat_it_as_a_source(self):
        """`is_tap_only` decides what the payment solver may tap for mana. Left
        out of that check, a permanent whose `{T}` also untaps two creatures
        would be tapped for mana by the solver and the untaps never charged."""
        assert not Cost.from_spec({"tap": True, **COST}).is_tap_only()
        assert Cost.from_spec({"tap": True}).is_tap_only()


class TestLoadTimeGuards:
    def test_the_card_loads_and_describes_itself(self):
        card = compile_card(CardModel.model_validate(UNTAPPER))
        assert "Untap 2 tapped permanents" in card.abilities[0].cost.describe()

    def test_a_bad_selector_key_is_refused(self):
        card = copy.deepcopy(UNTAPPER)
        card["abilities"][0]["cost"]["untap_permanents"] = {"subtyps": ["Bear"]}
        with pytest.raises(DslError, match="unknown selector keys"):
            compile_card(CardModel.model_validate(card))

    def test_spelling_tapped_is_refused_rather_than_overridden(self):
        """The pool forces `tapped: True`. A card that set it would read as a
        knob that works and would be silently ignored -- and a card that set it
        to `false` would be free."""
        card = copy.deepcopy(UNTAPPER)
        card["abilities"][0]["cost"]["untap_permanents"] = {
            "subtypes": ["Bear"],
            "count": 2,
            "tapped": False,
        }
        with pytest.raises(DslError, match="'tapped' is implied"):
            compile_card(CardModel.model_validate(card))

    def test_total_power_belongs_to_the_tap_half(self):
        """Crew is a printed sum and it taps. Nothing printed unbends a board by
        power, so `total_power` here is refused rather than loaded and ignored
        -- which would silently become "untap one creature"."""
        card = copy.deepcopy(UNTAPPER)
        card["abilities"][0]["cost"]["untap_permanents"] = {
            "types": ["Creature"],
            "total_power": 3,
        }
        with pytest.raises(DslError, match="'total_power' is crew's"):
            compile_card(CardModel.model_validate(card))

    def test_an_unknown_cost_key_is_still_a_load_error(self):
        """`CostModel` is `extra="forbid"`, which is what made this capability a
        load error rather than a silent no-op before it existed."""
        card = copy.deepcopy(UNTAPPER)
        card["abilities"][0]["cost"]["untap_permanent"] = {"count": 1}
        with pytest.raises(ValidationError):
            compile_card(CardModel.model_validate(card))
