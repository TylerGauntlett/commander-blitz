"""Connive — rule 701.47a, and the second op whose counter counts a discard.

    "Connive N. (Draw N cards, then discard N cards. Put a +1/+1 counter on this
    creature for each nonland card discarded this way.)"

`draw` and `discard` both exist, and a card written as the three of them plus
`add_counters` is the obvious spelling and the wrong one: nothing it could count
is "the cards discarded this way". `count` over the graveyard counts what was
already lying there, and `cards_to_graveyard_this_turn` counts every graveyard
at the table plus every earlier discard this turn. Both load and resolve, and
both grow the creature by a number that looks plausible on a board.

The clause the tests here are really guarding is **"nonland"**. Conniving away
two lands is the drawback the mechanic is priced around, so an implementation
that counted the discards rather than reading them would be a strictly better
card, and the difference only shows on the turn you had nothing but lands.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import _validate_effect
from automtg.engine.effects import OPS
from automtg.engine.effects.context import EffectContext
from automtg.engine.enums import DecisionKind, Zone
from automtg.engine.errors import DslError
from automtg.engine.objects import PLUS_ONE

FOREST = "forest"
BEAR = "t_bear"

SELF = {"op": "connive", "objects": {"zone": "battlefield", "self_only": True}}


def position(builder, hand: list[str], library: list[str], creatures: int = 1):
    game = (
        builder(players=2)
        .battlefield(0, [BEAR] * creatures)
        .hand(0, hand)
        .library(0, library)
        .build()
    )
    oids = [obj.oid for obj in game.state.battlefield_objects(0)]
    return game, (oids[0] if creatures == 1 else oids)


def run(game, spec, source=None, *, pitch: str | None = None):
    """Drive the op, discarding cards whose def_id is ``pitch`` where it can."""
    ctx = EffectContext(state=game.state, controller=0, source_oid=source)
    gen = OPS["connive"](ctx, spec)
    asked, send = [], None
    while True:
        try:
            decision = gen.send(send)
        except StopIteration:
            return asked
        asked.append(decision)
        if pitch is None:
            send = list(range(len(decision.options)))
            continue
        wanted = [
            i
            for i, option in enumerate(decision.options)
            if game.state.objects[option.value].def_id == pitch
        ]
        rest = [i for i in range(len(decision.options)) if i not in wanted]
        send = (wanted + rest)[: decision.max_count]


def counters(game, oid: int) -> int:
    return game.state.objects[oid].counters.get(PLUS_ONE, 0)


def hand_ids(game, pid: int = 0) -> list[str]:
    return [game.state.objects[o].def_id for o in game.state.players[pid].hand]


class TestTheDrawAndTheDiscard:
    def test_hand_size_is_unchanged_and_the_library_shrinks(self, builder):
        game, bear = position(builder, [FOREST, BEAR], [BEAR] * 5)
        before = len(hand_ids(game))

        run(game, SELF, bear, pitch=BEAR)

        assert len(hand_ids(game)) == before, "one in, one out"
        assert len(game.state.players[0].library) == 4

    def test_connive_two_draws_two_and_discards_two(self, builder):
        game, bear = position(builder, [FOREST, FOREST], [BEAR] * 5)

        run(game, dict(SELF, amount={"const": 2}), bear, pitch=BEAR)

        assert len(game.state.players[0].library) == 3
        assert len(hand_ids(game)) == 2

    def test_the_discard_is_not_optional(self, builder):
        """"Then discard N cards" — there is no declining it."""
        game, bear = position(builder, [FOREST, BEAR], [BEAR] * 5)

        asked = run(game, SELF, bear, pitch=BEAR)

        discard = next(d for d in asked if d.kind is DecisionKind.CHOOSE_OBJECTS)
        assert discard.min_count == discard.max_count == 1

    def test_the_discarded_card_reaches_the_graveyard(self, builder):
        game, bear = position(builder, [FOREST, BEAR], [BEAR] * 5)
        run(game, SELF, bear, pitch=FOREST)
        graveyard = game.state.players[0].graveyard
        assert [game.state.objects[o].def_id for o in graveyard] == [FOREST]


class TestWhatTheCounterCounts:
    def test_a_nonland_discard_places_one_counter(self, builder):
        game, bear = position(builder, [FOREST, BEAR], [BEAR] * 5)
        run(game, SELF, bear, pitch=BEAR)
        assert counters(game, bear) == 1

    def test_a_land_discard_places_none(self, builder):
        """The drawback. Counting discards instead would delete it."""
        game, bear = position(builder, [FOREST, BEAR], [BEAR] * 5)
        run(game, SELF, bear, pitch=FOREST)
        assert counters(game, bear) == 0

    def test_a_mixed_discard_counts_only_the_nonlands(self, builder):
        """Connive 2 pitching one land and one spell is one counter, not two."""
        game, bear = position(builder, [FOREST, FOREST, BEAR], [BEAR, BEAR, BEAR])
        # Drawing two Bears makes the hand two Forests and three Bears; the
        # answer below takes one of each, which is the only interesting case.
        ctx = EffectContext(state=game.state, controller=0, source_oid=bear)
        gen = OPS["connive"](ctx, dict(SELF, amount={"const": 2}))
        send = None
        while True:
            try:
                decision = gen.send(send)
            except StopIteration:
                break
            by_id = {
                i: game.state.objects[o.value].def_id
                for i, o in enumerate(decision.options)
            }
            land = next(i for i, name in by_id.items() if name == FOREST)
            spell = next(i for i, name in by_id.items() if name == BEAR)
            send = [land, spell]

        assert counters(game, bear) == 1


class TestWhichPermanentConnives:
    def test_two_creatures_connive_separately(self, builder):
        game, (first, second) = position(builder, [BEAR, BEAR], [BEAR] * 6, creatures=2)
        spec = {
            "op": "connive",
            "objects": {"zone": "battlefield", "controller": "you"},
        }

        run(game, spec, first, pitch=BEAR)

        assert counters(game, first) == counters(game, second) == 1
        assert len(game.state.players[0].library) == 4, "two draws, not one"

    def test_an_empty_pool_connives_nobody(self, builder):
        game, _ = position(builder, [BEAR], [BEAR] * 5)
        spec = {"op": "connive", "objects": {"zone": "battlefield", "subtypes": ["Sliver"]}}

        run(game, spec, None)

        assert len(game.state.players[0].library) == 5, "nothing drawn"


class TestTheEmptyHandBoundary:
    def test_a_hand_of_one_discards_that_one(self, builder):
        """The draw comes first, so there is always something to discard."""
        game, bear = position(builder, [], [FOREST] * 5)

        run(game, SELF, bear)

        assert hand_ids(game) == [], "drew a Forest and pitched it"
        assert counters(game, bear) == 0, "a land, so no counter"
        assert game.state.objects[game.state.players[0].graveyard[0]].zone is Zone.GRAVEYARD


class TestTheLoaderGuard:
    def test_a_well_formed_effect_loads(self):
        _validate_effect(SELF, "test", {})

    def test_omitting_objects_is_refused(self):
        with pytest.raises(DslError, match="connive needs 'objects'"):
            _validate_effect({"op": "connive"}, "test", {})
