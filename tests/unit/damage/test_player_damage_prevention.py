"""Absorb over a player -- "If a creature would deal damage to you, prevent 1 of
that damage."

Orbs of Warding and Heart-Shaped Herb are the witnesses. 615.1: a static
prevention shield that subtracts N from **each** damage event dealt to the
player and lets the rest through, narrowed by what is dealing it -- "a
creature", "a source an opponent controls".

Three near misses, each a different card:

* the `prevent_damage` *op* is a Fog: it stops all damage to the seat for the
  turn and then is gone;
* "prevent the next N damage" (615.7) is a one-shot pool that drains, which
  `docs/rules-coverage.md` lists as not implemented -- this shield never
  drains, and every hit loses N;
* `prevent_all_but` caps each event at N rather than subtracting N, so a
  1-damage ping lands under it and is prevented here.

So it is the `prevent_damage` static's absorb with the recipient moved from a
permanent (`affects`) to a seat (`affects_player`), and the dealer named by the
`damage_source` filter `replace_damage` already reads. Pinned below:

1. Per event, never a pool: every hit loses 1, and a hit of 1 is gone.
2. Only the named seat, and only the named dealer. Orbs reads the dealer's
   current characteristics, so an animated Vehicle is a creature and a burn
   spell is not; the Herb's "a source an opponent controls" reaches the spell.
3. Prevented damage was never dealt: lifelink gains the reduced number, and
   `DAMAGE_PREVENTED` carries the 1.
4. Prevention comes before doubling (616.1, the protected player's order).
5. The loader refuses the shapes nothing reads.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.actions import ActionKind
from commanderblitz.engine.enums import Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import animate, damage_permanent, damage_player
from tests.conftest import only_oid, settle, static_probe

HERB = "t_heart_herb"  # "a source an opponent controls ... to you, prevent 1"
ORBS = "t_orbs_of_warding"  # "a creature ... to you, prevent 1"
BEAR = "t_bear"  # a 2/2
LIFELINKER = "t_lifelinker"  # a 2/2 with lifelink
VEHICLE = "t_vehicle"  # a noncreature artifact until crewed
DOUBLER = "t_damage_doubler"  # Furnace of Rath's shape


def position(builder, mine=(), theirs=(BEAR,)):
    """Player 0 has ``mine``; player 1 has ``theirs``. Main phase, nothing on the stack."""
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(0)
        .step(Step.UNTAP)
        .build()
    )


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


def prevented(game, mark: int) -> list[int]:
    return [
        e.data["amount"]
        for e in game.state.events[mark:]
        if e.type == "damage_prevented" and e.data.get("reason") == "prevent_damage"
    ]


class TestEachEventLosesN:
    def test_a_creature_hit_loses_one(self, builder):
        game = position(builder, [ORBS])
        before = life(game)
        assert damage_player(game.state, 0, 3, only_oid(game, BEAR, 1)) == 2
        assert life(game) == before - 2

    def test_a_hit_of_one_is_gone(self, builder):
        """The difference from `prevent_all_but`: the ping does not land."""
        game = position(builder, [ORBS])
        before = life(game)
        assert damage_player(game.state, 0, 1, only_oid(game, BEAR, 1)) == 0
        assert life(game) == before

    def test_it_never_drains(self, builder):
        """The difference from "prevent the next N": every hit, all game."""
        game = position(builder, [ORBS])
        bear = only_oid(game, BEAR, 1)
        before = life(game)
        for _ in range(3):
            damage_player(game.state, 0, 2, bear)
        assert life(game) == before - 3

    def test_two_shields_stack(self, builder):
        game = position(builder, [ORBS, HERB])
        before = life(game)
        damage_player(game.state, 0, 3, only_oid(game, BEAR, 1))
        assert life(game) == before - 1

    def test_without_the_shield_nothing_is_prevented(self, builder):
        game = position(builder)
        before = life(game)
        damage_player(game.state, 0, 3, only_oid(game, BEAR, 1))
        assert life(game) == before - 3


class TestOnlyTheNamedSeat:
    def test_the_opponent_is_not_shielded(self, builder):
        game = position(builder, [ORBS, BEAR])
        before = life(game, 1)
        damage_player(game.state, 1, 3, only_oid(game, BEAR, 0))
        assert life(game, 1) == before - 3

    def test_your_creatures_are_not_shielded(self, builder):
        """"…to you" names a player; a permanent you control is not you."""
        game = position(builder, [ORBS, BEAR])
        assert damage_permanent(game.state, only_oid(game, BEAR, 0), 1, only_oid(game, BEAR, 1)) == 1


class TestOnlyTheNamedDealer:
    def test_orbs_does_not_stop_a_noncreature_permanent(self, builder):
        game = position(builder, [ORBS], [VEHICLE])
        before = life(game)
        damage_player(game.state, 0, 3, only_oid(game, VEHICLE, 1))
        assert life(game) == before - 3

    def test_orbs_stops_the_vehicle_once_it_is_a_creature(self, builder):
        """"A creature" is asked of the dealer as it deals the damage."""
        game = position(builder, [ORBS], [VEHICLE])
        vehicle = only_oid(game, VEHICLE, 1)
        animate(game.state, vehicle, 4, 4)
        before = life(game)
        damage_player(game.state, 0, 3, vehicle)
        assert life(game) == before - 2

    def test_orbs_stops_your_own_creature(self, builder):
        """"A creature", not "a creature an opponent controls"."""
        game = position(builder, [ORBS, BEAR])
        before = life(game)
        damage_player(game.state, 0, 2, only_oid(game, BEAR, 0))
        assert life(game) == before - 1

    def test_the_herb_does_not_stop_your_own_source(self, builder):
        game = position(builder, [HERB, BEAR])
        before = life(game)
        damage_player(game.state, 0, 2, only_oid(game, BEAR, 0))
        assert life(game) == before - 2

    def test_unsourced_damage_matches_no_dealer(self, builder):
        game = position(builder, [HERB])
        before = life(game)
        damage_player(game.state, 0, 2, None)
        assert life(game) == before - 2


def bolt_player_zero(builder, mine):
    """Player 1 casts a 3-damage Bolt at player 0, who has ``mine``."""
    game = (
        builder(players=2)
        .battlefield(0, list(mine))
        .hand(1, ["t_bolt"])
        .battlefield(1, ["mountain"])
        .library(0, ["forest"] * 10)
        .library(1, ["forest"] * 10)
        .active(1)
        .build()
    )
    before = life(game)
    cast = next(
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and repr(a).endswith("-> P0)")
    )
    game.apply(cast)
    settle(game)
    return before - life(game)


class TestASpellIsASource:
    def test_the_herb_stops_an_opponents_burn_spell(self, builder):
        """109.5: "a source an opponent controls" is the spell on the stack too."""
        assert bolt_player_zero(builder, [HERB]) == 2

    def test_orbs_does_not_stop_a_burn_spell(self, builder):
        assert bolt_player_zero(builder, [ORBS]) == 3


class TestPreventedDamageWasNeverDealt:
    def test_lifelink_gains_what_landed(self, builder):
        game = position(builder, [ORBS], [LIFELINKER])
        theirs = life(game, 1)
        damage_player(game.state, 0, 2, only_oid(game, LIFELINKER, 1))
        assert life(game, 1) == theirs + 1

    def test_the_prevention_event_carries_the_one(self, builder):
        game = position(builder, [ORBS])
        mark = len(game.state.events)
        damage_player(game.state, 0, 3, only_oid(game, BEAR, 1))
        assert prevented(game, mark) == [1]
        dealt = [e.data["amount"] for e in game.state.events[mark:] if e.type == "damage_dealt"]
        assert dealt == [2]


class TestPreventionComesBeforeDoubling:
    def test_three_doubled_after_one_is_prevented_is_four(self, builder):
        """616.1: the protected player orders the two, and prevents first --
        doubling first and then preventing would let 5 through."""
        game = position(builder, [ORBS], [BEAR, DOUBLER])
        before = life(game)
        damage_player(game.state, 0, 3, only_oid(game, BEAR, 1))
        assert life(game) == before - 4


def load(static: dict) -> None:
    compile_card(CardModel.model_validate(static_probe(static)))


class TestTheLoaderRefusesAGuess:
    def test_the_orbs_line_loads(self):
        load(
            {
                "effect": "prevent_damage",
                "amount": 1,
                "affects_player": "you",
                "damage_source": {"controller": "any", "types": ["Creature"]},
            }
        )

    def test_a_recipient_is_required(self):
        with pytest.raises(DslError, match="whose damage is prevented"):
            load({"effect": "prevent_damage", "amount": 1})

    def test_prevent_all_over_a_player_is_refused(self):
        with pytest.raises(DslError, match="not 'prevent_all'"):
            load({"effect": "prevent_damage", "prevent_all": True, "affects_player": "you"})

    def test_a_dealer_beside_a_permanent_recipient_is_refused(self):
        with pytest.raises(DslError, match="only for damage to a player"):
            load(
                {
                    "effect": "prevent_damage",
                    "amount": 1,
                    "affects_player": "you",
                    "affects": {"controller": "you", "types": ["Creature"]},
                    "damage_source": {"controller": "opponent"},
                }
            )

    def test_an_unknown_dealer_key_is_refused(self):
        with pytest.raises(DslError, match="unsupported keys"):
            load(
                {
                    "effect": "prevent_damage",
                    "amount": 1,
                    "affects_player": "you",
                    "damage_source": {"targeting": "you"},
                }
            )

    def test_a_dealer_on_another_static_is_still_refused(self):
        with pytest.raises(DslError, match="also on a prevent_damage static"):
            load(
                {
                    "effect": "prevent_all_but",
                    "amount": 1,
                    "affects_player": "you",
                    "damage_source": {"controller": "opponent"},
                }
            )
