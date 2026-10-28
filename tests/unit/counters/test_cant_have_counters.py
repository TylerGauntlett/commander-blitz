"""Counters that can't be put on at all.

    "Creatures you control can't have -1/-1 counters put on them."
                                -- Darksteel Angel, Melira, Sylvok Outcast

A prohibition, not a replacement (101.2: "can't" beats every "can"). The
placement simply does not happen: nothing is written, no `counter_placed`
fires, and -- because nothing "would be put" -- no counter replacement sees
it either, so Hardened Scales cannot turn zero -1/-1 counters into one.

`replace_counters` could not say it: its multiplier is refused below 2,
because "no counters are put on" is a different and stronger sentence than
"twice that many". So the check is its own static, asked by
`player_statics.counters_prohibited` at the three places a counter can reach a
permanent:

- `primitives.add_counters`, the funnel for every effect, wither and infect
  damage, proliferate and a cost's counters;
- `zones._entering_counters`, every "enters with" (persist's and undying's
  returns among them -- the creature comes back with nothing on it);
- `costs.can_pay`: Melira's ruling, "if a cost includes putting a -1/-1
  counter on a creature you control, you can't pay that cost", so the ability
  is not offered.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import add_counters, damage_permanent
from commanderblitz.engine.zones import move_object
from tests.conftest import activations, only_oid, two_seat_board

WARD = "t_chc_ward"  # "Creatures you control can't have -1/-1 counters put on them."
BEAR = "t_chc_bear"
WITHERED = "t_chc_withered"  # a 4/4 that enters with two -1/-1 counters
SHRINKER = "t_chc_shrinker"  # "Put a -1/-1 counter on this creature: gain 1 life."
ROCK = "t_chc_rock"  # a noncreature artifact
SCALES = "t_rc_scales"  # Hardened Scales, "that many plus one" +1/+1
SEASON = "t_rc_season"  # Doubling Season over every kind
WITHERER = "t_witherer"  # a 2/2 with wither
INFECTER = "t_infecter"  # a 2/2 with infect


def counters(game, oid: int, kind: str = "-1/-1") -> int:
    return game.state.objects[oid].counter(kind)


def placed(game, mark: int) -> list:
    return [e for e in game.state.events[mark:] if e.type == "counter_placed"]


def arrive(game, card_id: str, pid: int = 0) -> int:
    """Put ``pid``'s ``card_id`` from hand onto the battlefield by `move_object`."""
    oid = next(
        o for o in game.state.players[pid].hand if game.state.objects[o].def_id == card_id
    )
    move_object(game.state, oid, Zone.BATTLEFIELD, to_player=pid)
    return oid


class TestNothingIsPut:
    def test_an_effect_puts_none_on(self, builder):
        game = two_seat_board(builder, mine=[WARD, BEAR])
        bear = only_oid(game, BEAR)
        mark = len(game.state.events)
        assert add_counters(game.state, bear, "-1/-1", 2) == 0
        assert counters(game, bear) == 0
        assert placed(game, mark) == [], "a placement that did not happen fired nothing"

    def test_the_control(self, builder):
        game = two_seat_board(builder, mine=[BEAR])
        bear = only_oid(game, BEAR)
        add_counters(game.state, bear, "-1/-1", 1)
        assert counters(game, bear) == 1

    def test_no_replacement_turns_nothing_into_something(self, builder):
        """Doubling Season doubles a placement; there is none to double."""
        game = two_seat_board(builder, mine=[WARD, SEASON, BEAR])
        bear = only_oid(game, BEAR)
        add_counters(game.state, bear, "-1/-1", 1)
        assert counters(game, bear) == 0


