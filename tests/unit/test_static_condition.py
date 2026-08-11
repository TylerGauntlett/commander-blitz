"""A static's "as long as…" clause, widened past counters on its own source.

Rule 604.3: a static ability with a condition is a continuous effect that
*exists whenever the condition is met* and stops existing the instant it is
not. There is no trigger, nothing goes on the stack, and nobody gets priority
in between — which is exactly why the trigger-shaped substitute is wrong. A
`pump` from an `upkeep` trigger applies a bonus at a moment and holds it until
cleanup; Nimble Mongoose is a 1/1 at six cards in the graveyard and a 3/3 at
seven, in either direction, mid-combat, on an opponent's turn, and again the
moment a card leaves the graveyard.

**Nimble Mongoose is the shipped witness** — "Threshold — This creature gets
+2/+2 as long as there are seven or more cards in your graveyard." Before this,
`_validate_static_condition` accepted exactly `{"counters": ...}`, so a card
whose condition asked about a zone could not be spelled at all, and the pool's
Mongoose was a 1/1 with the wrong evasion keyword.

The constraint the widening had to keep is the one in
`characteristics`'s module docstring: **no static may read another static's
output.** The condition is evaluated in `_battlefield_statics`, before layer -1,
so every leaf it can reach has to be a pipeline *input*. That is the claim
`TestItStaysAcyclic` pins: an anthem standing next to a conditional static
cannot change whether the condition holds, and `chars()` terminates.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.characteristics import chars
from automtg.engine.enums import Keyword
from automtg.engine.errors import DslError
from tests.conftest import only_oid


def board(builder, card: str, *, graveyard: int = 0, extra: list[str] | None = None):
    """``card`` on the battlefield, and ``graveyard`` Forests in its controller's yard."""
    b = builder(players=2).battlefield(0, [card, *(extra or [])])
    if graveyard:
        b = b.graveyard(0, ["forest"] * graveyard)
    game = b.build()
    return game, only_oid(game, card)


class TestThreshold:
    """The zone count -- the form Nimble Mongoose is printed with."""

    def test_below_seven_it_is_a_one_one(self, builder):
        game, oid = board(builder, "nimble_mongoose", graveyard=6)
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (1, 1), "six cards is not threshold"

    def test_at_seven_it_is_a_three_three(self, builder):
        game, oid = board(builder, "nimble_mongoose", graveyard=7)
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (3, 3)

    def test_the_boundary_is_seven_not_eight(self, builder):
        """`>=`, not `>`. Off by one here is the whole ability word."""
        game, oid = board(builder, "nimble_mongoose", graveyard=7)
        assert chars(game.state, oid).power == 3
        game.state.players[0].graveyard.pop()
        game.state.char_version += 1
        assert chars(game.state, oid).power == 1

    def test_it_wears_off_when_the_graveyard_shrinks(self, builder):
        """The half a trigger cannot do: the bonus goes away again."""
        game, oid = board(builder, "nimble_mongoose", graveyard=9)
        assert chars(game.state, oid).toughness == 3
        del game.state.players[0].graveyard[:5]
        game.state.char_version += 1
        assert chars(game.state, oid).toughness == 1

    def test_it_is_your_graveyard_not_everyones(self, builder):
        """`controller: "you"` -- an opponent milling themselves is not threshold."""
        game = (
            builder(players=2)
            .battlefield(0, ["nimble_mongoose"])
            .graveyard(1, ["forest"] * 10)
            .build()
        )
        oid = only_oid(game, "nimble_mongoose")
        assert chars(game.state, oid).power == 1

    def test_shroud_is_the_printed_evasion(self, builder):
        """It prints Shroud; the pool had it as hexproof, which is strictly better."""
        game, oid = board(builder, "nimble_mongoose")
        keywords = chars(game.state, oid).keywords
        assert Keyword.SHROUD.value in keywords
        assert Keyword.HEXPROOF.value not in keywords


class TestExists:
    """`{"exists": filter}` -- "as long as you control a…"."""

    def test_off_with_no_island(self, builder):
        game, oid = board(builder, "t_island_flier", extra=["forest"])
        assert Keyword.FLYING.value not in chars(game.state, oid).keywords

    def test_on_with_an_island(self, builder):
        game, oid = board(builder, "t_island_flier", extra=["island"])
        assert Keyword.FLYING.value in chars(game.state, oid).keywords

    def test_an_opponents_island_does_not_count(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["t_island_flier"])
            .battlefield(1, ["island"])
            .build()
        )
        oid = only_oid(game, "t_island_flier")
        assert Keyword.FLYING.value not in chars(game.state, oid).keywords


