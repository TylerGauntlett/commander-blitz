"""'This spell costs {X} less to cast.'

Ghalta is printed at twelve mana and is meant to be cast for two, so a reduction
that legality knows about but payment does not -- or the other way round -- is
the difference between a card that is uncastable and one that is free. Both
sides read the same `costs.cost_reduction`, and these tests are what pins them
together.

The reduction is read off the board every time it is asked for, never stored: a
creature arriving between the offer and the payment changes the answer.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.cost_reduction import cost_reduction
from automtg.engine.enums import ActionKind
from automtg.engine.errors import DslError
from tests.conftest import only_oid


def can_cast(game) -> bool:
    return any(
        a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == "ghalta_primal_hunger"
        for a in game.legal_actions()
    )


class TestGhalta:
    def board(self, builder, creatures: list[str], forests: int = 2):
        return (
            builder(players=2)
            .battlefield(0, ["forest"] * forests + creatures)
            .hand(0, ["ghalta_primal_hunger"])
            .build()
        )

    def test_the_reduction_is_the_total_power_you_control(self, registry, builder):
        game = self.board(builder, ["grizzly_bears", "grizzly_bears"])
        card = registry.get("ghalta_primal_hunger")
        assert cost_reduction(game.state, 0, card) == 4, "two 2/2s"

    def test_it_counts_only_your_creatures(self, registry, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["grizzly_bears"])
            .battlefield(1, ["grizzly_bears"] * 4)
            .build()
        )
        card = registry.get("ghalta_primal_hunger")
        assert cost_reduction(game.state, 0, card) == 2

    def test_twelve_mana_is_uncastable_off_two_lands_and_no_board(self, builder):
        assert not can_cast(self.board(builder, []))

    def test_ten_power_makes_it_castable_off_two_forests(self, registry, builder):
        """{10}{G}{G} minus ten is {G}{G}, and two Forests pay that."""
        if "terastodon" not in registry:
            pytest.skip("no fat creature in the pool")
        game = self.board(builder, ["terastodon"])  # 9/9
        assert cost_reduction(game.state, 0, registry.get("ghalta_primal_hunger")) == 9
        assert not can_cast(game), "nine is one short"

        game = self.board(builder, ["terastodon", "grizzly_bears"])  # 9/9 + 2/2
        assert can_cast(game)

    def test_paying_it_actually_taps_only_two(self, registry, builder):
        if "terastodon" not in registry:
            pytest.skip("no fat creature in the pool")
        game = self.board(builder, ["terastodon", "grizzly_bears"], forests=6)
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == "ghalta_primal_hunger"
        )
        game.apply(cast)
        tapped = sum(1 for o in game.state.battlefield_objects(0) if o.tapped)
        assert tapped == 2, "legality offered it for two; payment must charge two"

    def test_it_never_eats_into_the_coloured_pips(self, registry, builder):
        """A huge board does not make it free -- {G}{G} is still {G}{G}."""
        if "terastodon" not in registry:
            pytest.skip("no fat creature in the pool")
        game = self.board(builder, ["terastodon"] * 4, forests=1)
        assert cost_reduction(game.state, 0, registry.get("ghalta_primal_hunger")) == 36
        assert not can_cast(game), "one Forest cannot pay {G}{G}"

    def test_a_creature_arriving_changes_the_answer(self, registry, builder):
        game = self.board(builder, ["grizzly_bears"])
        card = registry.get("ghalta_primal_hunger")
        before = cost_reduction(game.state, 0, card)
        bear = only_oid(game, "grizzly_bears")
        game.state.objects[bear].counters["+1/+1"] = 3
        game.state.bump_chars()
        assert cost_reduction(game.state, 0, card) == before + 3, "counters count too"


class TestTheFieldIsChecked:
    base = {"id": "probe", "name": "Probe", "types": ["Instant"]}

    def test_an_unknown_reduction_is_rejected(self):
        model = CardModel.model_validate({**self.base, "cost_reduction": {"vibes": {}}})
        with pytest.raises(DslError, match="unknown reduction"):
            compile_card(model)

    def test_a_filter_that_reads_derived_state_is_rejected(self):
        model = CardModel.model_validate(
            {**self.base, "cost_reduction": {"count": {"damaged": True}}}
        )
        with pytest.raises(DslError, match="unsupported filter keys"):
            compile_card(model)
