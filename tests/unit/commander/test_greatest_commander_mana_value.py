"""`greatest_commander_mana_value` -- a static's magnitude read off the command zone.

    Tangleweave Armor -- "Equipped creature gets +X/+X, where X is the greatest
    mana value among your commanders."

Rule 903.3: a commander is a card, and it is one wherever it is. For most of a
game it sits in the command zone, which no static filter reaches -- a `count`
or `max_count_of` walks the battlefield or one player's zone list, and
`is_commander` on a battlefield filter would read 0 whenever the commander is
home. So the leaf reads `GameState.commanders_of` directly, off the printed
card, which is a pipeline input on `mana_symbols`' terms.

"Greatest", not a sum: a player with two partners gets the larger of the two,
and a seat with no commander at all reads 0 rather than failing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pt

HOST = "t_gcmv_host"            # 1/1, +X/+X
BIG = "t_commander_five"        # mana value 5
SMALL = "t_commander_two"       # mana value 2
FOREST = "forest"


def position(builder, *, commanders=(), opponent_commanders=()):
    """``HOST`` on player 0's battlefield, commanders in the command zones."""
    b = (
        builder(players=2)
        .battlefield(0, [FOREST, HOST])
        .library(0, [FOREST] * 10)
        .library(1, [FOREST] * 10)
    )
    if commanders:
        b = b.commander(0, list(commanders))
    if opponent_commanders:
        b = b.commander(1, list(opponent_commanders))
    game = b.build(advance=False)
    host = next(o.oid for o in game.state.battlefield_objects(0) if o.def_id == HOST)
    return game, host


class TestItReadsTheCommandZone:
    def test_a_commander_at_home_counts(self, builder):
        game, host = position(builder, commanders=[BIG])

        assert pt(game, host) == (6, 6)

    def test_no_commander_is_zero(self, builder):
        game, host = position(builder)

        assert pt(game, host) == (1, 1)

    def test_a_commander_on_the_battlefield_still_counts(self, builder):
        game, host = position(builder, commanders=[BIG])
        commander = game.state.players[0].commanders[0]
        move_object(game.state, commander, Zone.BATTLEFIELD, to_player=0)

        assert pt(game, host) == (6, 6)


class TestItIsTheGreatestOne:
    def test_two_partners_give_the_larger_not_the_sum(self, builder):
        game, host = position(builder, commanders=[SMALL, BIG])

        assert pt(game, host) == (6, 6)

    def test_an_opponents_commander_is_not_yours(self, builder):
        game, host = position(builder, commanders=[SMALL], opponent_commanders=[BIG])

        assert pt(game, host) == (3, 3)


class TestTheLoader:
    def _card(self, value) -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_gcmv_probe",
                "name": "Commander Mana Value Probe",
                "mana_cost": "{1}",
                "types": ["Creature"],
                "power": 1,
                "toughness": 1,
                "abilities": [
                    {
                        "kind": "static",
                        "effect": "buff",
                        "affects": {"self_only": True},
                        "power": value,
                        "toughness": value,
                    }
                ],
            }
        )

    def test_you_loads(self):
        compile_card(self._card({"greatest_commander_mana_value": "you"}))

    def test_another_seat_is_refused(self):
        with pytest.raises(DslError, match="greatest_commander_mana_value"):
            compile_card(self._card({"greatest_commander_mana_value": "opponent"}))
