"""`turn_face_up` -- an effect turning a face-down permanent face up (708.8).

    Showstopping Surprise -- "Choose target creature you control. Turn it face
    up if it's face down."
    Ugin's Mastery -- "... you may turn a face-down creature you control face
    up."

Until this op the only way face up was the special action, which pays the
morph, disguise or manifested card's cost. An effect pays nothing, and that is
the rules argument here:

* **No cost, so no megamorph counter.** The +1/+1 counter comes with paying the
  megamorph cost (702.37b); a megamorph creature an effect turns up gets none.
* **Any face-down permanent**, a manifested noncreature card included: the
  special action is offered only for a creature card (701.34c), and that limit
  is the action's, not the turn's. An instant or sorcery card is the exception
  -- revealed, and left face down, with nothing hearing it turn.
* **The same event.** `turned_face_up` fires as it does for the special action,
  so "when this is turned face up" and Growing Dread hear an effect's turn.
* **Already face up, nothing.** "Turn it face up if it's face down" needs no
  condition: on a face-up creature the op does nothing and fires nothing.

`transform` is the near miss: it turns a double-faced card over, and a
face-down permanent is not one.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.characteristics import chars
from commanderblitz.engine.enums import ActionKind, DecisionKind
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from tests.conftest import (
    action_for_card,
    activations,
    oids_of,
    only_oid,
    pass_until,
    plus_one_counters,
    settle,
    settle_completely,
)

FOREST = "forest"
FLIP = "t_tfu_op_flip"  # instant: "turn target creature you control face up"
MASTERY = "t_tfu_op_mastery"  # sorcery: "you may turn a face-down creature you control face up"
MEGAMORPHER = "t_tfu_megamorpher"  # {3}{G} 4/4, megamorph {2}{G}
MORPHER = "t_morpher"  # {4}{G} 5/5 flier, morph {2}{G}
SNATCHER = "t_tfu_snatcher"  # morph {G}; "when this is turned face up, draw a card"
DREAD = "t_tfu_dread"  # "whenever you turn a permanent face up, +1/+1 counter on it"
BOLT = "t_bolt"  # an instant card, to manifest


def board(builder, mine=(), *, spell=FLIP, down=(), theirs=()):
    """Player 0 with two Forests, ``mine`` on the battlefield and ``spell`` in
    hand; every card in ``down`` is turned face down as a manifest leaves it.
    Returns ``(game, oid)`` with the oid of the first card in ``down``."""
    game = (
        builder(players=2)
        .battlefield(0, [FOREST] * 2 + list(mine) + list(down))
        .battlefield(1, [FOREST] * 2 + list(theirs))
        .hand(0, [spell])
        .library(0, [FOREST] * 20)
        .library(1, [FOREST] * 20)
        .build()
    )
    oid = None
    for card in reversed(list(down)):
        # The last copy on the battlefield is the one ``down`` added.
        oid = oids_of(game, card, 0)[-1]
        turn_down(game, oid)
    return game, oid


def turn_down(game, oid: int) -> None:
    obj = game.state.objects[oid]
    obj.face_down = True
    obj.revealed_to.add(obj.controller)
    game.state.bump_chars()


def flip(game, oid: int) -> None:
    """Cast the flip instant at ``oid`` and let everything resolve."""
    game.apply(
        next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == FLIP
            and any(ref.id == oid for ref in a.targets)
        )
    )
    settle(game)


def cast_mastery(game, pick: int | None) -> None:
    """Cast the sorcery and pick ``pick`` (or decline with ``None``)."""
    game.apply(action_for_card(game, ActionKind.CAST, MASTERY))

    def asked_or_done(g) -> bool:
        d = g.pending()
        return (d is not None and d.kind is DecisionKind.CHOOSE_OBJECTS) or (
            not g.state.stack and not g.state.pending_triggers
        )

    pass_until(game, asked_or_done)
    decision = game.pending()
    if decision is not None and decision.kind is DecisionKind.CHOOSE_OBJECTS:
        offered = {o.ref.id for o in decision.options if o.ref is not None}
        game.last_offered = offered  # type: ignore[attr-defined]
        if pick is not None:
            index = next(i for i, o in enumerate(decision.options) if o.ref and o.ref.id == pick)
            game.apply(
                next(a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE and a.choice == index)
            )
        if game.pending() is decision:
            game.apply(next(a for a in game.legal_actions() if a.kind is ActionKind.FINISH_DECLARATION))
    settle_completely(game)


def turned_up(game) -> list:
    return [e for e in game.state.events if e.type == EventType.TURNED_FACE_UP]


class TestItTurnsUpForFree:
    def test_a_morph_turns_up_and_no_mana_is_spent(self, builder):
        game, beast = board(builder, down=[MORPHER])
        assert chars(game.state, beast).power == 2

        flip(game, beast)

        assert not game.state.objects[beast].face_down
        assert chars(game.state, beast).power == 5
        # The {G} for the instant and nothing for the morph cost {2}{G}.
        untapped = [o for o in oids_of(game, FOREST, 0) if not game.state.objects[o].tapped]
        assert len(untapped) == 1

    def test_megamorph_gets_no_counter(self, builder):
        """702.37b: the counter comes with paying the megamorph cost."""
        game, beast = board(builder, down=[MEGAMORPHER])

        flip(game, beast)

        assert not game.state.objects[beast].face_down
        assert plus_one_counters(game, beast) == 0
        assert chars(game.state, beast).power == 4

    def test_paying_the_megamorph_cost_still_gives_one(self, builder):
        """The near side of the boundary: the special action keeps its counter."""
        game, beast = board(builder, [FOREST], down=[MEGAMORPHER])

        game.apply(activations(game, beast, 0)[0])
        settle(game)

        assert plus_one_counters(game, beast) == 1

    def test_the_event_fires_and_self_hears_it(self, builder):
        game, snatcher = board(builder, down=[SNATCHER])
        before = len(game.state.players[0].hand)

        flip(game, snatcher)

        assert [(e.source, e.data["oid"]) for e in turned_up(game)] == [(snatcher, snatcher)]
        # The instant left the hand, the snatcher's own trigger drew one.
        assert len(game.state.players[0].hand) == before

    def test_growing_dread_hears_an_effect_turn(self, builder):
        game, beast = board(builder, [DREAD], down=[MORPHER])

        flip(game, beast)

        assert plus_one_counters(game, beast) == 1

    def test_the_ward_of_a_disguised_or_cloaked_shell_goes(self, builder):
        game, beast = board(builder, down=[MORPHER])
        obj = game.state.objects[beast]
        obj.disguised = True
        obj.cloaked = True

        flip(game, beast)

        assert not obj.disguised and not obj.cloaked and not obj.face_down


class TestAnyFaceDownPermanent:
    def test_a_manifested_land_turns_up_into_the_land(self, builder):
        """The special action refuses it (701.34c); an effect does not."""
        game, land = board(builder, spell=MASTERY, down=[FOREST])
        assert not activations(game, land, 0), "no special action for a land card"

        cast_mastery(game, land)

        assert not game.state.objects[land].face_down
        assert "Land" in chars(game.state, land).types
        assert len(turned_up(game)) == 1

    def test_a_manifested_instant_is_revealed_and_stays_down(self, builder):
        game, bolt = board(builder, spell=MASTERY, down=[BOLT])

        cast_mastery(game, bolt)

        assert game.state.objects[bolt].face_down
        assert not turned_up(game)
        assert any(e.type == "reveal" and e.source == bolt for e in game.state.events)


class TestNothingToTurn:
    def test_a_face_up_creature_is_left_alone(self, builder):
        """Showstopping Surprise's "if it's face down", with no condition."""
        game, _ = board(builder, [DREAD, MORPHER])
        beast = only_oid(game, MORPHER)

        flip(game, beast)

        assert not turned_up(game)
        assert plus_one_counters(game, beast) == 0

    def test_the_choice_offers_only_face_down_creatures(self, builder):
        game, beast = board(builder, [MORPHER], spell=MASTERY, down=[MORPHER])

        cast_mastery(game, beast)

        assert game.last_offered == {beast}  # type: ignore[attr-defined]
        assert not game.state.objects[beast].face_down

    def test_may_declines(self, builder):
        game, beast = board(builder, spell=MASTERY, down=[MORPHER])

        cast_mastery(game, None)

        assert game.state.objects[beast].face_down
        assert not turned_up(game)


class TestLoader:
    def test_objects_is_required(self):
        model = CardModel.model_validate(
            {
                "id": "t_tfu_bad",
                "name": "Bad",
                "oracle_text": "Turn it face up.",
                "mana_cost": "{G}",
                "types": ["Sorcery"],
                "spell_effects": [{"op": "turn_face_up"}],
            }
        )
        with pytest.raises(DslError, match="turn_face_up needs 'objects'"):
            compile_card(model)