class TestTreeAndTurn:
    """`all` / `not` / `is_your_turn`, and a zone count over opponents.

    ``advance=False`` throughout: `is_your_turn` is an assertion about the
    position, and `build()`'s auto-pass rolls turns forward whenever nobody has
    a real decision, which would decide it for us.
    """

    def a_wall(self, builder, *, controller: int, active: int, graveyard=()):
        b = builder(players=2).battlefield(controller, ["t_defensive_wall"]).active(active)
        if graveyard:
            b = b.graveyard(1 - controller, list(graveyard))
        game = b.build(advance=False)
        return game, only_oid(game, "t_defensive_wall")

    def test_both_halves_true(self, builder):
        game, oid = self.a_wall(builder, controller=1, active=0)
        assert chars(game.state, oid).toughness == 7

    def test_your_own_turn_switches_it_off(self, builder):
        game, oid = self.a_wall(builder, controller=0, active=0)
        assert chars(game.state, oid).toughness == 4

    def test_a_creature_in_an_opponents_graveyard_switches_it_off(self, builder):
        game, oid = self.a_wall(builder, controller=1, active=0, graveyard=["t_bear"])
        assert chars(game.state, oid).toughness == 4

    def test_a_land_in_an_opponents_graveyard_does_not(self, builder):
        """The filter is `types: ["Creature"]`, so it must actually filter."""
        game, oid = self.a_wall(builder, controller=1, active=0, graveyard=["forest"] * 5)
        assert chars(game.state, oid).toughness == 7


class TestItStaysAcyclic:
    """The constraint the widening had to keep."""

    def test_an_anthem_cannot_change_whether_a_condition_holds(self, builder):
        """`t_anthem` gives +1/+1 to your creatures; the count is printed-only.

        If the condition read *derived* characteristics, a static could switch
        another static on and the fixed-order pipeline would have nothing to
        resolve it with. The count sees printed faces, so it does not.
        """
        game = (
            builder(players=2)
            .battlefield(0, ["nimble_mongoose", "t_anthem"])
            .graveyard(0, ["forest"] * 7)
            .build()
        )
        oid = only_oid(game, "nimble_mongoose")
        c = chars(game.state, oid)
        assert (c.power, c.toughness) == (4, 4), "1/1 +2/+2 threshold +1/+1 anthem"

    def test_two_conditional_statics_side_by_side_terminate(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["nimble_mongoose", "t_island_flier", "island"])
            .graveyard(0, ["forest"] * 7)
            .build()
        )
        assert chars(game.state, only_oid(game, "nimble_mongoose")).power == 3
        flier = only_oid(game, "t_island_flier")
        assert Keyword.FLYING.value in chars(game.state, flier).keywords


class TestTheLoaderRefusesWhatCannotWork:
    """A condition that loads and quietly matches nothing is the failure mode."""

    base = {
        "id": "t_probe",
        "name": "Probe",
        "mana_cost": "{G}",
        "types": ["Creature"],
        "power": 1,
        "toughness": 1,
    }

    def _with(self, condition):
        return CardModel.model_validate(
            {
                **self.base,
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "buff",
                        "affects": {"self_only": True},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                        "condition": condition,
                    }
                ],
            }
        )

    def test_board_state_keys_are_refused_off_the_battlefield(self):
        """A card in a graveyard is not tapped, so `tapped` there means nothing."""
        with pytest.raises(DslError, match="printed face and an owner"):
            compile_card(
                self._with({"exists": {"zone": "graveyard", "tapped": False}})
            )

    def test_an_unknown_zone_is_refused(self):
        with pytest.raises(DslError, match="unknown zone"):
            compile_card(self._with({"exists": {"zone": "stack"}}))

    def test_cmp_needs_both_sides(self):
        with pytest.raises(DslError, match="both 'left' and 'right'"):
            compile_card(self._with({"cmp": ">=", "left": {"const": 1}}))

    def test_a_static_value_is_still_only_const_or_count(self):
        with pytest.raises(DslError, match="only use 'const' or 'count'"):
            compile_card(
                self._with(
                    {"cmp": ">=", "left": {"life_of": "you"}, "right": {"const": 1}}
                )
            )

    def test_affects_still_may_not_name_a_zone(self):
        """`affects` picks out permanents; there are none outside the battlefield."""
        model = CardModel.model_validate(
            {
                **self.base,
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "buff",
                        "affects": {"zone": "graveyard"},
                        "power": {"const": 1},
                        "toughness": {"const": 1},
                    }
                ],
            }
        )
        with pytest.raises(DslError, match="printed characteristics"):
            compile_card(model)

    def test_the_counters_form_still_loads(self):
        """Arixmethes' spelling is untouched -- this widened, it did not replace."""
        card = compile_card(
            self._with({"counters": {"counter": "slumber", "op": ">=", "amount": 1}})
        )
        assert card.abilities[0].static["condition"] == {
            "counters": {"counter": "slumber", "op": ">=", "amount": 1}
        }
