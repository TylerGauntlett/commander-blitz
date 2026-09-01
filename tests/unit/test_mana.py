"""Mana cost parsing, pools, and the automatic payment solver."""

from __future__ import annotations

import pytest

from automtg.engine.errors import DslError
from automtg.engine.mana import (
    SYMBOL_INDEX,
    ManaCost,
    ManaPool,
    ManaSource,
    Requirement,
    format_symbols,
    max_affordable_x,
    parse_mana_production,
    satisfies,
    solve_payment,
)


def amounts(**kwargs: int) -> tuple[int, ...]:
    out = [0] * 6
    for symbol, value in kwargs.items():
        out[SYMBOL_INDEX[symbol.upper()]] = value
    return tuple(out)


def source(oid: int, *options: tuple[int, ...], is_land: bool = True) -> ManaSource:
    return ManaSource(oid=oid, ability_index=0, options=options, is_land=is_land, sort_key=(0, oid))


class TestParsing:
    def test_generic_and_colored(self):
        cost = ManaCost.parse("{4}{G}{U}")
        assert cost.generic == 4
        assert cost.colored == amounts(g=1, u=1)
        assert cost.mana_value() == 6

    def test_repeated_pips(self):
        assert ManaCost.parse("{U}{U}").mana_value() == 2

    def test_colorless_pip_is_not_generic(self):
        cost = ManaCost.parse("{C}{C}")
        assert cost.generic == 0
        assert cost.colored == amounts(c=2)

    def test_x_counts_as_zero_off_the_stack(self):
        cost = ManaCost.parse("{X}{G}")
        assert cost.x_count == 1
        assert cost.mana_value() == 1
        assert cost.mana_value(x=3) == 4

    def test_empty_cost(self):
        assert ManaCost.parse(None).is_free()
        assert ManaCost.parse("").is_free()

    def test_colors_property(self):
        assert {c.value for c in ManaCost.parse("{W}{B}{R}").colors} == {"W", "B", "R"}

    # `{W/P}` was in this list and is deliberately no longer: phyrexian mana is
    # implemented, and `tests/unit/test_phyrexian_mana.py` asserts the parse it
    # now gets. `{S}` stays -- snow is still unmodelled.
    @pytest.mark.parametrize("text", ["{G", "G}", "{S}", "{4}x", "{W/Q}"])
    def test_unsupported_symbols_raise(self, text: str):
        with pytest.raises(DslError):
            ManaCost.parse(text)


class TestHybrid:
    """``{G/U}`` is a choice; ``{2/W}`` is a choice with a price."""

    def test_a_colour_choice_is_one_mana_and_two_colours(self):
        cost = ManaCost.parse("{4}{G/U}{G/U}")
        assert cost.mana_value() == 6
        assert {c.value for c in cost.colors} == {"G", "U"}, "both halves count"
        assert len(cost.hybrid) == 2

    def test_the_two_over_one_form_costs_the_larger_half(self):
        """``{2/W}`` has mana value 2, not 1 -- that is the printed rule."""
        cost = ManaCost.parse("{2/W}{2/W}")
        assert cost.mana_value() == 4

    def test_pips_are_not_folded_into_colored(self):
        """Kept apart because a hybrid pip is not a fixed demand.

        If ``{G/U}`` were counted as a ``{G}``, a deck with only Islands could
        not cast it -- the whole point of the symbol.
        """
        cost = ManaCost.parse("{G/U}")
        assert not any(cost.colored)

    @pytest.mark.parametrize(
        ("cost", "have", "payable"),
        [
            ("{G/U}{G/U}", {"g": 1, "u": 1}, True),
            ("{G/U}{G/U}", {"g": 2}, True),
            ("{G/U}{G/U}", {"g": 1}, False),
            ("{G/U}{G/U}", {"c": 2}, False),  # colourless is not either half
            ("{2/W}", {"w": 1}, True),
            ("{2/W}", {"c": 2}, True),  # the expensive way
            ("{2/W}", {"c": 1}, False),
            ("{1}{G/U}", {"g": 1, "c": 1}, True),
        ],
    )
    def test_what_can_pay_for_it(self, cost: str, have: dict, payable: bool):
        assert satisfies(amounts(**have), ManaCost.parse(cost).with_x(0)) is payable

    def test_spending_takes_the_half_the_solver_relied_on(self):
        """The interacting case, where a greedy deduction would go wrong.

        ``{G}{G/U}`` off one Green and one Blue: the fixed pip must take the
        Green, so the hybrid pip has to take the Blue. A rule that spent the
        most plentiful symbol first would take Green twice and strand the cost.
        """
        pool = ManaPool(amounts(g=1, u=1))
        pool.spend(ManaCost.parse("{G}{G/U}").with_x(0))
        assert pool.total() == 0

    def test_production_parsing(self):
        assert parse_mana_production("{G}{U}") == amounts(g=1, u=1)
        assert parse_mana_production("{2}") == amounts(c=2)

    def test_format_uses_wubrg_order(self):
        assert format_symbols(amounts(g=2, u=1)) == "{U}{G}{G}"
        assert format_symbols(amounts()) == "{0}"


