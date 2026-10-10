""""…any **type** that a land you control could produce."

    Reflecting Pool — "{T}: Add one mana of any type that a land you control
    could produce."
    Horizon of Progress — the same clause, off a land that also ramps and
    cantrips.

One printed word apart from `reflecting` (Exotic Orchard, Fellwar Stone), and
that word is worth a whole capability. 106.1b names **six** types of mana —
white, blue, black, red, green and *colorless* — so "any type" is "any color"
plus `{C}`, and `reflecting` drops `{C}` on purpose twice over: its load-time
superset is `_ANY_COLOR_OPTIONS`, five tuples, and `costs._reflect_options`
skips the colorless index while polling the board.

Written as plain `reflecting`, Reflecting Pool loads clean and is an Exotic
Orchard pointed at your own side: it cannot tap off a Wastes, an Ancient Tomb or
any other colorless land — which is half of what the card is in a deck that
plays them. `proxy._REFLECTED_COLOR` names this card in its own comment as the
reason it refuses to match "any type", so the narrowness was a decision, and
this is the widening of it.

**Only the vocabulary widens.** The question is the same question — "what could
these permanents produce" — asked of the same selector, answered by the same
one-level recursion with the same skip of other reflecting abilities. A Pool
still offers nothing the board cannot make: beside a lone Forest it taps for
`{G}` and not for `{C}`, which is what separates this from the `choose_mode`
over six modes that would be an unconditional any-type land.

The colorless case is the entire test. Every other assertion here is shared with
`test_reflecting_mana.py`; a Pool beside a Wastes is the one that is not.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import mana_options_of, mana_sources
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX
from tests.conftest import oids_of

POOL = "t_pool"  # "…any *type* that a land *you control* could produce"
ORCHARD = "t_orchard"  # "…any *color* that a land *an opponent* controls could produce"


def types_offered(game, oid: int) -> set[str]:
    """Every mana symbol the ability actually offers, after the board narrows it."""
    ability = game.state.card(oid).abilities[0]
    out: set[str] = set()
    for option in mana_options_of(game.state, oid, ability):
        for symbol, index in SYMBOL_INDEX.items():
            if option[index]:
                out.add(symbol)
    return out


def board(builder, my_lands):
    """The Pool, plus whatever else I control. Nothing on the other side."""
    game = builder(players=2).battlefield(0, [POOL, *my_lands]).battlefield(1, []).build()
    return game, oids_of(game, POOL)[0]


class TestTheSixthTypeOfMana:
    """`{C}` is the whole difference between "any color" and "any type"."""

    def test_a_wastes_offers_colorless(self, builder):
        """The claim. Written as plain `reflecting` this is the empty set."""
        game, pool = board(builder, ["wastes"])
        assert types_offered(game, pool) == {"C"}

    def test_the_colour_only_family_still_refuses_the_same_wastes(self, builder):
        """Exotic Orchard's line has not moved. The widening is per-card, not
        a relaxation of the family: the Orchard beside a Wastes taps for
        nothing, and that is still the right answer to "any **color**"."""
        game = (
            builder(players=2)
            .battlefield(0, [ORCHARD])
            .battlefield(1, ["wastes"])
            .build()
        )
        assert types_offered(game, oids_of(game, ORCHARD)[0]) == set()

    def test_a_land_that_makes_two_colorless_also_offers_it(self, builder):
        """Ancient Tomb adds {C}{C}. The amount is not the question — whether
        the type appears in any option is."""
        game, pool = board(builder, ["ancient_tomb"])
        assert types_offered(game, pool) == {"C"}

    def test_colour_and_colorless_together(self, builder):
        game, pool = board(builder, ["forest", "wastes"])
        assert types_offered(game, pool) == {"G", "C"}


class TestItIsStillTheBoardsQuestion:
    """The near miss is a six-mode any-type land, and it is a better card."""

    def test_a_forest_offers_green_and_not_colorless(self, builder):
        """The regression that a `_ANY_TYPE_OPTIONS` superset left un-narrowed
        would produce: a Pool that taps for {C} with no colorless source out."""
        game, pool = board(builder, ["forest"])
        assert types_offered(game, pool) == {"G"}

    def test_a_forest_offers_only_green(self, builder):
        game, pool = board(builder, ["forest"])
        assert len(types_offered(game, pool)) == 1

    def test_no_other_land_offers_nothing(self, builder):
        """The Pool is itself a land I control, and a reflecting ability is
        skipped before the recursion — so an otherwise empty board is empty."""
        game, pool = board(builder, [])
        assert types_offered(game, pool) == set()

    def test_two_pools_do_not_ask_each_other(self, builder):
        game, pool = board(builder, [POOL])
        assert types_offered(game, pool) == set()

    def test_an_opponents_wastes_does_not_count(self, builder):
        """"…a land **you control**." The selector is unchanged by the widening."""
        game = (
            builder(players=2)
            .battlefield(0, [POOL])
            .battlefield(1, ["wastes", "forest"])
            .build()
        )
        assert types_offered(game, oids_of(game, POOL)[0]) == set()


class TestTheSolverSeesTheColorless:
    """`mana_options_of` has two callers and they must agree, or a payment is
    offered on one type and billed on another mid-cast."""

    def test_the_pool_is_a_source_off_a_wastes_alone(self, builder):
        game, pool = board(builder, ["wastes"])
        assert any(s.oid == pool for s in mana_sources(game.state, 0))

    def test_it_produces_colorless(self, builder):
        game, pool = board(builder, ["wastes"])
        source = next(s for s in mana_sources(game.state, 0) if s.oid == pool)
        assert source.producible() == {SYMBOL_INDEX["C"]}

    def test_it_produces_both_beside_a_forest(self, builder):
        game, pool = board(builder, ["forest", "wastes"])
        source = next(s for s in mana_sources(game.state, 0) if s.oid == pool)
        assert source.producible() == {SYMBOL_INDEX["G"], SYMBOL_INDEX["C"]}


def _land(effect: dict) -> dict:
    return {
        "id": "t_any_type_probe",
        "name": "Probe",
        "types": ["Land"],
        "abilities": [
            {
                "kind": "activated",
                "text": "{T}: Add one mana of any type that a land you control could produce.",
                "is_mana_ability": True,
                "cost": {"tap": True},
                "effects": [effect],
            }
        ],
    }


REFLECTS = {"zone": "battlefield", "controller": "you", "types": ["Land"]}


class TestTheLoaderPinsTheSuperset:
    """The static superset is what makes the ability a mana source at all —
    `solver_taps` and `offerable_mana_ability` both read it before the board is
    consulted, so an ability carrying the wrong one is narrowed to nothing."""

    def test_any_type_advertises_six(self):
        card = compile_card(
            CardModel.model_validate(
                _land({"op": "add_mana", "reflecting": REFLECTS, "any_type": True})
            )
        )
        ability = card.abilities[0]
        assert ability.mana_reflects_any_type is True
        assert len(ability.mana_options) == 6

    def test_any_color_still_advertises_five(self):
        card = compile_card(
            CardModel.model_validate(_land({"op": "add_mana", "reflecting": REFLECTS}))
        )
        ability = card.abilities[0]
        assert ability.mana_reflects_any_type is False
        assert len(ability.mana_options) == 5


class TestTheLoaderRefusesAnyTypeAlone:
    """`any_type` is read only beside `reflecting`. Everywhere else on an
    add_mana it would load, be ignored, and leave the printed word doing
    nothing — which is exactly the silent wrong card this capability exists to
    stop being."""

    def test_a_fixed_mana_string_refuses_it(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(_land({"op": "add_mana", "mana": "{C}", "any_type": True}))
            )

    def test_commander_identity_refuses_it(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _land(
                        {
                            "op": "add_mana",
                            "in_commander_identity": True,
                            "any_type": True,
                        }
                    )
                )
            )

    def test_false_is_refused_rather_than_read_as_any_color(self):
        """"any color" is the default and is spelled by saying nothing, so a
        `false` here is a card whose author meant something this cannot tell."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    _land({"op": "add_mana", "reflecting": REFLECTS, "any_type": False})
                )
            )
