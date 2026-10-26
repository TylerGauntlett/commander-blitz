"""``add_mana_on_tap`` conditioned on the mana the tap made.

    "Whenever you tap a permanent for {C}, add an additional {C}."
                                                  -- Forsaken Monument

Crypt Ghast's sentence names what was tapped ("a Swamp"); this one names what
the tap *made*. "Tap a permanent for {C}" (106.12) is a mana ability with {T} in
its cost that produced {C}, whatever the permanent is: a Sol Ring, a Wastes, a
Battlefield Forge tapped for its {C} -- and not the same Forge tapped for {R}.
`tapped_permanent` could not say it. Every other key it takes describes the
permanent, so the nearest spelling would add {C} to every Forest tapped for {G}.

`{"produced": "{C}"}` is the one key that describes the tap. It is met when
the tap made at least one of that mana, and it fires **once per tap**: a Sol
Ring's {C}{C} is one tap for {C}, so it makes {C}{C}{C}, not four. It is read at
the three places tapped mana is counted, now per mana option: the planner, the
payment and the chip label. If the planner counted the Forge's {R} option as
three mana, legality would offer a spell the payment then strands.

Ultima, Origin of Oblivion prints "a land for {C}", so the key combines with
the permanent's own keys.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.costs import activate_mana_ability, pay_mana
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.legality import _mana_option_label
from commanderblitz.engine.mana import SYMBOL_INDEX, ManaCost
from tests.conftest import oids_of, static_probe

MONUMENT = "t_tap_c_monument"
LAND_ONLY = "t_tap_c_land_only"

C = SYMBOL_INDEX["C"]
R = SYMBOL_INDEX["R"]
G = SYMBOL_INDEX["G"]


def position(builder, mine=(), theirs=()):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .active(0)
        .build(advance=False)
    )


def tap(game, card_id: str, pid: int = 0, ability: int = 0, option: int = 0) -> list[int]:
    oid = oids_of(game, card_id, pid)[0]
    activate_mana_ability(game.state, oid, ability, pid, option)
    return list(game.state.players[pid].mana_pool.amounts)


class TestWhatTheTapMade:
    def test_a_wastes_makes_two(self, builder):
        game = position(builder, [MONUMENT, "wastes"])
        assert tap(game, "wastes")[C] == 2

    def test_a_forest_makes_only_its_own(self, builder):
        """The near miss: an empty `tapped_permanent` would pay out here."""
        game = position(builder, [MONUMENT, "forest"])
        pool = tap(game, "forest")
        assert (pool[G], pool[C]) == (1, 0)

    def test_the_forge_tapped_for_colorless_counts(self, builder):
        game = position(builder, [MONUMENT, "battlefield_forge"])
        assert tap(game, "battlefield_forge", ability=0)[C] == 2

    def test_the_forge_tapped_for_red_does_not(self, builder):
        game = position(builder, [MONUMENT, "battlefield_forge"])
        pool = tap(game, "battlefield_forge", ability=1, option=0)
        assert (pool[R], pool[C]) == (1, 0)

    def test_any_permanent_counts(self, builder):
        game = position(builder, [MONUMENT, "sol_ring"])
        assert tap(game, "sol_ring")[C] == 3, "{C}{C} is one tap for {C}: one more, not two"

    def test_an_opponents_tap_does_not(self, builder):
        game = position(builder, [MONUMENT], ["wastes"])
        assert tap(game, "wastes", pid=1)[C] == 1


class TestItCombinesWithThePermanentsKeys:
    def test_a_land_for_colorless_counts(self, builder):
        game = position(builder, [LAND_ONLY, "wastes"])
        assert tap(game, "wastes")[C] == 2

    def test_a_nonland_for_colorless_does_not(self, builder):
        game = position(builder, [LAND_ONLY, "sol_ring"])
        assert tap(game, "sol_ring")[C] == 2


class TestPlannerAndPaymentAgree:
    def test_two_wastes_pay_four_colorless(self, builder):
        game = position(builder, [MONUMENT, "wastes", "wastes"])
        assert pay_mana(game.state, 0, ManaCost.parse("{C}{C}{C}{C}").with_x(0))

    def test_without_the_monument_they_cannot(self, builder):
        game = position(builder, ["wastes", "wastes"])
        assert not pay_mana(game.state, 0, ManaCost.parse("{C}{C}{C}{C}").with_x(0))

    def test_the_forge_is_not_counted_as_red_plus_colorless(self, builder):
        """Per option: {R}{C} from one Forge would need its red tap to carry
        the extra, which it does not."""
        game = position(builder, [MONUMENT, "battlefield_forge"])
        assert not pay_mana(game.state, 0, ManaCost.parse("{R}{C}").with_x(0))

    def test_the_chip_label_does_not_promise_the_extra_on_red(self, builder):
        game = position(builder, [MONUMENT, "battlefield_forge"])
        forge = oids_of(game, "battlefield_forge", 0)[0]
        ability = game.state.card(forge).abilities[1]
        assert _mana_option_label(game.state, forge, ability, 0) == "{R}"

    def test_but_its_colorless_tap_pays_two(self, builder):
        game = position(builder, [MONUMENT, "battlefield_forge"])
        assert pay_mana(game.state, 0, ManaCost.parse("{C}{C}").with_x(0))


class TestTheLoader:
    @pytest.mark.parametrize("produced", ["{C}{C}", "{2}", "C", "{X}", 1, ""])
    def test_one_symbol_only(self, produced):
        with pytest.raises(DslError, match="produced"):
            compile_card(
                CardModel.model_validate(
                    static_probe(
                        {
                            "effect": "add_mana_on_tap",
                            "affects_player": "you",
                            "tapped_permanent": {"produced": produced},
                            "add_mana": "{C}",
                        }
                    )
                )
            )

    def test_the_fixtures_load(self, registry):
        assert registry.get(MONUMENT).abilities
        assert registry.get(LAND_ONLY).abilities
