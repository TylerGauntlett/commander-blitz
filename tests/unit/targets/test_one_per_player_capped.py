"""Protector of the Wastes -- "exile **up to two** target artifacts and/or
enchantments **controlled by different players**".

Two facts about one set of targets: a ceiling the card prints, and no two of
them sharing a controller. Each nearer spelling is a different card:

* `count: "any"` with `one_per_player` takes the ceiling from the pod -- at a
  table of four the trigger exiles up to four permanents instead of two;
* `count: 2, up_to: true` without it lets both targets be one opponent's.

So `one_per_player` sits beside an `up_to` ceiling, and the subset enumeration
(`targeting._spec_options`) applies both: at most two, pairwise different
controllers, every size from none up. Checked as the targets are chosen
(601.2c, and 603.3d for a trigger). An exact count, or `optional`'s "exactly
N, or none", is still refused -- "one per player" caps a size the caster picks.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.targeting import enumerate_target_tuples
from tests.conftest import settle

GUARD = "t_wastes_guard"
TRINKET = "t_opp_trinket"
SIGIL = "t_opp_sigil"


def board(builder, *, players: int = 4):
    """The guard in player 0's hand; every other seat controls a trinket and
    a sigil."""
    game = (
        builder(players=players)
        .battlefield(0, ["plains"] * 2)
        .hand(0, [GUARD])
    )
    for pid in range(players):
        game = game.library(pid, ["plains"] * 10)
        if pid:
            game = game.battlefield(pid, [TRINKET, SIGIL])
    return game.build()


def spec(game):
    return game.state.registry.get(GUARD).abilities[0].targets


def offers(game) -> list[tuple]:
    return enumerate_target_tuples(game.state, 0, spec(game), None, limit=10_000)


def controllers(game, combo) -> list[int]:
    return [game.state.objects[ref.id].controller for ref in combo]


class TestBothRulesHold:
    def test_never_more_than_two(self, builder):
        """Three opponents with something each: "any number" would offer three."""
        assert max(len(combo) for combo in offers(board(builder))) == 2

    def test_never_two_of_one_players(self, builder):
        game = board(builder)
        for combo in offers(game):
            seats = controllers(game, combo)
            assert len(seats) == len(set(seats))

    def test_a_pair_across_two_players_is_offered(self, builder):
        game = board(builder)
        assert any(len(set(controllers(game, combo))) == 2 for combo in offers(game))

    def test_one_and_none_are_offered(self, builder):
        sizes = {len(combo) for combo in offers(board(builder))}
        assert sizes == {0, 1, 2}

    def test_one_opponent_alone_offers_one_at_most(self, builder):
        """Both of a lone opponent's permanents share a controller."""
        game = board(builder, players=2)
        assert max(len(combo) for combo in offers(game)) == 1


class TestTheTriggerResolves:
    def test_the_two_picked_are_exiled(self, builder):
        game = board(builder, players=3)
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == GUARD
            )
        )
        settle(game)
        decision = game.pending()
        while decision is not None and decision.kind is not DecisionKind.PRIORITY:
            # The trigger's targets: the first offer is the largest legal one.
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE))
            settle(game)
            decision = game.pending()
        exiled = [o for o in game.state.objects.values() if o.zone is Zone.EXILE]
        assert len(exiled) == 2
        assert len({o.owner for o in exiled}) == 2


CARD = {
    "id": "t_capped_probe",
    "name": "Test Capped Probe",
    "oracle_text": "Exile up to two target artifacts controlled by different players.",
    "mana_cost": "{1}",
    "types": ["Sorcery"],
    "targets": [
        {
            "id": "t1",
            "kind": "permanent",
            "count": 2,
            "up_to": True,
            "one_per_player": True,
            "selector": {"types": ["Artifact"], "controller": "any"},
        }
    ],
    "spell_effects": [{"op": "exile", "objects": {"target": "t1"}}],
}


def _compile(**overrides):
    card = copy.deepcopy(CARD)
    card["targets"][0].update(overrides)
    for key, value in list(card["targets"][0].items()):
        if value is None:
            del card["targets"][0][key]
    return compile_card(CardModel.model_validate(card))


class TestTheLoader:
    def test_an_up_to_ceiling_loads(self):
        target = _compile().targets[0]
        assert target.one_per_player and target.up_to and target.count == 2

    def test_an_exact_count_is_refused(self):
        """"Two target artifacts controlled by different players" is no
        ceiling for the rule to cap."""
        with pytest.raises(DslError, match="one_per_player"):
            _compile(up_to=None)

    def test_exactly_n_or_none_is_refused(self):
        with pytest.raises(DslError, match="one_per_player"):
            _compile(up_to=None, optional=True)
