"""A mana ability whose amount reads what its own cost paid with.

"{T}, Sacrifice another creature: Add an amount of {B} equal to the sacrificed
creature's mana value." -- Illuminor Szeras. "{T}, Sacrifice this artifact: Add X
mana of any one color, where X is the number of stash counters on this
artifact." -- Glittering Stockpile.

A mana ability is an activated ability (605.1a) whose cost is paid as any
other's (605.3a, 602.2b), so the creature it sacrificed is fixed by the payment
and its last-known information (608.2h) is what "the sacrificed creature's mana
value" reads. A stack ability already reads it through `sacrifice`'s ``as``
binding (Ghoulcaller Gisa); a mana ability never reaches the stack (605.3b), so
the binding has to travel from `costs.pay` to `costs.mana_amount` inside
`Game._activate_mana`. Without that the amount read an empty context and the
altar tapped for nothing whatever it ate -- and writing the line as a stack
ability instead would let an opponent respond to a mana ability.

The loader half: an amount may read only a name its own cost writes, since no
other name is ever bound on this path and would read 0 for ever.
"""

from __future__ import annotations

import copy
import json

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX
from commanderblitz.engine.primitives import add_counters
from tests.conftest import TEST_CARD_DIR, activations, only_oid

ALTAR = "t_cost_bound_altar"
STOCKPILE = "t_cost_bound_stockpile"
THREE = "t_cost_bound_mv3"
FIVE = "t_cost_bound_mv5"

#: A land drop keeps the main-phase window open: a board offering only mana
#: abilities auto-passes (`game._should_auto_pass`).
FILLER_HAND = ["mountain"]


def position(builder, cards, *, stash: int = 0):
    """A main phase with ``cards`` on seat 0's battlefield, Stockpile stashed."""
    game = (
        builder(players=2)
        .battlefield(0, list(cards))
        .hand(0, FILLER_HAND)
        .library(0, ["swamp"] * 20)
        .library(1, ["island"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build(advance=False)
    )
    if stash:
        add_counters(game.state, only_oid(game, STOCKPILE), "stash", stash)
    game._advance()
    return game


def pool_of(game, pid: int = 0) -> dict[str, int]:
    amounts = game.state.players[pid].mana_pool.amounts
    return {sym: amounts[i] for sym, i in SYMBOL_INDEX.items() if amounts[i]}


def sacrifice(game, oid: int) -> None:
    """Answer the cost's "Sacrifice" with exactly ``oid``.

    A pool of one is not asked about (`ask_objects` takes the forced answer),
    so then there is nothing to answer and ``oid`` must already be gone.
    """
    decision = game.pending()
    if decision is None or decision.kind is not DecisionKind.CHOOSE_OBJECTS:
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        return
    index = next(i for i, o in enumerate(decision.options) if o.ref is not None and o.ref.id == oid)
    game.apply(
        next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
    )
    if game.pending() is decision:
        game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))


def tap_altar(game, victim: str) -> int:
    """Activate the altar, feeding it ``victim``; the victim's oid."""
    altar = only_oid(game, ALTAR)
    oid = only_oid(game, victim)
    game.apply(activations(game, altar)[0])
    sacrifice(game, oid)
    return oid


class TestTheAmountIsTheSacrificedCreaturesManaValue:
    def test_a_five_drop_makes_five(self, builder):
        game = position(builder, [ALTAR, THREE, FIVE])
        tap_altar(game, FIVE)
        assert pool_of(game) == {"B": 5}

    def test_a_three_drop_makes_three(self, builder):
        """The same board, the other choice: the amount follows the payment."""
        game = position(builder, [ALTAR, THREE, FIVE])
        tap_altar(game, THREE)
        assert pool_of(game) == {"B": 3}

    def test_the_creature_is_really_sacrificed(self, builder):
        game = position(builder, [ALTAR, THREE, FIVE])
        five = tap_altar(game, FIVE)
        assert game.state.objects[five].zone is Zone.GRAVEYARD
        assert game.state.objects[only_oid(game, ALTAR)].tapped


class TestItIsStillAManaAbility:
    """605.3b: nothing goes on the stack, so nothing can be responded to."""

    def test_no_stack_item(self, builder):
        game = position(builder, [ALTAR, FIVE])
        tap_altar(game, FIVE)
        assert game.state.stack == []
        assert pool_of(game) == {"B": 5}

    def test_the_altar_is_not_offered_with_nothing_to_eat(self, builder):
        """"Another creature": the altar itself is no answer, and there is no other."""
        game = position(builder, [ALTAR])
        assert activations(game, only_oid(game, ALTAR)) == []


class TestASelfSacrificeReadsWhatTheSourceHad:
    """Glittering Stockpile: its counters are gone once it moves (400.7)."""

    def offers(self, game):
        return activations(game, only_oid(game, STOCKPILE))

    def test_three_stash_counters_make_three_of_one_colour(self, builder):
        game = position(builder, [STOCKPILE], stash=3)
        stockpile = only_oid(game, STOCKPILE)
        red = SYMBOL_INDEX["R"]
        action = next(a for a in self.offers(game) if a.mana_option == red)
        game.apply(action)
        assert pool_of(game) == {"R": 3}
        assert game.state.objects[stockpile].zone is Zone.GRAVEYARD

    def test_the_chip_previews_the_amount(self, builder):
        """Drawn before the cost is paid, from the snapshot the cost will take."""
        game = position(builder, [STOCKPILE], stash=2)
        labels = {a.label for a in self.offers(game)}
        assert any("{G}{G}" in (label or "") for label in labels), labels

    def test_no_counters_makes_nothing(self, builder):
        game = position(builder, [STOCKPILE], stash=0)
        game.apply(self.offers(game)[0])
        assert pool_of(game) == {}


def _altar_model() -> dict:
    cards = json.loads((TEST_CARD_DIR / "mana_ability_cost_binding.cards.json").read_text())
    return copy.deepcopy(next(c for c in cards["cards"] if c["id"] == ALTAR))


class TestTheLoaderRefusesANameNothingBinds:
    def test_the_altar_loads(self):
        compile_card(CardModel.model_validate(_altar_model()))

    def test_a_name_the_cost_does_not_write(self):
        card = _altar_model()
        card["abilities"][0]["effects"][0]["amount"] = {"mana_value_of": {"binding": "eaten"}}
        with pytest.raises(DslError, match="bound by nothing"):
            compile_card(CardModel.model_validate(card))

    def test_a_cost_with_no_as(self):
        card = _altar_model()
        del card["abilities"][0]["cost"]["sacrifice"]["as"]
        with pytest.raises(DslError, match="bound by nothing"):
            compile_card(CardModel.model_validate(card))

    def test_a_split_cannot_be_sized_by_the_cost(self):
        """Its combinations are offered before the cost is paid."""
        card = _altar_model()
        effect = card["abilities"][0]["effects"][0]
        del effect["mana"]
        effect["split"] = ["{B}", "{R}"]
        with pytest.raises(DslError, match="split"):
            compile_card(CardModel.model_validate(card))
