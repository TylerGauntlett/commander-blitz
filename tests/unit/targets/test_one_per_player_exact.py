"""Run Away Together -- "choose **two** target creatures **controlled by
different players**. Return those creatures to their owners' hands."

An exact size and a rule between the picks. 601.2c chooses both targets at
once, so what is legal is the *pair*: the spell can be cast only while two
creatures with different controllers exist, and it never offers two of one
player's. `one_per_player` on a literal `count` of 2 says exactly that; the
near misses are each a different card:

* `count: 2, up_to: true` casts at zero or one creature;
* one spec `controller: "you"` and one `controller: "opponent"` cannot reach
  two different opponents' creatures in a pod.

608.2b re-checks each target as the spell resolves, and "controlled by a
different player" is part of what made each one legal. When one creature
changes controller to match the other, the restriction fails from both sides
and the game keeps no record of which one moved, so both are illegal and the
spell does nothing (`targeting._drop_shared_controllers`).
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from tests.conftest import oids_of, pass_until

SPELL = "t_run_away"
BEAR = "t_bear"


def board(builder, *, bears: dict[int, int], players: int = 2, held: bool = False):
    """The spell in player 0's hand, ``bears[pid]`` bears for each seat.

    ``held`` hands player 0 a second copy and the mana for it, so after the
    first is cast player 0 still has something to do and the engine stops on
    the stack instead of auto-passing it through -- a window to change the
    board in before the first copy resolves.
    """
    copies = 2 if held else 1
    game = (
        builder(players=players)
        .battlefield(0, ["island"] * 2 * copies)
        .hand(0, [SPELL] * copies)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
    )
    for pid in range(players):
        game = game.library(pid, ["island"] * 10)
        if bears.get(pid):
            game = game.battlefield(pid, [BEAR] * bears[pid])
    return game.build()


def casts(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == SPELL
    ]


def seats(game, action) -> list[int]:
    return [game.state.objects[ref.id].controller for ref in action.targets]


def resolve(game) -> None:
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def in_hand(game) -> list[int]:
    return [
        o.oid
        for o in game.state.objects.values()
        if o.def_id == BEAR and o.zone is Zone.HAND
    ]


class TestCastability:
    def test_one_players_creatures_cannot_be_targeted(self, builder):
        """Two bears, one controller: no pair passes, so no cast (601.2c)."""
        assert casts(board(builder, bears={1: 2})) == []

    def test_one_creature_is_not_a_pair(self, builder):
        assert casts(board(builder, bears={1: 1})) == []

    def test_two_players_creatures_make_it_castable(self, builder):
        game = board(builder, bears={0: 1, 1: 1})
        offers = casts(game)
        assert offers
        assert all(sorted(seats(game, a)) == [0, 1] for a in offers)


class TestNoTwoShareAController:
    def test_two_of_one_players_are_never_offered(self, builder):
        game = board(builder, bears={0: 2, 1: 2})
        offers = casts(game)
        assert len(offers) == 4  # every cross pair, and no same-seat pair
        for action in offers:
            assert len(action.targets) == 2
            assert len(set(seats(game, action))) == 2

    def test_a_three_player_pod_offers_cross_opponent_pairs(self, builder):
        """The pair two fixed you/opponent specs cannot make."""
        game = board(builder, bears={1: 1, 2: 1}, players=3)
        offers = casts(game)
        assert [sorted(seats(game, a)) for a in offers] == [[1, 2]]


class TestResolution:
    def test_both_are_returned(self, builder):
        game = board(builder, bears={0: 1, 1: 1})
        game.apply(casts(game)[0])
        resolve(game)
        assert len(in_hand(game)) == 2
        owners = {game.state.objects[oid].owner for oid in in_hand(game)}
        assert owners == {0, 1}

    def test_a_shared_controller_on_resolution_makes_both_illegal(self, builder):
        """608.2b: the opponent's bear changes control to player 0 in response.
        Neither target is now controlled by a different player than the other,
        so neither is returned and the spell does nothing."""
        game = board(builder, bears={0: 1, 1: 1}, held=True)
        game.apply(casts(game)[0])
        (theirs,) = oids_of(game, BEAR, 1)
        game.state.objects[theirs].controller = 0
        resolve(game)
        assert in_hand(game) == []
        bears = [o for o in game.state.objects.values() if o.def_id == BEAR]
        assert all(o.zone is Zone.BATTLEFIELD for o in bears)

    def test_a_target_that_left_does_not_spoil_the_other(self, builder):
        """One target gone is one illegal target; the other still returns."""
        game = board(builder, bears={0: 1, 1: 1}, held=True)
        game.apply(casts(game)[0])
        (mine,) = oids_of(game, BEAR, 0)
        game.state.objects[mine].zone = Zone.GRAVEYARD
        resolve(game)
        assert [game.state.objects[oid].owner for oid in in_hand(game)] == [1]


CARD = {
    "id": "t_run_away_probe",
    "name": "Test Run Away Probe",
    "oracle_text": "Choose two target creatures controlled by different players. Return those creatures to their owners' hands.",
    "mana_cost": "{1}{U}",
    "types": ["Instant"],
    "targets": [
        {
            "id": "t1",
            "kind": "permanent",
            "count": 2,
            "one_per_player": True,
            "selector": {"zone": "battlefield", "types": ["Creature"], "controller": "any"},
        }
    ],
    "spell_effects": [{"op": "return_to_hand", "objects": {"target": "t1"}}],
}


def _compile(**overrides):
    card = copy.deepcopy(CARD)
    card["targets"][0].update(overrides)
    return compile_card(CardModel.model_validate(card))


class TestTheLoader:
    def test_an_exact_count_of_two_loads(self):
        target = _compile().targets[0]
        assert target.one_per_player and target.count == 2 and not target.up_to

    def test_one_target_is_refused(self):
        with pytest.raises(DslError, match="one_per_player"):
            _compile(count=1)

    def test_exactly_n_or_none_is_refused(self):
        with pytest.raises(DslError, match="one_per_player"):
            _compile(optional=True)

    def test_a_computed_exact_count_is_refused(self):
        with pytest.raises(DslError, match="one_per_player"):
            _compile(count={"x": True})
