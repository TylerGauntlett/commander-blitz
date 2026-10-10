""""This ability costs {1} less to activate for each Vampire you control."

    Voldaren Estate — "{5}, {T}: Create a Blood token. This ability costs {1}
    less to activate for each Vampire you control."

Two cost reductions already existed and neither could reach an activated
ability. A card's own `cost_reduction` is Ghalta's "**this spell** costs {X}
less", and the `spell_cost_reduction` static is Warden of Evos Isle discounting
somebody else's spell — both read only from the cast path, through
`cost_reduction.cost_reduction`. An activated ability's `cost.mana` was the literal string
written on the card, at every board state.

`Cost.mana_reduction` takes the same `{"count": {filter}}` shape the card-level
field does, so the two cannot drift in what "for each" means, and it is applied
by `costs.ability_mana`.

**Generic only, clamped at zero.** "Costs {1} less" never reaches through the
generic part into the coloured pips, which is both what the rules say and the
only thing the payment solver could act on.

**One helper, two callers.** `can_pay` and `pay` both go through
`ability_mana`, because an ability offered at the reduced price and then charged
the printed one would strand the payment mid-activation — the same care
`life_cost`, `mana_produced` and `mana_options_of` already take, and the failure
each of them exists to prevent.
"""

from __future__ import annotations

from commanderblitz.engine.costs import ability_mana, can_pay
from tests.conftest import oids_of

SCALER = "t_scaling_ability"  # {5}, {T}: draw; {1} less per Vampire
VAMPIRE = "vampire_of_the_dire_moon"
BEAR = "t_bear"


def board(builder, *others, lands: int = 5):
    return (
        builder(players=2)
        .battlefield(0, [SCALER, *(["swamp"] * lands), *others])
        .library(0, ["swamp"] * 20)
        .build()
    )


def price(game) -> int:
    oid = oids_of(game, SCALER)[0]
    cost = game.state.card(oid).abilities[0].cost
    return ability_mana(game.state, 0, cost).total


class TestThePriceFollowsTheBoard:
    def test_no_vampires_is_the_printed_cost(self, builder):
        game = board(builder)
        assert price(game) == 5

    def test_each_vampire_takes_one_off(self, builder):
        game = board(builder, VAMPIRE)
        assert price(game) == 4

    def test_two_vampires_take_two_off(self, builder):
        game = board(builder, VAMPIRE, VAMPIRE)
        assert price(game) == 3

    def test_a_non_vampire_takes_nothing_off(self, builder):
        game = board(builder, BEAR)
        assert price(game) == 5

    def test_an_opponents_vampire_does_not_count(self, builder):
        """"…each Vampire **you** control."""
        game = (
            builder(players=2)
            .battlefield(0, [SCALER, *(["swamp"] * 5)])
            .battlefield(1, [VAMPIRE])
            .build()
        )
        assert price(game) == 5

    def test_it_never_goes_below_zero(self, builder):
        game = board(builder, *([VAMPIRE] * 8))
        assert price(game) == 0


class TestLegalityAndPaymentAgree:
    def test_it_is_unaffordable_at_the_printed_price(self, builder):
        game = board(builder, lands=4)
        oid = oids_of(game, SCALER)[0]
        assert not can_pay(game.state, 0, game.state.card(oid).abilities[0].cost, oid)

    def test_one_vampire_brings_it_into_range(self, builder):
        """Four lands cannot pay {5}; with a Vampire out the price is {4}."""
        game = board(builder, VAMPIRE, lands=4)
        oid = oids_of(game, SCALER)[0]
        assert can_pay(game.state, 0, game.state.card(oid).abilities[0].cost, oid)

    def test_the_offer_and_the_charge_are_the_same_number(self, builder):
        """`can_pay` and `pay` read one helper, so they cannot disagree."""
        game = board(builder, VAMPIRE, VAMPIRE, lands=3)
        oid = oids_of(game, SCALER)[0]
        cost = game.state.card(oid).abilities[0].cost
        assert ability_mana(game.state, 0, cost).total == 3
        assert can_pay(game.state, 0, cost, oid)
