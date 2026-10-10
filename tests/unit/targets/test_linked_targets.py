"""Cloak and Dagger, Entwined — "target opponent and up to one target creature
**they** control".

    When Cloak and Dagger enter, choose target opponent and up to one target
    creature they control. They reveal their hand. You may exile a nonland card
    from their hand or the chosen creature until Cloak and Dagger leave the
    battlefield.

One target spec reading another spec's answer. The *language* was already there
— `{"controller": {"target": "who"}}` is an ordinary player spec, and
`select_players` has always understood `{"target": ...}`. Two things stopped it.

**The loader refused it by construction.** A target's own `controller` clause
was validated with no siblings in scope, so any card that named one was told the
target did not exist.

**And the enumeration could not have answered it.** Every spec's candidates were
computed independently and multiplied at the end, so the second spec resolved
`{"target": "who"}` against a spec with no answer yet: no seats, no candidates,
and a card whose second target could never be chosen. 601.2c is the way out and
is also the reason the clause is legal at all — every target is chosen at once,
so what is legal is the **pair**. The combinations are grown one spec at a time
and a linked spec is enumerated per partial combination, against the opponent
that branch actually picked.

Only a linked spec pays for that; an independent one is enumerated once and
reused, which is the shape of every card in the pool but this one.

608.2b asks the same question again on resolution, so `filter_legal` hands each
spec the buckets already settled — and a creature that changes controller in
response stops being one "they" control.

`t_loose_dagger` is the counterfactual: the same two targets with no link, which
happily pairs one opponent with another opponent's creature.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.structs import TargetRef
from commanderblitz.engine.targeting import enumerate_target_tuples, filter_legal
from tests.conftest import only_oid

DAGGER = "t_dagger"
LOOSE = "t_loose_dagger"
BEAR = "t_bear"
DORK = "t_dork"


def table(builder, card: str = DAGGER):
    """Three seats, and each opponent controls a different creature."""
    return (
        builder(players=3)
        .battlefield(0, [card])
        .battlefield(0, ["swamp"] * 2)
        .battlefield(1, [BEAR])
        .battlefield(2, [DORK])
        .library(0, ["forest"] * 10)
        .build(advance=False)
    )


def pairs(game, card: str = DAGGER):
    """Every (seat, creature) combination the ability offers, as card ids."""
    state = game.state
    specs = state.registry.get(card).abilities[0].targets
    source = only_oid(game, card)
    out = []
    for tuple_ in enumerate_target_tuples(state, 0, specs, source):
        who = next(r.id for r in tuple_ if r.kind == "player")
        what = [state.card(r.id).id for r in tuple_ if r.kind == "object"]
        out.append((who, what[0] if what else None))
    return sorted(out, key=lambda p: (p[0], p[1] or ""))


class TestTheSecondTargetFollowsTheFirst:
    def test_each_opponent_is_paired_only_with_their_own_creature(self, builder):
        game = table(builder)
        assert pairs(game) == [(1, None), (1, BEAR), (2, None), (2, DORK)]

    def test_the_other_opponents_creature_is_never_offered(self, builder):
        """The whole clause: "…a creature **they** control"."""
        game = table(builder)
        assert (1, DORK) not in pairs(game)
        assert (2, BEAR) not in pairs(game)

    def test_without_the_link_every_creature_pairs_with_every_seat(self, builder):
        """The counterfactual, and a strictly wider card."""
        game = table(builder, LOOSE)
        offered = pairs(game, LOOSE)
        assert (1, DORK) in offered
        assert (2, BEAR) in offered

    def test_declining_the_creature_is_still_offered(self, builder):
        """"**up to** one target creature" -- and it is offered for a seat that
        has one, not only for a seat that has none."""
        game = table(builder)
        assert (1, None) in pairs(game)

    def test_an_opponent_with_no_creature_still_offers_the_seat(self, builder):
        game = (
            builder(players=3)
            .battlefield(0, [DAGGER])
            .battlefield(0, ["swamp"] * 2)
            .battlefield(1, [BEAR])
            .library(0, ["forest"] * 10)
            .build(advance=False)
        )
        assert (2, None) in pairs(game)


class TestItIsRecheckedOnResolution:
    def test_the_pair_survives_while_it_still_holds(self, builder):
        game = table(builder)
        state = game.state
        specs = state.registry.get(DAGGER).abilities[0].targets
        bear = only_oid(game, BEAR)
        refs = (TargetRef.player(1), TargetRef.obj(bear))
        buckets, remains = filter_legal(state, 0, specs, refs, only_oid(game, DAGGER))
        assert remains
        assert buckets["what"] == (TargetRef.obj(bear),)

    def test_a_creature_that_changed_hands_is_dropped(self, builder):
        """608.2b, and the half `filter_legal` needed the settled buckets for:
        the question is "is this still a creature **they** control"."""
        game = table(builder)
        state = game.state
        specs = state.registry.get(DAGGER).abilities[0].targets
        bear = only_oid(game, BEAR)
        state.objects[bear].controller = 2
        buckets, _ = filter_legal(state, 0, specs, (TargetRef.player(1), TargetRef.obj(bear)), None)
        assert buckets["what"] == ()
        assert buckets["who"] == (TargetRef.player(1),)


def _linked(**overrides):
    targets = [
        {"id": "who", "kind": "player", "count": 1, "selector": {"controller": "opponent"}},
        {
            "id": "what",
            "kind": "permanent",
            "count": 1,
            "selector": {"types": ["Creature"], "controller": {"target": "who"}},
        },
    ]
    targets = overrides.pop("targets", targets)
    return CardModel.model_validate(
        {
            "id": "t_link_probe",
            "name": "Test Link Probe",
            "oracle_text": "Destroy target creature.",
            "mana_cost": "{1}{B}",
            "types": ["Sorcery"],
            "targets": targets,
            "spell_effects": [{"op": "destroy", "objects": {"target": "what"}}],
            **overrides,
        }
    )


class TestTheLoaderChecksTheLink:
    def test_naming_an_earlier_sibling_loads(self):
        compile_card(_linked(), source="test")

    def test_naming_a_later_one_is_refused(self):
        """The combinations grow in declaration order, so the answer it needs
        would not exist yet -- and a spec offering nothing looks on the board
        like a target that simply cannot be chosen."""
        targets = [
            {
                "id": "what",
                "kind": "permanent",
                "count": 1,
                "selector": {"types": ["Creature"], "controller": {"target": "who"}},
            },
            {"id": "who", "kind": "player", "count": 1, "selector": {"controller": "opponent"}},
        ]
        with pytest.raises(DslError, match="declared after it"):
            compile_card(_linked(targets=targets), source="test")

    def test_naming_a_target_that_does_not_exist_is_refused(self):
        targets = [
            {"id": "who", "kind": "player", "count": 1, "selector": {"controller": "opponent"}},
            {
                "id": "what",
                "kind": "permanent",
                "count": 1,
                "selector": {"types": ["Creature"], "controller": {"target": "nobody"}},
            },
        ]
        with pytest.raises(DslError, match="does not declare"):
            compile_card(_linked(targets=targets), source="test")

    def test_naming_a_permanent_target_as_a_player_is_still_refused(self):
        """The check that was already there, and still is: a permanent is never
        a player, and `controller_of_target` is the key that means it."""
        targets = [
            {"id": "who", "kind": "permanent", "count": 1, "selector": {"types": ["Creature"]}},
            {
                "id": "what",
                "kind": "permanent",
                "count": 1,
                "selector": {"types": ["Creature"], "controller": {"target": "who"}},
            },
        ]
        with pytest.raises(DslError, match="never a player"):
            compile_card(_linked(targets=targets), source="test")
