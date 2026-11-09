"""`greatest_commander_mana_value` read by an effect as it resolves.

    Cactus Preserve -- "{3}: Until end of turn, this land becomes an X/X green
    Plant creature with reach, where X is the greatest mana value among your
    commanders. It's still a land."

The static leaf (Tangleweave Armor) is re-read every time characteristics are
computed; an effect's X is fixed once, as the ability resolves (608.2h), and
`animate` sets the base P/T from it. The computation is the same --
`characteristics.greatest_commander_mana_value`, off `GameState.commanders_of`
and each commander's printed card, wherever it is (903.3) -- so both sides give
the same number for the same board.

Without the effect-side leaf the nearest spelling is `extreme_value` over a
selector with `is_commander`, which reaches one zone per selector: it reads 0
while the commander sits in the command zone, which is most of the game, and
the land would animate as a 0/0 and die to 704.5f. That is the boundary here
too: a seat with no commander really does get a 0/0, which dies.

"Your" commanders: a partner pair gives the larger, an opponent's commander
never counts, and the player spec is validated at load time.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, pass_until, pt, settle

PRESERVE = "t_gcmv_preserve"
BIG = "t_commander_five"        # mana value 5
SMALL = "t_commander_two"       # mana value 2


def position(builder, *, commanders=(), opponent_commanders=()):
    """``(game, preserve)``: the land and three Forests to pay {3} with."""
    b = (
        builder(players=2)
        .battlefield(0, ["forest"] * 3 + [PRESERVE])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
    )
    if commanders:
        b = b.commander(0, list(commanders))
    if opponent_commanders:
        b = b.commander(1, list(opponent_commanders))
    game = b.build()
    preserve = next(
        o.oid for o in game.state.battlefield_objects(0) if o.def_id == PRESERVE
    )
    return game, preserve


def animate_it(game, preserve) -> None:
    (action,) = activations(game, preserve, 1)
    game.apply(action)
    settle(game)


class TestXIsTheGreatestCommanderManaValue:
    def test_a_commander_in_the_command_zone_sizes_it(self, builder):
        game, preserve = position(builder, commanders=[BIG])
        animate_it(game, preserve)

        c = chars(game.state, preserve)
        assert (c.power, c.toughness) == (5, 5)
        assert {"Creature", "Land"} <= set(c.types), "it's still a land"
        assert "Plant" in c.subtypes and "reach" in c.keywords

    def test_a_commander_on_the_battlefield_still_counts(self, builder):
        game, preserve = position(builder, commanders=[BIG])
        commander = game.state.players[0].commanders[0]
        move_object(game.state, commander, Zone.BATTLEFIELD, to_player=0)
        animate_it(game, preserve)

        assert pt(game, preserve) == (5, 5)

    def test_partners_give_the_larger_not_the_sum(self, builder):
        game, preserve = position(builder, commanders=[SMALL, BIG])
        animate_it(game, preserve)

        assert pt(game, preserve) == (5, 5)

    def test_an_opponents_commander_is_not_yours(self, builder):
        game, preserve = position(
            builder, commanders=[SMALL], opponent_commanders=[BIG]
        )
        animate_it(game, preserve)

        assert pt(game, preserve) == (2, 2)


class TestTheBoundary:
    def test_with_no_commander_it_is_a_0_0_and_dies(self, builder):
        """X is 0, not an error: 704.5f puts the 0/0 land into the graveyard."""
        game, preserve = position(builder)
        animate_it(game, preserve)

        assert preserve not in game.state.battlefield
        assert game.state.objects[preserve].zone is Zone.GRAVEYARD

    def test_it_wears_off_at_end_of_turn(self, builder):
        game, preserve = position(builder, commanders=[BIG])
        animate_it(game, preserve)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn)

        c = chars(game.state, preserve)
        assert "Creature" not in c.types
        assert "Land" in c.types


class TestTheLoader:
    def _card(self, value) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_gcmv_effect_probe",
                "name": "Commander Mana Value Effect Probe",
                "mana_cost": "{1}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "gain_life", "amount": value}],
            }
        )

    def test_a_player_spec_loads(self):
        compile_card(self._card({"greatest_commander_mana_value": "you"}))

    def test_a_non_player_spec_is_refused(self):
        with pytest.raises(DslError, match="greatest_commander_mana_value"):
            compile_card(self._card({"greatest_commander_mana_value": 3}))
