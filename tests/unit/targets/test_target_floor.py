""""One, two, or three target creature cards." -- `min_count` under `up_to`

    Aberrant Return -- "Put **one, two, or three** target creature cards from
    graveyards onto the battlefield under your control. Each of them enters
    with an additional -1/-1 counter on it."

601.2c: a spell that requires targets cannot be cast without them, and the
number is the card's. "Up to three" is zero to three, so `up_to` alone would
let the sorcery be cast with no creature card in any graveyard and resolve
doing nothing; a fixed `count: 3` takes exactly three and never lets the caster
choose one or two. `min_count: 1` is the floor between them: every size from
one through three, never zero, and no cast at all with nothing to target.

The floor holds on every path a variable-size spec is declared through: the
enumerator's subsets (`targeting._spec_options`), a spell's mid-cast pick
(`casting.deferred_target_spec` / `Game._ask_deferred_targets`) and a triggered
ability's pick (`stack._choose_each_target`).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.targeting import enumerate_target_tuples
from tests.conftest import declare_targets, settle

SPELL = "t_one_two_or_three_return"
RECALL = "t_one_or_two_recall"
BEAR = "t_bear"


def board(builder, mine: int = 0, theirs: int = 0, hand=(SPELL,)):
    return (
        builder(players=2)
        .battlefield(0, ["swamp"] * 6)
        .graveyard(0, [BEAR] * mine)
        .graveyard(1, [BEAR] * theirs)
        .hand(0, list(hand))
        .library(0, ["swamp"] * 20)
        .library(1, ["swamp"] * 20)
        .step(Step.PRECOMBAT_MAIN)
        .active(0)
        .build()
    )


def casts(game, card_id: str = SPELL) -> list:
    return [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]


def bears_in_graveyards(game) -> list[int]:
    return [
        oid
        for pid in (0, 1)
        for oid in game.state.players[pid].graveyard
        if game.state.objects[oid].def_id == BEAR
    ]


def tuples(game) -> list:
    """The enumerator's subsets for the spec, undeferred -- what a trigger or
    an activated ability with the same spec would be offered."""
    oid = next(o.oid for o in game.state.objects.values() if o.def_id == SPELL)
    return enumerate_target_tuples(game.state, 0, game.state.card(oid).targets, oid)


class TestTheFloorIsACastingCondition:
    def test_no_creature_card_in_any_graveyard_means_no_cast(self, builder):
        """601.2c: the near miss `up_to` alone would offer this line."""
        assert casts(board(builder)) == []

    def test_one_creature_card_is_enough(self, builder):
        assert len(casts(board(builder, theirs=1))) == 1

    def test_plain_up_to_would_have_offered_it(self, builder):
        """The contrast that makes the floor the whole capability."""
        game = board(builder)
        oid = next(o.oid for o in game.state.objects.values() if o.def_id == SPELL)
        spec = replace(game.state.card(oid).targets[0], min_count=0)
        assert enumerate_target_tuples(game.state, 0, [spec], oid) == [()]


class TestTheCastAsksForOneToThree:
    def test_the_pick_is_one_to_three(self, builder):
        game = board(builder, mine=2, theirs=3)
        game.apply(casts(game)[0])
        decision = game.pending()
        assert decision.kind is DecisionKind.CHOOSE_OBJECTS
        assert decision.context["purpose"] == "target"
        assert (decision.min_count, decision.max_count) == (1, 3)
        assert len(decision.options) == 5

    def test_it_cannot_be_finished_with_none(self, builder):
        game = board(builder, mine=2, theirs=3)
        game.apply(casts(game)[0])
        kinds = {a.kind for a in game.legal_actions()}
        assert ActionKind.FINISH_DECLARATION not in kinds

    def test_one_may_be_chosen_when_three_are_there(self, builder):
        """What a fixed `count: 3` cannot say."""
        game = board(builder, theirs=3)
        game.apply(casts(game)[0])
        chosen = bears_in_graveyards(game)[0]
        declare_targets(game, chosen)
        settle(game)
        assert game.state.objects[chosen].zone is Zone.BATTLEFIELD
        assert len(bears_in_graveyards(game)) == 2

    def test_a_lone_candidate_is_taken_without_asking(self, builder):
        """Floor and ceiling meet at one: there is nothing to choose."""
        game = board(builder, theirs=1)
        (only,) = bears_in_graveyards(game)
        game.apply(casts(game)[0])
        settle(game)
        assert game.state.objects[only].zone is Zone.BATTLEFIELD


class TestWhatItDoes:
    def test_they_enter_under_your_control_with_a_counter(self, builder):
        game = board(builder, mine=1, theirs=2)
        game.apply(casts(game)[0])
        picked = bears_in_graveyards(game)
        declare_targets(game, *picked)
        settle(game)
        for oid in picked:
            obj = game.state.objects[oid]
            assert obj.zone is Zone.BATTLEFIELD
            assert obj.controller == 0
            assert obj.counter("-1/-1") == 1


class TestTheEnumeratorHonoursTheFloor:
    def test_sizes_three_two_one_and_never_none(self, builder):
        sizes = sorted(len(t) for t in tuples(board(builder, theirs=3)))
        assert sizes == [1, 1, 1, 2, 2, 2, 3]

    def test_largest_first(self, builder):
        assert len(tuples(board(builder, theirs=3))[0]) == 3

    def test_no_candidates_is_no_tuple(self, builder):
        assert tuples(board(builder)) == []


class TestATriggerHonoursTheFloor:
    """"When this enters, return one or two target creature cards" -- the
    triggered path, `stack._choose_each_target`."""

    def test_the_pick_is_one_to_two(self, builder):
        game = board(builder, mine=3, hand=(RECALL,))
        game.apply(casts(game, RECALL)[0])
        for _ in range(20):
            decision = game.pending()
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                break
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.PASS))
        assert (decision.min_count, decision.max_count) == (1, 2)
        assert ActionKind.FINISH_DECLARATION not in {a.kind for a in game.legal_actions()}

    def test_with_nothing_to_target_it_is_never_put_on_the_stack(self, builder):
        game = board(builder, hand=(RECALL,))
        game.apply(casts(game, RECALL)[0])
        settle(game)
        recall = next(o for o in game.state.objects.values() if o.def_id == RECALL)
        assert recall.zone is Zone.BATTLEFIELD
        assert game.state.stack == []


class TestTheLoaderRefusesNonsense:
    def _card(self, **target):
        spec = {
            "id": "t1",
            "kind": "card_in_graveyard",
            "selector": {"types": ["Creature"], "zone": "graveyard"},
            **target,
        }
        return CardModel.model_validate(
            {
                "id": "t_bad_target_floor",
                "name": "Bad Target Floor",
                "oracle_text": "Bad.",
                "mana_cost": "{B}",
                "colors": ["B"],
                "color_identity": ["B"],
                "types": ["Sorcery"],
                "targets": [spec],
                "spell_effects": [
                    {"op": "return_from_graveyard", "objects": {"target": "t1"},
                     "destination": "hand"}
                ],
            }
        )

    def test_one_two_or_three_loads(self):
        card = compile_card(self._card(count=3, up_to=True, min_count=1))
        assert card.targets[0].min_count == 1

    def test_a_floor_without_up_to_is_refused(self):
        """Without `up_to` the count is already exact."""
        with pytest.raises(DslError, match="min_count"):
            compile_card(self._card(count=3, min_count=1))

    def test_a_floor_at_the_ceiling_is_refused(self):
        """"Two or two" is `count: 2`."""
        with pytest.raises(DslError, match="min_count"):
            compile_card(self._card(count=2, up_to=True, min_count=2))

    def test_a_floor_over_a_computed_ceiling_is_refused(self):
        with pytest.raises(DslError, match="min_count"):
            compile_card(self._card(count={"x": True}, up_to=True, min_count=1))

    def test_a_negative_floor_is_refused(self):
        with pytest.raises(DslError, match="min_count"):
            compile_card(self._card(count=3, up_to=True, min_count=-1))
