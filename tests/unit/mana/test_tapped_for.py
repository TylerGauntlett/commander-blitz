"""`tapped_for`: "whenever you tap a permanent **for {C}**, add an additional {C}".

    Forsaken Monument.

The same triggered mana ability as Crypt Ghast (605.1b), resolving at once and
never using the stack (605.4a), so it is the `add_mana_on_tap` static read at
the mana choke point. What differs is the trigger condition. Crypt Ghast asks
what the tapped permanent *is* ("a Swamp"); Forsaken Monument asks what it was
tapped *for* -- any permanent, of any type, whose {T} mana ability made {C}:
Sol Ring, Wastes, a colorless creature. `tapped_permanent` cannot say that:
every key it has describes the permanent, so the closest spelling, "any
permanent", would add {C} for every Forest tapped for {G}.

`tapped_for` names the type of mana. It reads the yield of the ability that was
activated (106.12: "tap for mana" is a mana ability with {T} in its cost), for
the option chosen, before any *other* triggered mana ability adds to it, and
fires once when that yield holds at least one mana of the type. A Sol Ring's
{C}{C} adds one {C}, not two -- it is a trigger, not Mana Reflection's
"produces twice as much" replacement -- and a doubler's extra {C} (Kinnan) is
the doubler's mana and does not trigger it again.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, pay_mana
from commanderblitz.engine.enums import ActionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from tests.conftest import oids_of

MONUMENT = "t_c_monument"
C_OR_G = "t_c_or_g_rock"  # {T}: Add {C} or {G}.
FIVE = "t_five_rock"  # {5}
KINNAN = "t_nonland_doubler"  # Kinnan's doubling, nonland permanents

C = SYMBOL_INDEX["C"]
G = SYMBOL_INDEX["G"]


def position(builder, mine=(), theirs=(), *, hand=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .hand(0, list(hand))
        .active(0)
        .build(advance=False)
    )


def tap(game, card_id: str, pid: int = 0, option: int = 0) -> list[int]:
    """Tap the first ``card_id`` ``pid`` controls for mana; return their pool."""
    oid = oids_of(game, card_id, pid)[0]
    activate_mana_ability(game.state, oid, 0, pid, option)
    return list(game.state.players[pid].mana_pool.amounts)


class TestAnyPermanentTappedForColorless:
    def test_a_wastes_makes_two(self, builder):
        game = position(builder, [MONUMENT, "wastes"])
        assert tap(game, "wastes") == [0, 0, 0, 0, 0, 2]

    def test_an_artifact_counts_too(self, builder):
        """Not a land question: any permanent type (Forsaken Monument's ruling)."""
        game = position(builder, [MONUMENT, "sol_ring"])
        assert tap(game, "sol_ring")[C] == 3

    def test_a_forest_tapped_for_green_does_not(self, builder):
        game = position(builder, [MONUMENT, "forest"])
        assert tap(game, "forest") == [0, 0, 0, 0, 1, 0]

    def test_without_the_monument_a_wastes_makes_one(self, builder):
        game = position(builder, ["wastes"])
        assert sum(tap(game, "wastes")) == 1

    def test_the_extra_pip_is_the_monuments(self, builder):
        game = position(builder, [MONUMENT, "wastes"])
        monument = oids_of(game, MONUMENT, 0)[0]
        wastes = oids_of(game, "wastes", 0)[0]
        tap(game, "wastes")
        made_by = [pip.source for pip in game.state.players[0].mana_pool.tags[C]]
        assert sorted(made_by) == sorted([monument, wastes])

    def test_an_opponents_wastes_gets_nothing(self, builder):
        game = position(builder, [MONUMENT], ["wastes"])
        assert sum(tap(game, "wastes", 1)) == 1


class TestWhatItWasTappedFor:
    def test_the_colorless_option_triggers_it(self, builder):
        game = position(builder, [MONUMENT, C_OR_G])
        assert tap(game, C_OR_G, option=0) == [0, 0, 0, 0, 0, 2]

    def test_the_green_option_does_not(self, builder):
        """Asked of the mana made, not of the permanent that can make {C}."""
        game = position(builder, [MONUMENT, C_OR_G])
        assert tap(game, C_OR_G, option=1) == [0, 0, 0, 0, 1, 0]

    def test_two_colorless_add_one(self, builder):
        """A trigger, not Mana Reflection's doubling: Sol Ring's {C}{C} adds
        one more {C}, as a Swamp under Crypt Ghast adds one more {B}."""
        game = position(builder, [MONUMENT, "sol_ring"])
        assert sum(tap(game, "sol_ring")) == 3

    def test_two_monuments_trigger_separately(self, builder):
        game = position(builder, [MONUMENT, MONUMENT, "wastes"])
        assert tap(game, "wastes")[C] == 3

    def test_a_doublers_extra_mana_does_not_trigger_it_again(self, builder):
        """Kinnan adds one {C} of its own; the Monument adds one for the Sol
        Ring's {C}{C}. Neither is counted as what the Sol Ring was tapped for."""
        game = position(builder, [MONUMENT, KINNAN, "sol_ring"])
        assert tap(game, "sol_ring")[C] == 4

    def test_a_mana_ability_without_tap_is_not_tapping_for_mana(self, builder):
        """106.12: an Eldrazi Spawn sacrificed for {C} was not tapped for it."""
        game = position(builder, [MONUMENT, "eldrazi_spawn_0_1_c"])
        assert sum(tap(game, "eldrazi_spawn_0_1_c")) == 1


class TestPlannerAndPaymentAgree:
    def test_the_solver_pays_five_from_a_sol_ring_and_a_wastes(self, builder):
        game = position(builder, [MONUMENT, "sol_ring", "wastes"])
        assert pay_mana(game.state, 0, ManaCost.parse("{5}").with_x(0))

    def test_without_the_monument_it_cannot(self, builder):
        game = position(builder, ["sol_ring", "wastes"])
        assert not pay_mana(game.state, 0, ManaCost.parse("{5}").with_x(0))

    def test_the_green_option_is_offered_without_the_extra(self, builder):
        """Per option: the solver may not count the {C} rider on a {G} yield."""
        game = position(builder, [MONUMENT, C_OR_G])
        assert not pay_mana(game.state, 0, ManaCost.parse("{G}{C}").with_x(0))
        assert pay_mana(
            position(builder, [MONUMENT, C_OR_G]).state, 0, ManaCost.parse("{C}{C}").with_x(0)
        )

    @staticmethod
    def offered(builder, mine) -> bool:
        game = builder(players=2).battlefield(0, list(mine)).hand(0, [FIVE]).active(0).build()
        return any(
            a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == FIVE
            for a in game.legal_actions()
        )

    def test_legality_offers_the_spell_the_extra_mana_affords(self, builder):
        assert self.offered(builder, [MONUMENT, "sol_ring", "wastes"])

    def test_and_does_not_offer_it_without(self, builder):
        assert not self.offered(builder, ["sol_ring", "wastes"])


def _card(**static) -> dict:
    ability = {
        "kind": "static",
        "text": "Whenever you tap a permanent for {C}, add an additional {C}.",
        "effect": "add_mana_on_tap",
        "affects_player": "you",
        "tapped_for": "{C}",
        "add_mana": "{C}",
    }
    ability.update(static)
    ability = {k: v for k, v in ability.items() if v is not None}
    return {
        "id": "t_bad_monument",
        "name": "Bad Monument",
        "oracle_text": ability["text"],
        "mana_cost": "{5}",
        "types": ["Artifact"],
        "abilities": [ability],
    }


class TestTheLoader:
    def test_the_shape_loads(self):
        compile_card(CardModel.model_validate(_card()))

    def test_it_composes_with_tapped_permanent(self):
        """ "Whenever you tap a land for {C}" would be both keys."""
        compile_card(CardModel.model_validate(_card(tapped_permanent={"types": ["Land"]})))

    @pytest.mark.parametrize(
        "change",
        [
            {"tapped_for": None},
            {"tapped_for": "C"},
            {"tapped_for": "{C}{C}"},
            {"tapped_for": "{1}"},
            {"tapped_for": "{W/U}"},
            {"tapped_for": "{Q}"},
            {"add_mana": None},
        ],
        ids=["neither", "bare-letter", "two-symbols", "generic", "hybrid", "unknown", "no-mana"],
    )
    def test_refused(self, change):
        with pytest.raises(DslError):
            compile_card(CardModel.model_validate(_card(**change)))

    def test_refused_on_another_static(self):
        card = _card(effect="double_land_mana", add_mana=None)
        with pytest.raises(DslError, match="tapped_for"):
            compile_card(CardModel.model_validate(card))
