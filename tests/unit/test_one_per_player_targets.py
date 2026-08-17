""""For each player, exile up to one target nonland permanent that player controls."

    Unexplained Absence.

Written as a hand-authored pair of specs — one "up to one target permanent you
control", one "up to one an opponent controls" — this reproduces the card only
in a duel. In the four-player game it is printed for it silently offers two
targets instead of four. That is an approximation, not the card.

Written as **one** variable-size spec with a per-player cap, it is exactly the
printed line: "any number of target nonland permanents, no two controlled by the
same player" is the same set of legal choices as "for each player, up to one",
and it scales with the pod because the pod is what it counts.

**The shape is chosen to avoid a bug, not just for brevity.** One spec per seat
would have to be `optional`, and `filter_legal` splits the stored refs by
*position* — a declined optional contributes nothing to the flat tuple, so every
spec after it reads the wrong refs back on resolution. The spell would fizzle,
or exile the wrong permanent, depending on how many targets the caster happened
to decline. No board would show it. One spec that swallows whatever was chosen
cannot have that bug at all.

Built on `count: "any"`, so the ordering it settled applies here too: the
largest legal combination comes first (one from each player), and declining
entirely comes last.
"""

from __future__ import annotations

import copy

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, Step, Zone
from automtg.engine.errors import DslError
from tests.conftest import pass_until

SPELL = "t_one_each"
BEAR = "t_bear"

CARD = {
    "id": "t_one_each_probe",
    "name": "Test One Each Probe",
    "oracle_text": "For each player, exile up to one target nonland permanent that player controls.",
    "mana_cost": "{2}{W}",
    "types": ["Sorcery"],
    "targets": [
        {
            "id": "t1",
            "kind": "permanent",
            "count": "any",
            "one_per_player": True,
            "selector": {"not_types": ["Land"]},
        }
    ],
    "spell_effects": [{"op": "exile", "objects": {"target": "t1"}}],
}


def board(builder, *, players: int, each: int):
    game = (
        builder(players=players)
        .battlefield(0, ["plains"] * 5)
        .hand(0, [SPELL])
        .library(0, ["plains"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
    )
    for pid in range(players):
        game = game.battlefield(pid, [BEAR] * each)
    return game.build()


def casts(game) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == SPELL
    ]


def controllers(game, action) -> list[int]:
    return [game.state.objects[ref.id].controller for ref in action.targets]


class TestNoTwoShareAController:
    def test_every_offer_hits_distinct_players(self, builder):
        game = board(builder, players=2, each=3)
        for action in casts(game):
            seats = controllers(game, action)
            assert len(seats) == len(set(seats))

    def test_the_biggest_offer_is_one_per_seat(self, builder):
        """"For each player" -- so at a pod of four the ceiling is four, and it
        is four because there are four seats rather than because the card says
        a number."""
        game = board(builder, players=2, each=3)
        assert len(casts(game)[0].targets) == 2

    def test_a_third_seat_raises_the_ceiling(self, builder):
        """The whole point. A hand-authored pair of specs is fixed at two."""
        game = board(builder, players=3, each=3)
        assert len(casts(game)[0].targets) == 3
        assert len(set(controllers(game, casts(game)[0]))) == 3


class TestTheSizesInBetween:
    def test_hitting_only_one_player_is_legal(self, builder):
        """"Up to one" per player, so any seat may be skipped."""
        game = board(builder, players=3, each=1)
        assert any(len(a.targets) == 1 for a in casts(game))

    def test_declining_entirely_is_legal(self, builder):
        game = board(builder, players=3, each=1)
        assert any(len(a.targets) == 0 for a in casts(game))

    def test_declining_comes_last(self, builder):
        game = board(builder, players=3, each=1)
        assert len(casts(game)[-1].targets) == 0


class TestItResolves:
    def test_one_permanent_per_player_is_exiled(self, builder):
        game = board(builder, players=3, each=1)
        game.apply(casts(game)[0])
        pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)

        exiled = [
            o
            for o in game.state.objects.values()
            if o.zone is Zone.EXILE and o.def_id == BEAR
        ]
        assert len(exiled) == 3
        assert len({o.owner for o in exiled}) == 3


class TestLoadTimeGuards:
    def test_it_needs_a_variable_count(self):
        """On a fixed-size spec the cap either changes nothing or makes the
        spec unsatisfiable, and both are silent."""
        card = copy.deepcopy(CARD)
        card["targets"][0]["count"] = 2
        with pytest.raises(DslError, match="one_per_player"):
            compile_card(CardModel.model_validate(card))

    def test_with_any_it_loads(self):
        assert compile_card(CardModel.model_validate(CARD)).targets[0].one_per_player