class TestPool:
    def test_add_and_total(self):
        pool = ManaPool()
        pool.add("G", 2)
        pool.add("U")
        assert pool.total() == 3
        assert pool.to_dict() == {"U": 1, "G": 2}

    def test_clear_reports_loss(self):
        pool = ManaPool(amounts(g=3))
        assert pool.clear() == 3
        assert pool.total() == 0

    def test_spend_colored_then_generic(self):
        pool = ManaPool(amounts(g=2, u=2))
        pool.spend(Requirement(colored=amounts(g=1), generic=2))
        assert pool.total() == 1

    def test_spend_beyond_pool_raises(self):
        pool = ManaPool(amounts(g=1))
        with pytest.raises(ValueError):
            pool.spend(Requirement(colored=amounts(u=1)))


class TestSatisfies:
    def test_surplus_pays_generic(self):
        assert satisfies(amounts(g=3), Requirement(colored=amounts(g=1), generic=2))

    def test_colorless_pip_needs_colorless(self):
        assert not satisfies(amounts(g=2), Requirement(colored=amounts(c=1)))
        assert satisfies(amounts(c=1, g=1), Requirement(colored=amounts(c=1), generic=1))


class TestSolver:
    def test_pays_from_floating_mana_without_tapping(self):
        payment = solve_payment(Requirement(colored=amounts(g=1)), ManaPool(amounts(g=1)), [])
        assert payment is not None
        assert payment.taps == []

    def test_simple_two_lands(self):
        sources = [source(1, amounts(g=1)), source(2, amounts(u=1))]
        payment = solve_payment(
            Requirement(colored=amounts(g=1, u=1)), ManaPool(), sources
        )
        assert payment is not None
        assert sorted(oid for oid, _, _ in payment.taps) == [1, 2]

    def test_unpayable_returns_none(self):
        sources = [source(1, amounts(g=1))]
        assert solve_payment(Requirement(colored=amounts(u=1)), ManaPool(), sources) is None

    def test_dual_land_covers_two_pips_at_once(self):
        """A land that adds {G}{U} on one tap must satisfy {G}{U} by itself."""
        sources = [source(1, amounts(g=1, u=1))]
        payment = solve_payment(
            Requirement(colored=amounts(g=1, u=1)), ManaPool(), sources
        )
        assert payment is not None
        assert payment.taps == [(1, 0, 0)]

    def test_most_constrained_color_first(self):
        """With one blue source and two green ones, the blue pip must not be stranded."""
        sources = [
            source(1, amounts(g=1), amounts(u=1)),  # either colour
            source(2, amounts(g=1)),
        ]
        payment = solve_payment(
            Requirement(colored=amounts(g=1, u=1)), ManaPool(), sources
        )
        assert payment is not None
        assert sorted(oid for oid, _, _ in payment.taps) == [1, 2]

    def test_generic_uses_leftovers(self):
        sources = [source(i, amounts(g=1)) for i in range(1, 5)]
        payment = solve_payment(
            Requirement(colored=amounts(g=1), generic=3), ManaPool(), sources
        )
        assert payment is not None
        assert len(payment.taps) == 4

    def test_prefers_lands_over_creatures_for_generic(self):
        sources = [
            source(1, amounts(g=1), is_land=False),
            source(2, amounts(g=1), is_land=True),
        ]
        sources[0] = ManaSource(1, 0, (amounts(g=1),), is_land=False, sort_key=(1, 1))
        payment = solve_payment(Requirement(generic=1), ManaPool(), sources)
        assert payment is not None
        assert payment.taps == [(2, 0, 0)]

    def test_deterministic_across_calls(self):
        sources = [source(i, amounts(g=1)) for i in range(1, 6)]
        first = solve_payment(Requirement(generic=3), ManaPool(), sources)
        second = solve_payment(Requirement(generic=3), ManaPool(), sources)
        assert first is not None and second is not None
        assert first.taps == second.taps

    def test_the_chosen_option_is_recorded(self):
        """A modal source must report *which* mode paid, not just that it tapped.

        Without this the caller has to re-decide, and a "add {G} or {U}" land
        would stop to ask its controller mid-payment.
        """
        dual = ManaSource(1, 0, (amounts(g=1), amounts(u=1)), sort_key=(0, 1))
        green = solve_payment(Requirement(colored=amounts(g=1)), ManaPool(), [dual])
        blue = solve_payment(Requirement(colored=amounts(u=1)), ManaPool(), [dual])
        assert green is not None and blue is not None
        assert green.taps == [(1, 0, 0)]
        assert blue.taps == [(1, 0, 1)]

    def test_backtracking_finds_awkward_assignment(self):
        """Greedy alone can strand a pip; the search fallback must recover."""
        sources = [
            ManaSource(1, 0, (amounts(w=1), amounts(u=1)), sort_key=(0, 1)),
            ManaSource(2, 0, (amounts(w=1), amounts(u=1)), sort_key=(0, 2)),
        ]
        payment = solve_payment(
            Requirement(colored=amounts(w=1, u=1)), ManaPool(), sources
        )
        assert payment is not None
        assert len(payment.taps) == 2


class TestMaxX:
    def test_no_x_returns_zero(self):
        assert max_affordable_x(ManaCost.parse("{G}"), ManaPool(amounts(g=1)), []) == 0

    def test_unaffordable_returns_minus_one(self):
        assert max_affordable_x(ManaCost.parse("{G}"), ManaPool(), []) == -1

    def test_scales_with_available_mana(self):
        sources = [source(i, amounts(g=1)) for i in range(1, 6)]
        assert max_affordable_x(ManaCost.parse("{X}{G}"), ManaPool(), sources) == 4
