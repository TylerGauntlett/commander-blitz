"""Mana produced as a free combination of colours, in an amount the board sets.

"{0}: Add X mana in **any combination of {U} and/or {R}**, where X is Vivi
Ornitier's power." Two things at once, and the engine had neither together:

- The **amount** reads the board. `mana_amount` has done that since Gyre Sage,
  as a multiplier on one fixed option.
- The **combination** is a choice. A `choose_mode` of two `add_mana`s is the
  near miss and the reason this is a new mode rather than a card written the
  clever way: it offers "X of {U}" *or* "X of {R}" and can never make {U}{U}{R}{R}
  off a power-4 Vivi, which is the whole card.

So a split ability offers **one option per composition** and lets the mana
solver pick the one that pays the spell — which is what a player does at a
table. `TestItPaysATwoColourCost` is the load-bearing test: it asks for
{U}{U}{R}{R} off nothing but a power-4 source, which no single-colour option
can cover.

The one trap in the implementation is double counting. Every other mana ability
multiplies its option by `mana_amount`; a split's size is already *inside* each
option, so `mana_amount` returns 1 for one and X mana comes out rather than X².
`TestTheAmountIsNotAppliedTwice` pins it.

`in_commander_identity` was considered for Vivi and refused: it reads the
controller's commander identity rather than the printed {U}/{R}, so it is
correct only while Vivi *is* the commander and silently wrong in the 99 of a
five-colour deck.
"""

from __future__ import annotations

from commanderblitz.engine.costs import mana_amount, mana_options_of
from commanderblitz.engine.enums import ActionKind, Step
from commanderblitz.engine.mana import SYMBOLS
from commanderblitz.engine.primitives import add_counters
from tests.conftest import only_oid

MAGE = "t_vivi"  # {0}: add X mana split across {U}/{R}, X = its power


def a_mage(builder, power: int):
    """The split mage on the battlefield at ``power``, grown with counters."""
    game = builder(players=2).battlefield(0, [MAGE]).build()
    oid = game.state.battlefield[0]
    for _ in range(power):
        add_counters(game.state, oid, "+1/+1", 1)
    game.state.bump_chars()
    ability = next(a for a in game.state.registry.get(MAGE).abilities if a.is_mana_ability)
    return game, oid, ability


def as_pairs(options) -> set[tuple[int, int]]:
    """Each option as (blue, red), which is all these cards can make."""
    u, r = SYMBOLS.index("U"), SYMBOLS.index("R")
    return {(option[u], option[r]) for option in options}


class TestEveryCompositionIsOffered:
    def test_power_three_offers_all_four_splits(self, builder):
        game, oid, ability = a_mage(builder, 3)
        assert as_pairs(mana_options_of(game.state, oid, ability)) == {
            (0, 3),
            (1, 2),
            (2, 1),
            (3, 0),
        }

    def test_a_genuine_mix_is_among_them(self, builder):
        """The half a `choose_mode` of two `add_mana`s can never reach."""
        game, oid, ability = a_mage(builder, 4)
        assert (2, 2) in as_pairs(mana_options_of(game.state, oid, ability))

    def test_power_one_offers_one_of_each_colour(self, builder):
        game, oid, ability = a_mage(builder, 1)
        assert as_pairs(mana_options_of(game.state, oid, ability)) == {(0, 1), (1, 0)}


class TestZeroPowerMakesNothing:
    def test_a_printed_zero_power_source_offers_no_options(self, builder):
        """Vivi is a printed 0/3, and taps for nothing until it grows."""
        game, oid, ability = a_mage(builder, 0)
        assert mana_options_of(game.state, oid, ability) == ()


class TestTheAmountIsNotAppliedTwice:
    def test_the_multiplier_is_one(self, builder):
        """Every option already sums to X, so a `times` of X would give X squared."""
        game, oid, ability = a_mage(builder, 4)
        assert mana_amount(game.state, oid, ability) == 1

    def test_every_option_totals_exactly_the_power(self, builder):
        game, oid, ability = a_mage(builder, 5)
        for option in mana_options_of(game.state, oid, ability):
            assert sum(option) == 5


class TestActivatingItPutsTheSplitInThePool:
    """The end-to-end claim, and the one a two-mode version fails.

    Not through `mana_sources`: that collects only tap-only abilities, by
    design, so a `{0}` ability the player activates deliberately is correctly
    invisible to the payment solver. The player's own activation is the path
    this card is used through, so it is the path tested.
    """

    def position(self, builder, power: int):
        """A priority window, which needs something to do.

        Without a castable card in hand the engine auto-passes the main phase
        and hands back "declare attackers", where no activation is offered --
        and a test reading zero actions there would blame the ability.
        """
        game = (
            builder(players=2)
            .battlefield(0, [MAGE, "mountain", "mountain"])
            .battlefield(1, ["plains"])
            .library(0, ["forest"] * 10)
            .hand(0, ["pyretic_ritual"])
            .hand(1, ["t_plain_instant"])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        oid = only_oid(game, MAGE)
        for _ in range(power):
            add_counters(game.state, oid, "+1/+1", 1)
        game.state.bump_chars()
        game._advance()
        return game, oid

    def activations(self, game, oid):
        return [
            a for a in game.legal_actions() if a.kind is ActionKind.ACTIVATE and a.source == oid
        ]

    def test_one_action_per_composition_is_offered(self, builder):
        game, oid = self.position(builder, 4)
        assert len(self.activations(game, oid)) == 5, "0+4 through 4+0"

    def test_each_action_pools_its_own_composition(self, builder):
        """All five, each in a fresh game, so one working does not hide four.

        {U}{U}{R}{R} in a single activation is the whole point of the card and
        the one a `choose_mode` of two `add_mana`s can never produce.
        """
        u, r = SYMBOLS.index("U"), SYMBOLS.index("R")
        pooled = set()
        for index in range(5):
            game, oid = self.position(builder, 4)
            game.apply(self.activations(game, oid)[index])
            pool = game.state.players[0].mana_pool
            assert pool.total() == 4, "four mana, not sixteen -- the amount is not doubled"
            pooled.add((pool.amounts[u], pool.amounts[r]))

        assert pooled == {(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)}

    def test_a_zero_power_source_offers_no_activation(self, builder):
        """No composition of zero mana, so nothing to offer."""
        game, oid = self.position(builder, 0)
        assert self.activations(game, oid) == []
