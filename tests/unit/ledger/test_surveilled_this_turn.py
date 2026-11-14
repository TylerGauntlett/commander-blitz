"""Which cards in a graveyard were put there by a surveil this turn.

    "You may play lands and cast spells from among cards in your graveyard
    **you've surveilled this turn**."                     -- Eye of Duskmantle

`EventType.SURVEILLED` says how many cards a surveil binned and never which, so
no selector or permission could ask the question. The fact is recorded per card
by `zones.move_object`, beside Banon's `graveyard_turn` and `graveyard_from`: the
move's own `cause`, which the `surveil` op writes as ``"surveil"``. Without it a
permission reading "your graveyard" would free a card milled, discarded or
killed on any turn.

What would be wrong without each piece:

- **Only the surveil's own cards.** A card milled, or one the surveil left on
  top, is in the same graveyard or library and was not surveilled.
- **A new object is not surveilled** (400.7). A card that leaves the graveyard
  and comes back by another route arrives afresh, and its arrival overwrites
  the record.
- **This turn only.** The mark is compared against the turn rather than
  cleared, `drawn_this_turn`'s way, so a card binned last turn no longer reads
  as surveilled.
- **The permissions read it per object**: `cast_from_graveyard` through
  `graveyard_cast_arrival_ok` and `play_lands_from_graveyard` through
  `graveyard_land_play_allows`, so a narrowed permission frees the surveilled
  card and nothing else in the yard.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.selectors import matches
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import move_object
from tests.conftest import pass_until, settle

SCAVENGER = "t_surveil_scavenger"
CRUCIBLE = "t_surveil_crucible"
BEAR = "t_bear"
SURVEILLED = {"zone": "graveyard", "controller": "you", "surveilled_this_turn": True}


def position(builder, *, mine=(), library=(BEAR, BEAR, BEAR)):
    """Player 0 holding priority in their main phase.

    The Forest in hand is a land drop, so the engine stops there with priority
    rather than passing on to combat, and the board's lines can be read.
    """
    return (
        builder(players=2)
        .battlefield(0, ["forest"] * 4 + list(mine))
        .hand(0, ["forest"])
        .library(0, list(library) + ["plains"] * 10)
        .library(1, ["plains"] * 10)
        .build()
    )


def next_turn(game, turns: int = 1) -> None:
    """Run the game on until ``turns`` more turns have begun."""
    turn = game.state.turn
    pass_until(game, lambda g: g.state.turn >= turn + turns, limit=800 * turns)


def surveil(game, amount: int, *, bin_count: int) -> list[int]:
    """Resolve one surveil by player 0, binning the top ``bin_count`` cards."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=None)
    gen = OPS["surveil"](ctx, {"op": "surveil", "amount": {"const": amount}})
    send = None
    binned: list[int] = []
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return binned
        assert decision.kind is not DecisionKind.MAY
        binned = list(game.state.players[0].library[:bin_count])
        send = list(range(bin_count))


def mill(game, count: int) -> list[int]:
    state = game.state
    oids = list(state.players[0].library[:count])
    for oid in oids:
        move_object(state, oid, Zone.GRAVEYARD, to_player=0, cause="mill")
    return oids


def surveilled(game) -> list[int]:
    ctx = EffectContext(state=game.state, controller=0)
    return [
        oid
        for oid in game.state.players[0].graveyard
        if matches(ctx, oid, SURVEILLED, default_zone=None)
    ]


def castable(game) -> list[int]:
    return [a.source for a in game.legal_actions() if a.kind is ActionKind.CAST]


def land_drops(game) -> list[int]:
    return [a.source for a in game.legal_actions() if a.kind is ActionKind.PLAY_LAND]


class TestOnlyTheSurveilsCardsMatch:
    def test_a_binned_card_matches(self, builder):
        game = position(builder)
        binned = surveil(game, 2, bin_count=2)
        assert len(binned) == 2
        assert sorted(surveilled(game)) == sorted(binned)

    def test_a_card_left_on_top_does_not(self, builder):
        """Looked at by the surveil and kept: still in the library."""
        game = position(builder)
        binned = surveil(game, 2, bin_count=1)
        assert surveilled(game) == binned

    def test_a_milled_card_does_not(self, builder):
        """The whole distinction: the same graveyard, a different cause."""
        game = position(builder)
        milled = mill(game, 2)
        assert set(game.state.players[0].graveyard) >= set(milled)
        assert surveilled(game) == []


