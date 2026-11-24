"""Waste Management -- "exile up to two target cards **from a single graveyard**".

A rule between the picks, the inverse of `one_per_player`: every chosen card
lies in the same graveyard, which is its owner's (404.2), so every pick shares
an owner. No selector clause can say it -- each is evaluated against one
candidate in isolation -- and each nearer spelling is a different card:

* without the rule, the two cards may come from two graveyards (one from each
  opponent, which a graveyard-hate spell printed this way never allows);
* a sibling ``player`` target naming the graveyard adds an unprinted "target
  player", which player hexproof stops and which changes when the spell
  fizzles;
* a fixed ``controller`` of "you" or "opponent" drops half the legal choices.

601.2c: a choice is legal only if every chosen card shares a graveyard, so two
cards from different graveyards are never offered together, two from one are,
one card alone always is, and "up to" includes none. 608.2b re-checks each
target's zone on resolution; ownership never changes (108.3), so the survivors
still share a graveyard and there is nothing more to re-check.
"""

from __future__ import annotations

import copy

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.targeting import enumerate_target_tuples
from tests.conftest import settle

SWEEP = "t_single_grave_sweep"
LOOSE = "t_any_grave_sweep"
PAIR = "t_single_grave_pair"


def board(builder, *, mine=("forest", "forest"), theirs=("mountain", "mountain"), players=2):
    game = (
        builder(players=players)
        .battlefield(0, ["swamp"] * 2)
        .hand(0, [SWEEP, PAIR])
        .library(0, ["swamp"] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
    )
    if mine:
        game = game.graveyard(0, list(mine))
    for pid in range(1, players):
        game = game.library(pid, ["swamp"] * 10)
        if theirs:
            game = game.graveyard(pid, list(theirs))
    game = game.build()
    return game, next(o.oid for o in game.state.objects.values() if o.def_id == SWEEP)


def offers(game, card: str = SWEEP) -> list[tuple]:
    spec = game.state.registry.get(card).targets
    return enumerate_target_tuples(game.state, 0, spec, None, limit=10_000)


def owners(game, combo) -> set[int]:
    return {game.state.objects[ref.id].owner for ref in combo}


class TestTheChoiceSharesAGraveyard:
    def test_two_from_different_graveyards_are_not_offered(self, builder):
        game, _ = board(builder)
        assert all(len(owners(game, combo)) <= 1 for combo in offers(game))

    def test_two_from_one_graveyard_are_offered(self, builder):
        game, _ = board(builder)
        pairs = [combo for combo in offers(game) if len(combo) == 2]
        assert {next(iter(owners(game, combo))) for combo in pairs} == {0, 1}

    def test_one_card_alone_is_offered(self, builder):
        game, _ = board(builder)
        singles = [combo for combo in offers(game) if len(combo) == 1]
        assert len(singles) == 4

    def test_up_to_allows_zero(self, builder):
        game, _ = board(builder)
        assert () in offers(game)
        assert offers(game)[-1] == ()

    def test_the_largest_choice_comes_first(self, builder):
        game, _ = board(builder)
        assert len(offers(game)[0]) == 2

    def test_one_card_in_each_graveyard_offers_singles_only(self, builder):
        game, _ = board(builder, mine=("forest",), theirs=("mountain",))
        assert {len(combo) for combo in offers(game)} == {0, 1}

    def test_across_a_pod_every_pair_is_from_one_seat(self, builder):
        game, _ = board(builder, players=4)
        pairs = [combo for combo in offers(game) if len(combo) == 2]
        # One pair per graveyard: two cards each, four graveyards.
        assert len(pairs) == 4
        assert all(len(owners(game, combo)) == 1 for combo in pairs)


class TestTheCounterfactual:
    def test_without_the_rule_a_mixed_pair_is_offered(self, builder):
        game, _ = board(builder)
        assert any(len(owners(game, combo)) == 2 for combo in offers(game, LOOSE))


class TestTheExactCount:
    def test_only_pairs_from_one_graveyard(self, builder):
        game, _ = board(builder)
        combos = offers(game, PAIR)
        assert combos and all(len(c) == 2 and len(owners(game, c)) == 1 for c in combos)

    def test_no_graveyard_holding_two_offers_nothing(self, builder):
        """601.2c: one card in each graveyard is not two from a single one, so
        the spell cannot be cast."""
        game, _ = board(builder, mine=("forest",), theirs=("mountain",))
        assert offers(game, PAIR) == []


class TestTheSpellResolves:
    def test_the_two_picked_are_exiled(self, builder):
        game, sweep = board(builder)
        # A rule between the picks keeps the whole tuple on the cast line
        # (`TargetSpec.constrains_the_set`); the first is the largest.
        game.apply(
            next(
                a
                for a in game.legal_actions()
                if a.kind is ActionKind.CAST and a.source == sweep and len(a.targets) == 2
            )
        )
        settle(game)
        exiled = [
            o for o in game.state.objects.values() if o.zone is Zone.EXILE and o.oid != sweep
        ]
        assert len(exiled) == 2
        assert len({o.owner for o in exiled}) == 1


CARD = {
    "id": "t_single_grave_probe",
    "name": "Test Single Grave Probe",
    "oracle_text": "Exile up to two target cards from a single graveyard.",
    "mana_cost": "{1}",
    "types": ["Sorcery"],
    "targets": [
        {
            "id": "t1",
            "kind": "card_in_graveyard",
            "count": 2,
            "up_to": True,
            "single_graveyard": True,
            "selector": {"zone": "graveyard", "controller": "any"},
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
        assert target.single_graveyard and target.up_to and target.constrains_the_set

    def test_an_exact_pair_loads_optional_or_not(self):
        assert _compile(up_to=None).targets[0].count == 2
        assert _compile(up_to=None, optional=True).targets[0].optional

    def test_one_card_is_refused(self):
        """One card is always from a single graveyard."""
        with pytest.raises(DslError, match="single_graveyard"):
            _compile(up_to=None, count=1)

    def test_a_permanent_target_is_refused(self):
        with pytest.raises(DslError, match="single_graveyard"):
            _compile(kind="permanent", selector={"controller": "any"})

    def test_with_one_per_player_is_refused(self):
        with pytest.raises(DslError, match="contradict"):
            _compile(one_per_player=True)
