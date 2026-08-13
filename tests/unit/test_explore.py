"""Explore — rule 701.40a, and the one branch a condition cannot express.

    Merfolk Branchwalker — "When this creature enters, it explores. (Reveal the
    top card of your library. Put that card into your hand if it's a land.
    Otherwise, put a +1/+1 counter on this creature, then put that card back on
    top of your library or into your graveyard.)"

The reason this is an op and not a `reveal` beside an `if` is the test in the
middle: it asks about **the card that was just revealed**, and the condition
language has no name for it. The nearest a card could get is `{"exists":
{"zone": "library", "types": ["Land"]}}` — "is there a land somewhere in my
deck" — which is true in essentially every game a Branchwalker is played in, so
the card would take the land branch every time and quietly draw a card instead
of growing. That failure loads cleanly and looks right on the board, which is
what these tests exist to catch.

Three properties are asserted because each is silent when wrong:

- **The counter goes on the exploring permanent**, which for "target creature
  you control explores" is not the ability's source.
- **Declining costs nothing.** The card stays on top, in order — 701.40a offers
  top *or* graveyard, and a version that binned it either way would be a
  strictly worse card than the printed one.
- **Each permanent explores separately**, so two exploring creatures reveal two
  cards rather than sharing one.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import ActionKind, DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.objects import PLUS_ONE
from tests.conftest import (
    action_for_card,
    count_on_battlefield,
    find_action,
    only_oid,
    pass_until,
)

FOREST = "forest"
BEAR = "t_bear"


def position(builder, library: list[str], creatures: int = 1):
    """A board with ``creatures`` bears and a stacked library."""
    game = (
        builder(players=2)
        .battlefield(0, [BEAR] * creatures)
        .library(0, library)
        .build()
    )
    oids = [obj.oid for obj in game.state.battlefield_objects(0)]
    return game, oids[0] if creatures == 1 else oids


def run(game, spec, source=None, *, bin_it: bool = False):
    """Drive the op to completion, answering every "…or graveyard?" the same way.

    Returns the decisions it asked, so a test can assert that it asked none.
    """
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = OPS["explore"](ctx, spec)
    asked, send = [], None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        if decision.kind is DecisionKind.MAY:
            send = [0] if bin_it else [1]
        else:
            send = list(range(len(decision.options)))


def library_ids(game, pid: int = 0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].library]


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(PLUS_ONE, 0)


SELF = {"op": "explore", "objects": {"zone": "battlefield", "self_only": True}}


class TestTheLandBranch:
    def test_a_land_on_top_goes_to_hand(self, builder):
        game, bear = position(builder, [FOREST, BEAR, BEAR])
        top = game.state.players[0].library[0]

        run(game, SELF, bear)

        assert game.state.objects[top].zone is Zone.HAND
        assert library_ids(game) == [BEAR, BEAR]

    def test_a_land_places_no_counter(self, builder):
        """The two halves are exclusive — 701.40a says "otherwise"."""
        game, bear = position(builder, [FOREST, BEAR])
        run(game, SELF, bear)
        assert counters(game, bear) == 0

    def test_a_land_asks_nothing(self, builder):
        """The choice belongs to the non-land branch only."""
        game, bear = position(builder, [FOREST, BEAR])
        assert run(game, SELF, bear) == []


class TestTheNonLandBranch:
    def test_a_nonland_places_one_counter(self, builder):
        game, bear = position(builder, [BEAR, FOREST])
        run(game, SELF, bear)
        assert counters(game, bear) == 1

    def test_declining_leaves_it_on_top_in_order(self, builder):
        game, bear = position(builder, [BEAR, FOREST, BEAR])
        top = game.state.players[0].library[0]

        run(game, SELF, bear, bin_it=False)

        assert game.state.objects[top].zone is Zone.LIBRARY
        assert library_ids(game) == [BEAR, FOREST, BEAR], "nothing moved or reordered"

    def test_accepting_puts_it_in_the_graveyard(self, builder):
        game, bear = position(builder, [BEAR, FOREST, BEAR])
        top = game.state.players[0].library[0]

        run(game, SELF, bear, bin_it=True)

        assert game.state.objects[top].zone is Zone.GRAVEYARD
        assert library_ids(game) == [FOREST, BEAR]

    def test_the_counter_is_placed_either_way(self, builder):
        """The counter is not what the graveyard is bought with."""
        game, bear = position(builder, [BEAR, FOREST])
        run(game, SELF, bear, bin_it=True)
        assert counters(game, bear) == 1


class TestWhichPermanentExplores:
    def test_only_the_permanent_the_selector_names_grows(self, builder):
        game, (first, second) = position(builder, [BEAR, FOREST], creatures=2)

        run(game, {"op": "explore", "objects": {"zone": "battlefield", "self_only": True}}, second)

        assert counters(game, second) == 1
        assert counters(game, first) == 0

    def test_two_permanents_reveal_two_cards(self, builder):
        """Each explores separately; they do not share one look."""
        game, (first, second) = position(builder, [BEAR, BEAR, FOREST], creatures=2)
        spec = {"op": "explore", "objects": {"zone": "battlefield", "controller": "you"}}

        asked = run(game, spec, first, bin_it=True)

        assert len(asked) == 2, "one question each"
        assert counters(game, first) == counters(game, second) == 1
        assert library_ids(game) == [FOREST], "two cards left the library"


class TestTheEmptyLibraryBoundary:
    def test_nothing_happens_with_no_cards_to_reveal(self, builder):
        """701.40b: no card revealed, so neither half of the instruction runs."""
        game, bear = position(builder, [])

        assert run(game, SELF, bear) == []
        assert counters(game, bear) == 0, "the counter is conditional on a card"


class TestThroughARealCard:
    """The op driven the way a card drives it, not by hand.

    Everything above builds an ``EffectContext`` directly, which cannot show
    that the op is *reachable*: an ETB trigger has to bind the right source, and
    the yes/no has to survive being suspended and answered through
    ``game.apply``. Both were free, and both would be silent if they were not.
    """

    def test_an_enters_trigger_explores_the_creature_that_entered(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [FOREST, FOREST])
            .hand(0, ["t_explorer"])
            .library(0, [BEAR, FOREST, BEAR])
            .build()
        )
        game.apply(action_for_card(game, ActionKind.CAST, "t_explorer"))
        pass_until(game, lambda g: count_on_battlefield(g, "t_explorer") == 1)

        explorer = only_oid(game, "t_explorer")
        # A Bear on top: the counter half, and the question that follows it.
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.MAY,
        )
        game.apply(find_action(game, ActionKind.NO))

        assert counters(game, explorer) == 1
        assert library_ids(game) == [BEAR, FOREST, BEAR], "declined, so nothing moved"

    def test_a_sorcery_grows_the_creature_it_targeted(self, builder):
        """The source is the spell, so a `self_only` default would grow nothing."""
        game = (
            builder(players=2)
            .battlefield(0, [FOREST, BEAR])
            .hand(0, ["t_explore_target"])
            .library(0, [BEAR, FOREST])
            .build()
        )
        bear = only_oid(game, BEAR)
        game.apply(action_for_card(game, ActionKind.CAST, "t_explore_target"))
        pass_until(
            game,
            lambda g: (d := g.pending()) is not None and d.kind is DecisionKind.MAY,
        )
        game.apply(find_action(game, ActionKind.YES))

        assert counters(game, bear) == 1, "the target explored, not the sorcery"
        assert library_ids(game) == [FOREST]


class TestTheLoaderGuard:
    def test_a_well_formed_effect_loads(self):
        _validate_effect(SELF, "test", set())

    def test_omitting_objects_is_refused(self):
        """Defaulted, it would read fine on a creature and do nothing on a sorcery."""
        with pytest.raises(DslError, match="explore needs 'objects'"):
            _validate_effect({"op": "explore"}, "test", set())
