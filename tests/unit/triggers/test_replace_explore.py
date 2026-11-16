"""Exploring twice -- the `replace_explore` static.

    Topography Tracker -- "If a creature you control would explore, instead it
    explores, then it explores again."

A replacement of an **action**, as `replace_proliferate` is. Explore (701.40a)
has no number in it, so "again" is the whole explore performed a second time:
a second reveal of the (new) top card, a second land to hand or counter and
choice, and a second `EXPLORED`, so "whenever a creature you control explores"
hears two. Revealing one card and applying its result twice would be a
different card -- it would grow the creature by two off one nonland and never
see the card beneath -- and an `explores` trigger would explore again on the
stack, after the first, and hear its own explore.

Unlike Tekuthal it names the explorer, so it is matched through `affects`
against the exploring permanent: an opponent's creature exploring is not
doubled, and the source's controller's creature is, whoever made it explore.
Two Trackers are two replacements of one event, each applying once (614.5) to
the events the other produced (616.1): one explore becomes four.

Read by the `explore` op through `player_statics.explore_times`; the witness
card is Topography Tracker.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import OPS
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.enums import DecisionKind, Step
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.player_statics import explore_times
from tests.conftest import only_oid, plus_one_counters

DOUBLER = "t_explore_doubler"
WATCHER = "t_explore_watcher"  # Whenever a creature you control explores, gain 1.
BEAR = "t_bear"
FOREST = "forest"

MY_BEARS = {"zone": "battlefield", "subtypes": ["Bear"], "controller": "you"}


def position(builder, library, *, mine=(DOUBLER, BEAR), theirs=(BEAR,)):
    return (
        builder(players=2)
        .battlefield(0, list(mine))
        .battlefield(1, list(theirs))
        .library(0, list(library))
        .library(1, [BEAR] * 10)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )


def explore(game, objects, *, controller=0, bin_it=False):
    """Resolve an explore op; every nonland is kept on top unless ``bin_it``."""
    ctx = EffectContext(state=game.state, controller=controller)
    gen = OPS["explore"](ctx, {"op": "explore", "objects": objects})
    send = None
    asked = 0
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        if decision.kind is DecisionKind.MAY:
            asked += 1
            send = [0] if bin_it else [1]
        else:
            send = list(range(decision.min_count))


def explores(game) -> list:
    return [e for e in game.state.events if e.type == EventType.EXPLORED]


def bear(game, pid=0) -> int:
    return only_oid(game, BEAR, pid)


def hand_ids(game, pid=0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].hand]


class TestItExploresTwice:
    def test_two_lands_are_two_reveals(self, builder):
        game = position(builder, [FOREST, FOREST, BEAR])
        explore(game, MY_BEARS)
        assert [e.data["land"] for e in explores(game)] == [True, True]
        assert hand_ids(game) == [FOREST, FOREST]
        assert plus_one_counters(game, bear(game)) == 0

    def test_a_kept_nonland_is_revealed_again(self, builder):
        """The second explore reveals the new top card: a nonland kept on top
        is that card again, so it is two counters and two choices."""
        game = position(builder, [BEAR, FOREST])
        assert explore(game, MY_BEARS) == 2
        assert [e.data["revealed"] for e in explores(game)] == [BEAR, BEAR]
        assert plus_one_counters(game, bear(game)) == 2

    def test_a_binned_nonland_uncovers_the_next_card(self, builder):
        game = position(builder, [BEAR, FOREST])
        explore(game, MY_BEARS, bin_it=True)
        assert [e.data["land"] for e in explores(game)] == [False, True]
        assert hand_ids(game) == [FOREST]
        assert plus_one_counters(game, bear(game)) == 1

    def test_without_it_is_once(self, builder):
        game = position(builder, [FOREST, FOREST], mine=(BEAR,))
        explore(game, MY_BEARS)
        assert len(explores(game)) == 1
        assert hand_ids(game) == [FOREST]

    def test_an_empty_library_is_still_two_explores(self, builder):
        """701.40b: each is an explore though nothing is revealed."""
        game = position(builder, [])
        explore(game, MY_BEARS)
        assert [e.data["land"] for e in explores(game)] == [None, None]

    def test_two_doublers_compound_to_four(self, builder):
        game = position(builder, [FOREST] * 5, mine=(DOUBLER, DOUBLER, BEAR))
        assert explore_times(game.state, bear(game)) == 4
        explore(game, MY_BEARS)
        assert len(explores(game)) == 4
        assert hand_ids(game) == [FOREST] * 4


class TestEachExploreIsHeard:
    def test_the_watcher_hears_both(self, builder):
        game = position(builder, [FOREST, BEAR], mine=(DOUBLER, WATCHER, BEAR))
        explore(game, MY_BEARS)
        queued = [
            t
            for t in game.state.pending_triggers
            if game.state.objects[t.source_oid].def_id == WATCHER
        ]
        assert len(queued) == 2


class TestWhoseExplore:
    def test_an_opponents_creature_is_not_doubled(self, builder):
        game = position(builder, [FOREST] * 3)
        explore(game, MY_BEARS, controller=1)
        assert len(explores(game)) == 1
        assert explore_times(game.state, bear(game, 1)) == 1

    def test_an_opponents_doubler_does_not_double_mine(self, builder):
        game = position(builder, [FOREST] * 3, mine=(BEAR,), theirs=(DOUBLER,))
        explore(game, MY_BEARS)
        assert len(explores(game)) == 1

    def test_it_leaves_the_battlefield_and_stops(self, builder):
        game = position(builder, [FOREST] * 3)
        game.state.battlefield.remove(only_oid(game, DOUBLER, 0))
        game.state.bump_chars()
        assert explore_times(game.state, bear(game)) == 1


class TestTheLoaderGuardsIt:
    def _model(self, **extra):
        ability = {
            "kind": "static",
            "text": "If a creature you control would explore, instead it explores, "
            "then it explores again.",
            "effect": "replace_explore",
            "affects": {"types": ["Creature"], "controller": "you"},
            **extra,
        }
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Probe",
                "oracle_text": ability["text"],
                "mana_cost": "{1}{G}",
                "types": ["Enchantment"],
                "abilities": [ability],
            }
        )

    def test_a_well_formed_static_loads(self):
        compile_card(self._model())

    def test_affects_is_required(self):
        with pytest.raises(DslError, match="replace_explore needs 'affects'"):
            compile_card(self._model(affects=None))

    def test_a_seat_is_refused(self):
        with pytest.raises(DslError, match="replace_explore needs"):
            compile_card(self._model(affects_player="you"))

    def test_an_amount_is_refused(self):
        with pytest.raises(DslError, match="replace_explore needs"):
            compile_card(self._model(amount=3))