class TestANewObjectIsNotSurveilled:
    def test_a_card_that_left_and_came_back(self, builder):
        """400.7: back in the graveyard by a discard, it was surveilled by nobody."""
        game = position(builder)
        (oid,) = surveil(game, 1, bin_count=1)
        move_object(game.state, oid, Zone.HAND, to_player=0, cause="test")
        assert surveilled(game) == []
        move_object(game.state, oid, Zone.GRAVEYARD, to_player=0, cause="discard")
        assert surveilled(game) == []

    def test_one_surveilled_again_is_surveilled(self, builder):
        """The record is of the latest arrival, whatever came before."""
        game = position(builder)
        (oid,) = mill(game, 1)
        move_object(game.state, oid, Zone.LIBRARY, to_player=0, to_top=True, cause="test")
        assert surveil(game, 1, bin_count=1) == [oid]
        assert surveilled(game) == [oid]


class TestTheMarkIsSelfClearing:
    def test_a_card_surveilled_last_turn_no_longer_matches(self, builder):
        game = position(builder)
        binned = surveil(game, 1, bin_count=1)
        assert surveilled(game) == binned
        next_turn(game)
        assert surveilled(game) == []


class TestTheCastPermissionReadsIt:
    def test_a_surveilled_spell_is_castable(self, builder):
        game = position(builder, mine=(SCAVENGER,))
        (oid,) = surveil(game, 1, bin_count=1)
        assert castable(game) == [oid]

    def test_a_milled_one_is_not(self, builder):
        game = position(builder, mine=(SCAVENGER,))
        mill(game, 1)
        assert castable(game) == []

    def test_it_is_still_once_per_turn(self, builder):
        """The narrowing is beside the rate limit, not instead of it."""
        game = position(builder, mine=(SCAVENGER,))
        first, second = surveil(game, 2, bin_count=2)
        assert sorted(set(castable(game))) == sorted([first, second])
        game.apply(next(a for a in game.legal_actions() if a.source == first))
        settle(game)
        assert game.state.objects[first].zone is Zone.BATTLEFIELD
        assert game.state.objects[second].zone is Zone.GRAVEYARD
        assert second not in castable(game), "the permission is spent for the turn"


class TestTheLandPermissionReadsIt:
    def test_a_surveilled_land_is_playable(self, builder):
        game = position(builder, mine=(CRUCIBLE,), library=("forest",))
        (oid,) = surveil(game, 1, bin_count=1)
        assert oid in land_drops(game)

    def test_a_milled_land_is_not(self, builder):
        game = position(builder, mine=(CRUCIBLE,), library=("forest",))
        (oid,) = mill(game, 1)
        assert oid not in land_drops(game)

    def test_nor_once_the_turn_is_over(self, builder):
        game = position(builder, mine=(CRUCIBLE,), library=("forest",))
        (oid,) = surveil(game, 1, bin_count=1)
        next_turn(game, 2)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        assert oid not in land_drops(game)


def _static(**overrides) -> CardModel:
    static = {
        "kind": "static",
        "text": "You may cast spells from among cards in your graveyard you've surveilled this turn.",
        "effect": "cast_from_graveyard",
        "affects_player": "you",
        "affects_spells": {"not_types": ["Land"]},
        "static_max_per_turn": 1,
        "surveilled_this_turn": True,
    }
    for key, value in overrides.items():
        if value is None:
            static.pop(key, None)
        else:
            static[key] = value
    return CardModel.model_validate(
        {
            "id": "t_bad_surveil_permission",
            "name": "Test Bad Surveil Permission",
            "oracle_text": static["text"],
            "mana_cost": "{2}{U}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [static],
        }
    )


class TestTheLoader:
    def test_it_compiles_onto_the_permission(self):
        card = compile_card(_static(), source="test")
        assert card.abilities[0].static["surveilled_this_turn"] is True

    def test_it_is_refused_on_a_static_that_does_not_read_it(self):
        with pytest.raises(DslError, match="surveilled_this_turn"):
            compile_card(
                _static(
                    effect="cast_from_library_top",
                    pay_life_instead=True,
                    affects_spells=None,
                    static_max_per_turn=None,
                ),
                source="test",
            )

    def test_it_is_refused_on_a_cards_own_permission(self):
        """Gravecrawler's shape frees only the card carrying it."""
        with pytest.raises(DslError, match="surveilled_this_turn"):
            compile_card(
                _static(
                    active_zones=["graveyard"],
                    affects_spells=None,
                    static_max_per_turn=None,
                ),
                source="test",
            )
