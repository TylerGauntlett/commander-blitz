""""Plotting cards from your hand costs {2} less." -- Doc Aurlock, Grizzled Genius.

Plot (702.171a) is a special action (116.2k): neither a spell, so
`spell_cost_reduction` is never asked, nor an activated ability, so
`ability_cost_reduction` is not either. Without `plot_cost_reduction` Doc's
second line loads as nothing at all and every plot costs its printed price.

`suspend.plot_price` is the one price both the offer (`legality`) and the
payment (`suspend.plot_card`) read, so a card offered at the reduced price is
charged it. Generic only and clamped at zero, like every reduction: {2} less off
Plot {1}{R} is {R}, and Plot {G} stays {G}. The later cast of a plotted card is
free (601.2b), so there is nothing left there to discount; the discount is on
plotting alone, never on casting the card from hand.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.suspend import plot_price
from commanderblitz.engine.zones import move_object
from tests.conftest import settle_to_priority

BOLT = "t_plotter"  # {3}{R}{R} instant, plot {1}{R}
BEAR = "t_plotted_bear"  # {3}{G} 2/2, plot {G}
DOC = "t_plot_discounter"  # plotting cards from your hand costs {2} less


def position(builder, hand, *, lands=("mountain",), mine=(DOC,), theirs=()):
    game = (
        builder(players=2)
        .battlefield(0, [*lands, *mine])
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .hand(0, list(hand))
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game, game.state.players[0].hand[0]


def plot_action(game, oid: int):
    return next(
        (a for a in game.legal_actions() if a.kind is ActionKind.SUSPEND and a.source == oid),
        None,
    )


def price(game, oid: int) -> tuple[int, tuple[int, ...]]:
    cost = plot_price(game.state, 0, game.state.card(oid))
    return cost.generic, cost.colored


class TestTheOffer:
    def test_one_mountain_plots_a_one_red_plot_cost(self, builder):
        """{1}{R} less {2} is {R}: one Mountain is enough."""
        game, oid = position(builder, [BOLT])

        assert plot_action(game, oid) is not None

    def test_without_the_static_it_is_not_enough(self, builder):
        """The control, `test_plot_from_hand.py`'s own boundary."""
        game, oid = position(builder, [BOLT], mine=())

        assert plot_action(game, oid) is None

    def test_the_discount_never_reaches_a_coloured_pip(self, builder):
        """Plot {G} has no generic part, so nothing is taken off it."""
        game, oid = position(builder, [BEAR], lands=())

        generic, colored = price(game, oid)
        assert generic == 0 and sum(colored) == 1
        assert plot_action(game, oid) is None

    def test_casting_the_card_is_not_discounted(self, builder):
        """Plotting, not casting: {3}{R}{R} off three Mountains is still too much."""
        game, oid = position(builder, [BOLT], lands=("mountain",) * 3)

        assert not any(
            a.kind is ActionKind.CAST and a.source == oid for a in game.legal_actions()
        )


class TestThePayment:
    def test_it_charges_the_reduced_price(self, builder):
        """Two Mountains, a price of {R}: one is left untapped."""
        game, oid = position(builder, [BOLT], lands=("mountain", "mountain"))
        game.apply(plot_action(game, oid))
        settle_to_priority(game)

        assert game.state.objects[oid].zone is Zone.EXILE
        mountains = [
            m for m in game.state.battlefield if game.state.objects[m].def_id == "mountain"
        ]
        assert sorted(game.state.objects[m].tapped for m in mountains) == [False, True]

    def test_the_plotted_card_is_left_the_ordinary_permission(self, builder):
        game, oid = position(builder, [BOLT])
        game.apply(plot_action(game, oid))
        settle_to_priority(game)
        obj = game.state.objects[oid]

        assert obj.playable_by == 0 and obj.playable_free and obj.playable_sorcery_only


class TestWhoseAndHowMuch:
    def test_two_add_up_but_clamp_at_the_generic_part(self, builder):
        game, oid = position(builder, [BOLT], mine=(DOC, DOC))

        generic, colored = price(game, oid)
        assert generic == 0 and sum(colored) == 1

    def test_an_opponents_does_not_discount_yours(self, builder):
        game, oid = position(builder, [BOLT], mine=(), theirs=(DOC,))

        assert price(game, oid)[0] == 1
        assert plot_action(game, oid) is None

    def test_it_ends_when_the_source_leaves(self, builder):
        game, oid = position(builder, [BOLT])
        doc = next(m for m in game.state.battlefield if game.state.objects[m].def_id == DOC)
        move_object(game.state, doc, Zone.GRAVEYARD, cause="test")

        assert price(game, oid)[0] == 1
        assert plot_action(game, oid) is None


class TestTheLoader:
    def card(self, **extra):
        static = {
            "kind": "static",
            "text": "Plotting cards from your hand costs {2} less.",
            "effect": "plot_cost_reduction",
            "affects_player": "you",
            "amount": {"const": 2},
        }
        static.update(extra)
        return {
            "id": "t_probe_plot_discount",
            "name": "Probe Plot Discount",
            "mana_cost": "{4}",
            "types": ["Artifact"],
            "abilities": [{k: v for k, v in static.items() if v is not None}],
        }

    def test_the_printed_line_loads(self):
        compile_card(CardModel.model_validate(self.card()))

    def test_it_needs_an_amount(self):
        with pytest.raises(DslError, match="needs an 'amount'"):
            compile_card(CardModel.model_validate(self.card(amount=None)))

    def test_a_zero_amount_is_refused(self):
        with pytest.raises(DslError, match="1 or more"):
            compile_card(CardModel.model_validate(self.card(amount={"const": 0})))

    def test_a_permanent_filter_is_refused(self):
        with pytest.raises(DslError, match="no 'affects'"):
            compile_card(CardModel.model_validate(self.card(affects={"types": ["Creature"]})))

    def test_it_needs_a_player(self):
        with pytest.raises(DslError, match="affects_player"):
            compile_card(CardModel.model_validate(self.card(affects_player=None)))
