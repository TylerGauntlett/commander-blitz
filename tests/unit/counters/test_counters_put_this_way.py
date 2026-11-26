"""Binding how many counters an `add_counters` actually put.

    Guinan, Ancient Advisor -- "{1}, {T}: Put a +1/+1 counter on each creature
    you control that entered this turn. **If you put two or more +1/+1
    counters on creatures this way**, draw a card."

"This way" is the placement's own record (608.2c reads back what the earlier
part of the effect did), and it is a count of **counters**, not of creatures.
Counting the creatures that entered this turn agrees with the printed card only
while nothing modifies the placement: one arrival under Hardened Scales gets two
counters (614.1a, a replacement) and should draw, and an arrival that can't have
+1/+1 counters put on it (101.2, a prohibition) gets none and should not count.

So `as` on `add_counters` binds the total `primitives.add_counters` returned
across every recipient -- after every replacement, zero for a forbidden one --
as an int that the following `if` reads with ``{"binding": …}``, the shape
`lose_life` and `remove_counters` already use for "this way". The witness is
Guinan's ability, written on `t_cptw_advisor` exactly as a card author would.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, oids_of, only_oid, plus_one_counters, settle

ADVISOR = "t_cptw_advisor"  # Guinan's ability
WARD = "t_cptw_ward"  # "Walls you control can't have +1/+1 counters put on them."
WALL = "t_cptw_wall"  # the Wall it reaches
BEAR = "t_rc_bear"  # a plain creature
SCALES = "t_rc_scales"  # Hardened Scales, "that many plus one" +1/+1
SEASON = "t_rc_season"  # Doubling Season over every kind


def position(builder, arrivals=(), board=()):
    """The advisor, ``board`` and two Forests for player 0, in a main phase,
    with each of ``arrivals`` moved from hand onto the battlefield this turn.

    Returns ``(game, advisor, arrived)``.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 2 + [ADVISOR, *board])
        .hand(0, list(arrivals))
        .library(0, ["forest"] * 20)
        .library(1, ["forest"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    arrived = []
    for card_id in arrivals:
        oid = next(
            o
            for o in game.state.players[0].hand
            if game.state.objects[o].def_id == card_id
        )
        arrived.append(move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0).oid)
    return game, only_oid(game, ADVISOR, 0), arrived


def activate(game, advisor: int) -> int:
    """Activate and resolve the ability; return how many cards it drew."""
    before = len(game.state.players[0].hand)
    game.apply(activations(game, advisor)[0])
    settle(game)
    return len(game.state.players[0].hand) - before


class TestTheCountIsOfCounters:
    def test_one_arrival_puts_one_and_draws_nothing(self, builder):
        game, advisor, (bear,) = position(builder, [BEAR])
        assert activate(game, advisor) == 0
        assert plus_one_counters(game, bear) == 1

    def test_two_arrivals_put_two_and_draw(self, builder):
        game, advisor, (a, b) = position(builder, [BEAR, BEAR])
        assert activate(game, advisor) == 1
        assert plus_one_counters(game, a) == plus_one_counters(game, b) == 1

    def test_a_creature_already_here_is_not_an_arrival(self, builder):
        game, advisor, (arrival,) = position(builder, [BEAR], board=[BEAR])
        (resident,) = [oid for oid in oids_of(game, BEAR, 0) if oid != arrival]
        assert activate(game, advisor) == 0
        assert plus_one_counters(game, arrival) == 1
        assert plus_one_counters(game, resident) == plus_one_counters(game, advisor) == 0

    def test_nothing_entered_puts_none_and_draws_nothing(self, builder):
        game, advisor, _ = position(builder)
        assert activate(game, advisor) == 0


class TestReplacementsAreCounted:
    def test_one_arrival_under_hardened_scales_puts_two_and_draws(self, builder):
        game, advisor, (bear,) = position(builder, [BEAR], board=[SCALES])
        assert activate(game, advisor) == 1
        assert plus_one_counters(game, bear) == 2

    def test_one_arrival_under_doubling_season_puts_two_and_draws(self, builder):
        game, advisor, (bear,) = position(builder, [BEAR], board=[SEASON])
        assert activate(game, advisor) == 1
        assert plus_one_counters(game, bear) == 2


class TestAForbiddenPlacementCountsNothing:
    def test_a_wall_that_cant_have_counters_does_not_count(self, builder):
        game, advisor, (bear, wall) = position(builder, [BEAR, WALL], board=[WARD])
        assert activate(game, advisor) == 0
        assert plus_one_counters(game, bear) == 1
        assert plus_one_counters(game, wall) == 0

    def test_the_control_two_unwarded_arrivals_draw(self, builder):
        game, advisor, _ = position(builder, [BEAR, WALL])
        assert activate(game, advisor) == 1


def _probe(effect: dict) -> CardModel:
    return CardModel.model_validate(
        {
            "id": "t_add_counters_as_probe",
            "name": "Test Add Counters As Probe",
            "oracle_text": "Put a +1/+1 counter on each creature you control.",
            "mana_cost": "{G}",
            "types": ["Sorcery"],
            "spell_effects": [effect],
        }
    )


_EACH = {"zone": "battlefield", "controller": "you", "types": ["Creature"]}


class TestTheLoader:
    def test_as_is_accepted(self):
        compile_card(
            _probe({"op": "add_counters", "objects": _EACH, "as": "put"}), source="test"
        )

    @pytest.mark.parametrize("name", [3, "", None])
    def test_a_non_name_as_is_refused(self, name):
        with pytest.raises(DslError, match="'as' must be a non-empty binding name"):
            compile_card(
                _probe({"op": "add_counters", "objects": _EACH, "as": name}), source="test"
            )
