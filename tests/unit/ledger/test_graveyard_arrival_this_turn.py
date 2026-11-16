"""How a card reached a graveyard this turn: discarded, milled, or from a zone.

    "…choose up to one target card in a graveyard that was **discarded or put
    there from a library this turn**."              -- Ghost of Ramirez DePietro
    "…cast a spell from among cards in your graveyard that were **milled this
    turn**."                                        -- Raul, Trouble Shooter

Every card's latest arrival is already recorded on the object by
`zones.move_object` -- `graveyard_turn`, `graveyard_from` and the move's
`graveyard_cause` -- and `surveilled_this_turn` read one cause off it.
`graveyard_arrival_this_turn` reads the rest: a list of ways, any one enough.

What would be wrong without each piece:

- **The action, not only the zone.** Milling (701.13) and putting a card there
  from a library are different sets: a surveil bins a library card and milled
  nothing, so Raul must not see it while Ghost must. Banon's zone-only
  `arrived_this_turn_from` cannot tell them apart.
- **The discard action, not "from a hand".** `discarded` reads the cause the
  discard primitive writes.
- **This turn only, and this object only** (400.7): a card binned last turn, or
  one that left and came back by another route, answers for its latest arrival.
- **Any graveyard** when the selector says so: Ghost's target is "a graveyard".
- **The permission reads it per object**, so Raul frees the milled card and
  nothing else in the yard.
"""

from __future__ import annotations

import pytest

from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches, validate_selector
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.primitives import discard_cards, mill_cards
from commanderblitz.engine.zones import move_object
from tests.conftest import oids_of, pass_until

RAUL = "raul_trouble_shooter"
BEAR = "t_bear"
INSTANT = "t_plain_instant"
GHOSTS = {
    "zone": "graveyard",
    "controller": "any",
    "graveyard_arrival_this_turn": ["discarded", "from_library"],
}
MILLED = {"zone": "graveyard", "controller": "any", "graveyard_arrival_this_turn": ["milled"]}


def position(builder, *, mine=(), hand=(), library=(BEAR, BEAR)):
    return (
        builder(players=2)
        .battlefield(0, ["plains"] * 4 + list(mine))
        .hand(0, [*hand, "forest"])
        .library(0, list(library) + ["plains"] * 10)
        .library(1, [BEAR] + ["plains"] * 10)
        .build()
    )


def matching(game, selector) -> set[int]:
    ctx = EffectContext(state=game.state, controller=0)
    return {
        oid
        for p in game.state.players
        for oid in p.graveyard
        if matches(ctx, oid, selector, default_zone=None)
    }


def in_hand(game, card_id: str) -> list[int]:
    return [oid for oid in game.state.players[0].hand if game.state.objects[oid].def_id == card_id]


def castable(game) -> set[int]:
    return {a.source for a in game.legal_actions() if a.kind is ActionKind.CAST}


class TestTheWays:
    def test_a_discarded_card_is_ghosts_and_not_milled(self, builder):
        game = position(builder, hand=[BEAR])
        (oid,) = discard_cards(game.state, 0, in_hand(game, BEAR))
        assert matching(game, GHOSTS) == {oid}
        assert matching(game, MILLED) == set()

    def test_a_milled_card_is_both(self, builder):
        game = position(builder)
        (oid,) = mill_cards(game.state, 0, 1)
        assert matching(game, GHOSTS) == {oid}
        assert matching(game, MILLED) == {oid}

    def test_a_card_binned_from_the_library_otherwise_is_ghosts_not_milled(self, builder):
        """A surveil's card: put there from a library, and milled by nobody."""
        game = position(builder)
        oid = game.state.players[0].library[0]
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="surveil")
        assert matching(game, GHOSTS) == {oid}
        assert matching(game, MILLED) == set()

    def test_a_creature_that_died_is_neither(self, builder):
        game = position(builder, mine=[BEAR])
        (oid,) = oids_of(game, BEAR, 0)
        move_object(game.state, oid, Zone.GRAVEYARD, cause="test")
        assert matching(game, GHOSTS) == set()
        assert matching(game, {**GHOSTS, "graveyard_arrival_this_turn": ["from_battlefield"]}) == {
            oid
        }

    def test_an_opponents_graveyard_is_a_graveyard(self, builder):
        game = position(builder)
        (oid,) = mill_cards(game.state, 1, 1)
        assert matching(game, GHOSTS) == {oid}
        assert matching(game, {**GHOSTS, "controller": "you"}) == set()


class TestThisArrivalOnly:
    def test_last_turns_mill_no_longer_matches(self, builder):
        game = position(builder)
        mill_cards(game.state, 0, 1)
        turn = game.state.turn
        pass_until(game, lambda g: g.state.turn > turn, limit=800)
        assert matching(game, MILLED) == set()

    def test_a_card_that_left_and_came_back_answers_for_its_new_arrival(self, builder):
        """400.7: milled, returned to hand, then put there from the hand by a test move."""
        game = position(builder)
        (oid,) = mill_cards(game.state, 0, 1)
        move_object(game.state, oid, Zone.HAND, to_player=0, cause="test")
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="test")
        assert matching(game, GHOSTS) == set()
        assert matching(game, MILLED) == set()


class TestRaulsPermission:
    def test_a_milled_spell_is_castable(self, builder):
        game = position(builder, mine=[RAUL], library=(INSTANT,))
        (oid,) = mill_cards(game.state, 0, 1)
        assert oid in castable(game)

    def test_a_discarded_one_is_not(self, builder):
        game = position(builder, mine=[RAUL], hand=[INSTANT])
        (oid,) = discard_cards(game.state, 0, in_hand(game, INSTANT))
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert oid not in castable(game)

    def test_a_surveilled_one_is_not(self, builder):
        game = position(builder, mine=[RAUL], library=(INSTANT,))
        oid = game.state.players[0].library[0]
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="surveil")
        assert oid not in castable(game)

    def test_not_during_an_opponents_turn(self, builder):
        """"Once during each of **your** turns": an instant milled on theirs stays put."""
        game = position(builder, mine=[RAUL], library=(INSTANT,))
        pass_until(
            game,
            lambda g: g.state.active_player == 1
            and g.pending() is not None
            and g.pending().player == 0,
            limit=800,
        )
        (oid,) = mill_cards(game.state, 0, 1)
        assert oid not in castable(game)


class TestTheLoaderRefuses:
    @pytest.mark.parametrize("ways", [[], "milled", ["exiled"], ["from_graveyard"], True])
    def test_a_way_that_is_not_one(self, ways):
        with pytest.raises(DslError, match="graveyard_arrival_this_turn"):
            validate_selector({"zone": "graveyard", "graveyard_arrival_this_turn": ways}, "t")

    def test_a_selector_outside_the_graveyard(self):
        with pytest.raises(DslError, match="graveyard_arrival_this_turn"):
            validate_selector(
                {"zone": "battlefield", "graveyard_arrival_this_turn": ["milled"]}, "t"
            )
