"""Phyrexian mana: one printed symbol, two currencies.

Rule 107.4f: ``{U/P}`` can be paid with one blue mana **or** with 2 life, and
which one is the caster's choice, made while the cost is being paid. Without
that choice the symbol is not modelled at all -- narrowing it to ``{U}``, which
is what ``cards/proxy.py`` used to do, deletes the whole reason Gitaxian Probe is
played (a cantrip castable off no lands) and turns Gut Shot into a strictly worse
Shock. Widening it the other way, into an ordinary hybrid colour choice, would
make every card in the cycle cheaper than it is printed.

So the pip stays in the cost and the *line* is what varies: legality offers one
cast per number of pips bought with life, `ManaCost.paying_phyrexian` takes those
pips out of the price, and the life is charged alongside the mana. Rule 118.4
bounds it -- life may be paid down to exactly 0 and no further, the same boundary
`test_pay_life.py` pins for Adanto Vanguard -- so a player at 2 life may buy a
pip and a player at 1 may not.

Gitaxian Probe is the witness: the whole card is the choice. Gut Shot and Mental
Misstep are shipped alongside it, and Thundering Tanadon's ``{4}{G/P}{G/P}`` is
the two-pip case.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import ManaCost, ManaPool, Requirement, satisfies

ISLANDS = ["island"] * 4
MOUNTAINS = ["mountain"] * 4


def in_hand(game, card_id: str, pid: int = 0) -> int:
    """The oid of a card waiting in hand -- `conftest.only_oid` reads the
    battlefield, and every card here is measured before it is cast."""
    found = [
        oid for oid in game.state.players[pid].hand
        if game.state.objects[oid].def_id == card_id
    ]
    assert len(found) == 1, f"expected exactly one {card_id} in hand, found {len(found)}"
    return found[0]


def probe_at(builder, life: int, lands: list[str] | None = None):
    """Gitaxian Probe in hand, `life` life, and whatever lands are named."""
    game = (
        builder(players=2)
        .hand(0, ["gitaxian_probe"])
        .battlefield(0, lands or [])
        .life(0, life)
        .build()
    )
    return game, in_hand(game, "gitaxian_probe")


def cast_lines(game, oid: int) -> list[str]:
    """Every distinct way this card is offered, by its ungrouped label."""
    return sorted(
        {
            action.base_label
            for action in game.legal_actions()
            if action.kind is ActionKind.CAST and action.source == oid
        }
    )


def life_lines(game, oid: int) -> list[int]:
    """How many Phyrexian pips each offered line buys with life."""
    return sorted(
        {
            action.phyrexian
            for action in game.legal_actions()
            if action.kind is ActionKind.CAST and action.source == oid
        }
    )


class TestTheSymbolItself:
    """``{U/P}`` is one blue pip of mana value 1, whichever way it is paid."""

    def test_it_parses(self):
        cost = ManaCost.parse("{U/P}")
        assert len(cost.hybrid) == 1
        assert cost.hybrid[0].phyrexian
        assert cost.hybrid[0].life == 2

    def test_mana_value_is_one(self):
        # Load-bearing for Mental Misstep, which is legal against a one-drop.
        assert ManaCost.parse("{U/P}").mana_value() == 1
        assert ManaCost.parse("{2}{R/P}").mana_value() == 3

    def test_the_card_is_still_its_printed_colour(self):
        # 202.2: the colour comes from the cost's symbols, not from the mana
        # actually spent. A Gitaxian Probe cast for life is still a blue spell.
        assert {c.value for c in ManaCost.parse("{U/P}").colors} == {"U"}
        assert {c.value for c in ManaCost.parse("{G/P}{G/P}").colors} == {"G"}

    def test_the_life_half_is_not_a_colour(self):
        # The failure mode the old rejection existed to prevent: if P were read
        # as a symbol the pip would be payable off anything.
        assert not satisfies((0, 0, 0, 0, 0, 1), ManaCost.parse("{U/P}").with_x(0))

    def test_a_pip_still_in_the_cost_must_be_paid_with_mana(self):
        cost = ManaCost.parse("{U/P}").with_x(0)
        assert satisfies((0, 1, 0, 0, 0, 0), cost)
        assert not satisfies((0, 0, 0, 0, 0, 0), cost)

    def test_snow_is_still_refused(self):
        # The rejection this replaced named phyrexian *and* snow; only one of
        # them was implemented here.
        with pytest.raises(DslError):
            ManaCost.parse("{S}")


class TestBuyingPipsWithLife:
    """`paying_phyrexian` is the whole of 107.4f: the pip leaves, the life is owed."""

    def test_nothing_bought_is_the_printed_cost(self):
        cost = ManaCost.parse("{U/P}")
        remaining, owed = cost.paying_phyrexian(0)
        assert remaining is cost
        assert owed == 0

    def test_one_pip_bought_costs_two_life_and_no_mana(self):
        remaining, owed = ManaCost.parse("{U/P}").paying_phyrexian(1)
        assert owed == 2
        assert remaining.is_free()

    def test_the_rest_of_the_cost_survives(self):
        # Not an alternative cost: {2}{R/P} paid the life way is still a {2}
        # that a cost reduction can shrink and a tax can raise.
        remaining, owed = ManaCost.parse("{2}{R/P}").paying_phyrexian(1)
        assert owed == 2
        assert remaining.mana_value() == 2

    def test_each_pip_is_charged_separately(self):
        remaining, owed = ManaCost.parse("{4}{G/P}{G/P}").paying_phyrexian(2)
        assert owed == 4
        assert remaining.mana_value() == 4

    def test_the_printed_cost_never_changes(self):
        # `text` is what the card says and `mana_value` is read off the printed
        # cost, so neither moves because of how one casting was paid.
        cost = ManaCost.parse("{U/P}")
        remaining, _ = cost.paying_phyrexian(1)
        assert remaining.text == "{U/P}"
        assert cost.mana_value() == 1

    def test_buying_more_pips_than_are_printed_is_an_error(self):
        with pytest.raises(DslError):
            ManaCost.parse("{U/P}").paying_phyrexian(2)


class TestTheLinesLegalityOffers:
    """One cast per number of pips bought, and none the player cannot pay for."""

    def test_both_lines_are_offered_with_a_source_and_the_life(self, builder):
        game, oid = probe_at(builder, 20, ISLANDS)
        assert life_lines(game, oid) == [0, 1]
        assert any("paying 2 life" in label for label in cast_lines(game, oid))

    def test_with_no_blue_source_only_the_life_line_exists(self, builder):
        game, oid = probe_at(builder, 20, MOUNTAINS)
        assert life_lines(game, oid) == [1]

    def test_with_neither_the_card_is_not_castable(self, builder):
        game, oid = probe_at(builder, 1, MOUNTAINS)
        assert life_lines(game, oid) == []

    def test_the_mana_line_alone_when_life_is_short(self, builder):
        game, oid = probe_at(builder, 1, ISLANDS)
        assert life_lines(game, oid) == [0]

    def test_two_pips_offer_three_lines(self, builder):
        # {4}{G/P}{G/P}: all mana, one pip for 2 life, both for 4.
        game = (
            builder(players=2)
            .hand(0, ["thundering_tanadon"])
            .battlefield(0, ["forest"] * 6)
            .life(0, 20)
            .build()
        )
        oid = in_hand(game, "thundering_tanadon")
        assert life_lines(game, oid) == [0, 1, 2]


class TestTheBoundary:
    """118.4, the same rule `test_pay_life.py` pins: down to exactly 0, no further."""

    def test_exactly_two_life_can_buy_a_pip(self, builder):
        game, oid = probe_at(builder, 2, MOUNTAINS)
        assert life_lines(game, oid) == [1]

    def test_one_life_cannot(self, builder):
        game, oid = probe_at(builder, 1, MOUNTAINS)
        assert life_lines(game, oid) == []

    def test_two_pips_need_four_life_between_them(self, builder):
        def tanadon_at(life: int):
            game = (
                builder(players=2)
                .hand(0, ["thundering_tanadon"])
                .battlefield(0, ["mountain"] * 6)
                .life(0, life)
                .build()
            )
            return game, in_hand(game, "thundering_tanadon")

        # No green source, so both pips must go the life way or neither.
        game, oid = tanadon_at(3)
        assert life_lines(game, oid) == []
        game, oid = tanadon_at(4)
        assert life_lines(game, oid) == [2]


class TestPayingIt:
    """What the cast actually charges, on the board."""

    def cast(self, game, oid: int, phyrexian: int):
        action = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST and a.source == oid and a.phyrexian == phyrexian
        )
        game.apply(action)
        return game

    def test_the_all_life_cast_taps_nothing_and_costs_two_life(self, builder):
        # Gitaxian Probe's whole reason for existing: a free cantrip, paid for
        # out of a life total, off a board with no blue mana on it at all.
        game, oid = probe_at(builder, 20, MOUNTAINS)
        self.cast(game, oid, 1)
        assert game.state.players[0].life == 18
        assert not any(o.tapped for o in game.state.battlefield_objects(0))
        assert len(game.state.players[0].hand) == 1  # the card it drew

    def test_the_mana_cast_costs_no_life(self, builder):
        game, oid = probe_at(builder, 20, ISLANDS)
        self.cast(game, oid, 0)
        assert game.state.players[0].life == 20
        assert sum(1 for o in game.state.battlefield_objects(0) if o.tapped) == 1

    def test_a_player_may_pay_their_last_two_life(self, builder):
        # 118.4 again, from the paying side: the payment is legal and the loss
        # is a state-based action afterwards, not a reason to refuse the cost.
        game, oid = probe_at(builder, 2, MOUNTAINS)
        self.cast(game, oid, 1)
        assert game.state.players[0].life == 0

    def test_only_the_bought_pips_come_off_the_price(self, builder):
        # {4}{G/P}{G/P} with one pip bought: 4 generic and one green still owed,
        # which six Forests can pay -- and 2 life on top.
        game = (
            builder(players=2)
            .hand(0, ["thundering_tanadon"])
            .battlefield(0, ["forest"] * 6)
            .life(0, 20)
            .build()
        )
        oid = in_hand(game, "thundering_tanadon")
        self.cast(game, oid, 1)
        assert game.state.players[0].life == 18
        assert sum(1 for o in game.state.battlefield_objects(0) if o.tapped) == 5


class TestTheSolverIsUnchanged:
    """Life never reaches the payment solver, so ordinary hybrid is untouched."""

    def test_a_requirement_carries_no_life(self):
        req = ManaCost.parse("{U/P}").with_x(0)
        assert req == Requirement(hybrid=req.hybrid)

    def test_spending_a_phyrexian_pip_spends_its_colour(self):
        # Sunburst and converge read `SpentMana.colors`, and a pip paid the mana
        # way is a blue mana spent like any other.
        pool = ManaPool()
        pool.add("U")
        spent = pool.spend(ManaCost.parse("{U/P}").with_x(0))
        assert spent.colors == frozenset({"U"})
        assert pool.total() == 0

    def test_ordinary_hybrid_still_chooses_between_colours(self):
        cost = ManaCost.parse("{W/U}{W/U}").with_x(0)
        assert satisfies((1, 1, 0, 0, 0, 0), cost)
        assert satisfies((2, 0, 0, 0, 0, 0), cost)
        assert not satisfies((1, 0, 0, 0, 0, 0), cost)