class TestTheFilters:
    def test_another_kind_is_untouched(self, builder):
        """It names -1/-1, and +1/+1 counters (with Hardened Scales) arrive."""
        game = two_seat_board(builder, mine=[WARD, SCALES, BEAR])
        bear = only_oid(game, BEAR)
        add_counters(game.state, bear, "+1/+1", 1)
        assert counters(game, bear, "+1/+1") == 2

    def test_a_noncreature_is_untouched(self, builder):
        game = two_seat_board(builder, mine=[WARD, ROCK])
        rock = only_oid(game, ROCK)
        add_counters(game.state, rock, "-1/-1", 1)
        assert counters(game, rock) == 1

    def test_an_opponents_creature_is_untouched(self, builder):
        game = two_seat_board(builder, mine=[WARD], theirs=[BEAR])
        bear = only_oid(game, BEAR)
        add_counters(game.state, bear, "-1/-1", 1)
        assert counters(game, bear) == 1

    def test_it_wears_off_with_its_source(self, builder):
        game = two_seat_board(builder, mine=[WARD, BEAR])
        bear = only_oid(game, BEAR)
        move_object(game.state, only_oid(game, WARD), Zone.GRAVEYARD)
        add_counters(game.state, bear, "-1/-1", 1)
        assert counters(game, bear) == 1


class TestDamage:
    def test_wither_damage_is_dealt_and_puts_nothing_on(self, builder):
        """Melira's ruling: the damage is still dealt, as -1/-1 counters that
        can't be put on -- so the creature ends with neither marked damage
        nor counters, and the dealt amount is still reported."""
        game = two_seat_board(builder, mine=[WARD, BEAR], theirs=[WITHERER])
        bear = only_oid(game, BEAR)
        dealt = damage_permanent(game.state, bear, 2, only_oid(game, WITHERER))
        assert dealt == 2
        assert counters(game, bear) == 0
        assert game.state.objects[bear].damage == 0

    def test_infect_damage_too(self, builder):
        game = two_seat_board(builder, mine=[WARD, BEAR], theirs=[INFECTER])
        bear = only_oid(game, BEAR)
        damage_permanent(game.state, bear, 2, only_oid(game, INFECTER))
        assert counters(game, bear) == 0


class TestEntersWith:
    def test_it_enters_without_them(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WARD])
            .hand(0, [WITHERED])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        mark = len(game.state.events)
        hulk = arrive(game, WITHERED)
        assert counters(game, hulk) == 0
        assert placed(game, mark) == []

    def test_the_control(self, builder):
        game = (
            builder(players=2)
            .hand(0, [WITHERED])
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        hulk = arrive(game, WITHERED)
        assert counters(game, hulk) == 2


class TestACostThatWouldPutOne:
    def _position(self, builder, board):
        game = (
            builder(players=2)
            .battlefield(0, [*board, SHRINKER])
            .library(0, ["forest"] * 20)
            .library(1, ["forest"] * 20)
            .step(Step.PRECOMBAT_MAIN)
            .build(advance=False)
        )
        game._advance()
        return game, only_oid(game, SHRINKER, 0)

    def test_it_cannot_be_paid(self, builder):
        """Melira's ruling: the ability is not offered at all."""
        game, oid = self._position(builder, [WARD])
        assert activations(game, oid) == []

    def test_the_control(self, builder):
        game, oid = self._position(builder, [])
        assert activations(game, oid)


class TestTheLoaderPlacesIt:
    def _card(self, **extra):
        static = {
            "kind": "static",
            "text": "Creatures you control can't have -1/-1 counters put on them.",
            "effect": "cant_have_counters",
            **extra,
        }
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": static["text"],
                "mana_cost": "{W}",
                "types": ["Enchantment"],
                "abilities": [static],
            }
        )

    def test_the_printed_shape_loads(self):
        card = compile_card(
            self._card(counter="-1/-1", affects={"controller": "you", "types": ["Creature"]})
        )
        static = card.abilities[0].static
        assert static["effect"] == "cant_have_counters"
        assert static["counter"] == "-1/-1"
        assert static["affects"] == {"controller": "you", "types": ["Creature"]}

    def test_affects_is_required(self):
        with pytest.raises(DslError, match="affects"):
            compile_card(self._card(counter="-1/-1"))

    def test_counter_is_required(self):
        with pytest.raises(DslError, match="counter"):
            compile_card(self._card(affects={"controller": "you", "types": ["Creature"]}))
