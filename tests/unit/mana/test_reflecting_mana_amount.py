"""A reflecting mana ability whose size the board sets.

    Incubation Druid -- "{T}: Add one mana of any type that a land you control
    could produce. If this creature has a +1/+1 counter on it, add three mana of
    that type instead."

Two questions about the board in one line, and each already had an answer on its
own. *Which type* is `reflecting` + `any_type` (Reflecting Pool): the options
are the one-symbol tuples the lands you control could make. *How many* is
`amount` (Gyre Sage, Helga): a value expression `costs.mana_amount` reads at
activation and `mana_produced` multiplies the chosen option by. Rule 106.7 and
605.1a keep both of them inside a mana ability -- neither stops to ask anything,
both only look.

What was missing is the pair. The loader's reflecting branch set
`mana_amount = None`, so an `amount` beside `reflecting` loaded clean and was
never read: a Druid with an adapted body still tapped for one mana, which is a
different (and much worse) card. The near misses are both better cards:
`any_one_color` with the same amount offers all five colours off a board of
Forests, and an `if` on counters is refused inside a mana ability.

The amount is `1 + 2 * min(+1/+1 counters, 1)` -- one, or three with any
number of counters, never more.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import (
    activate_mana_ability,
    mana_amount,
    mana_options_of,
    mana_sources,
)
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX
from commanderblitz.engine.primitives import add_counters
from tests.conftest import only_oid

DRUID = "t_incubator"

AMOUNT = {
    "sum": [
        {"const": 1},
        {
            "times": [
                {"const": 2},
                {
                    "min": [
                        {"counters_on": {"counter": "+1/+1", "objects": {"self_only": True}}},
                        {"const": 1},
                    ]
                },
            ]
        },
    ]
}


def druid(builder, lands, counters: int = 0):
    """The Druid beside ``lands``, carrying ``counters`` +1/+1 counters."""
    game = builder(players=2).battlefield(0, [DRUID, *lands]).battlefield(1, []).build()
    oid = only_oid(game, DRUID)
    if counters:
        add_counters(game.state, oid, "+1/+1", counters)
        game.state.bump_chars()
    ability = game.state.card(oid).abilities[0]
    return game, oid, ability


def offered(game, oid) -> set[tuple[int, ...]]:
    source = next(s for s in mana_sources(game.state, 0) if s.oid == oid)
    return set(source.options)


def g(n: int) -> tuple[int, ...]:
    out = [0] * 6
    out[SYMBOL_INDEX["G"]] = n
    return tuple(out)


def c(n: int) -> tuple[int, ...]:
    out = [0] * 6
    out[SYMBOL_INDEX["C"]] = n
    return tuple(out)


class TestTheAmountIsRead:
    """The claim: the `amount` beside `reflecting` is no longer dropped."""

    def test_the_loader_keeps_it(self, builder):
        _game, _oid, ability = druid(builder, ["forest"])
        assert ability.mana_reflects is not None
        assert ability.mana_amount == AMOUNT

    def test_no_counter_taps_for_one(self, builder):
        game, oid, ability = druid(builder, ["forest"])
        assert mana_amount(game.state, oid, ability) == 1
        assert offered(game, oid) == {g(1)}

    def test_a_counter_taps_for_three(self, builder):
        game, oid, ability = druid(builder, ["forest"], counters=1)
        assert mana_amount(game.state, oid, ability) == 3
        assert offered(game, oid) == {g(3)}

    def test_more_counters_still_three(self, builder):
        """"Three mana instead", not three per counter -- adapted is 3 counters."""
        game, oid, ability = druid(builder, ["forest"], counters=3)
        assert mana_amount(game.state, oid, ability) == 3
        assert offered(game, oid) == {g(3)}

    def test_the_payment_adds_three(self, builder):
        """The offer and the payment both go through `mana_produced`."""
        game, oid, ability = druid(builder, ["forest"], counters=1)
        activate_mana_ability(game.state, oid, ability.index, 0)
        assert game.state.players[0].mana_pool.amounts[SYMBOL_INDEX["G"]] == 3
        assert game.state.players[0].mana_pool.total() == 3


class TestTheTypeIsStillTheBoards:
    """Scaling the size widens nothing about which types are on offer."""

    def test_all_three_of_one_type(self, builder):
        game, oid, _ = druid(builder, ["forest", "wastes"], counters=1)
        assert offered(game, oid) == {g(3), c(3)}

    def test_no_land_offers_nothing(self, builder):
        game, oid, ability = druid(builder, [], counters=1)
        assert mana_options_of(game.state, oid, ability) == ()

    def test_an_island_is_not_offered_off_forests(self, builder):
        """The `any_one_color` near miss would offer blue here."""
        game, oid, _ = druid(builder, ["forest"], counters=1)
        assert all(option[SYMBOL_INDEX["U"]] == 0 for option in offered(game, oid))


def _probe(amount) -> dict:
    return {
        "id": "t_incubator_probe",
        "name": "Probe",
        "types": ["Creature"],
        "power": 0,
        "toughness": 2,
        "abilities": [
            {
                "kind": "activated",
                "text": "{T}: Add mana.",
                "is_mana_ability": True,
                "cost": {"tap": True},
                "effects": [
                    {
                        "op": "add_mana",
                        "reflecting": {"zone": "battlefield", "controller": "you", "types": ["Land"]},
                        "any_type": True,
                        "amount": amount,
                    }
                ],
            }
        ],
    }


class TestTheLoaderValidatesTheAmount:
    """The same refusals every other mana `amount` gets."""

    def test_x_is_refused(self):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_probe("x")))

    def test_a_constant_is_kept(self):
        card = compile_card(CardModel.model_validate(_probe(2)))
        assert card.abilities[0].mana_amount == 2
