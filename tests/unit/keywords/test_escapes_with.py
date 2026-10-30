"""Escapes with: counters that belong to the escape cast, and to nothing else.

    Escape—{3}{B}{B}, Exile four other cards from your graveyard.
    This creature escapes with two +1/+1 counters on it.

702.138c reads "[this permanent] escapes with ..." as "if this permanent
escaped, it enters with ...", and 702.138d says what escaping is: the spell
that became it was cast **for its escape cost**. So the rider is an ordinary
`self_enters_with_counters` replacement gated on `{"escaped": true}`, and the
whole design question is what writes that answer.

**Not `cast_from_graveyard`.** That stamp is also true of a card cast out of a
graveyard under a permanent's permission (Muldrotha, an Edgar-shaped
`cast_from_graveyard` static), which pays the mana cost and never escapes. A
Woe Strider cast that way is a 3/2, and reading the wider stamp would hand it
two counters it did not pay for.

**One arrival only.** The stamp is written as the spell resolves into the
permanent and cleared by `zones._enter_battlefield` on every other arrival,
`cast_impending`'s contract: a Strider that escaped, died and was reanimated is
a new object (400.7) that was never cast.

Witness: Woe Strider, whose test twin is `t_woe_strider`.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy, move_object
from tests.conftest import pass_until, plus_one_counters, pt

STRIDER = "t_woe_strider"  # {2}{B} 3/2; escape {3}{B}{B} + exile four others
KEEPER = "t_crypt_keeper"  # once each turn, cast a creature spell from your graveyard


def board(builder, *, where: str, keeper: bool = False):
    """Player 0 with the Strider in ``where``, five Swamps and four cards of fodder.

    Five Swamps pay either price, so when both lines are offered the test picks
    one by what it is rather than by what is affordable. A Forest stays in hand
    to keep the turn standing where it was put.
    """
    b = builder(players=2)
    graveyard = ["t_bear"] * 4
    if where == "graveyard":
        graveyard = [STRIDER, *graveyard]
        b = b.hand(0, ["forest"])
    else:
        b = b.hand(0, [STRIDER, "forest"])
    battlefield = ["swamp"] * 5 + ([KEEPER] if keeper else [])
    return (
        b.graveyard(0, graveyard)
        .battlefield(0, battlefield)
        .hand(1, ["forest"])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .build()
    )


def strider_oid(game) -> int:
    (oid,) = [o.oid for o in game.state.objects.values() if o.def_id == STRIDER]
    return oid


def casts(game):
    oid = strider_oid(game)
    return [a for a in game.legal_actions() if a.kind is ActionKind.CAST and a.source == oid]


def cast(game, *, escape: bool) -> int:
    """Cast the Strider the named way and resolve it, cost decisions and all.

    The escape line stops on the exile decision before the spell is pushed, so
    the wait is on the permanent, not on an empty stack.
    """
    game.apply(next(a for a in casts(game) if a.flashback == escape))
    oid = strider_oid(game)
    pass_until(
        game,
        lambda g: g.state.objects[oid].zone is Zone.BATTLEFIELD and not g.state.stack,
    )
    return oid


class TestItEscapesWithTheCounters:
    def test_escaped_it_enters_with_two_counters(self, builder):
        game = board(builder, where="graveyard")
        oid = cast(game, escape=True)
        assert plus_one_counters(game, oid) == 2
        assert pt(game, oid) == (5, 4)

    def test_the_escape_cost_was_really_paid(self, builder):
        # The boundary of the claim above: this was the escape line, not a
        # free graveyard cast that happened to read the same stamp.
        game = board(builder, where="graveyard")
        cast(game, escape=True)
        assert len(game.state.players[0].exile) == 4


class TestOnlyEscapingCounts:
    def test_cast_from_hand_it_enters_with_none(self, builder):
        game = board(builder, where="hand")
        oid = cast(game, escape=False)
        assert plus_one_counters(game, oid) == 0
        assert pt(game, oid) == (3, 2)

    def test_both_graveyard_lines_are_offered_under_a_permission(self, builder):
        game = board(builder, where="graveyard", keeper=True)
        assert sorted(a.flashback for a in casts(game)) == [False, True]

    def test_cast_from_the_graveyard_for_its_mana_cost_it_did_not_escape(self, builder):
        # 702.138c: the permission's line left a graveyard and paid the
        # printed {2}{B}. `cast_from_graveyard` is true of it; `escaped` is not.
        game = board(builder, where="graveyard", keeper=True)
        oid = cast(game, escape=False)
        assert game.state.objects[oid].cast_from_graveyard
        assert plus_one_counters(game, oid) == 0
        assert game.state.players[0].exile == []


class TestTheStampIsOneArrival:
    def test_reanimated_after_escaping_it_enters_with_none(self, builder):
        # 400.7: what comes back is a new object, and nothing cast it.
        game = board(builder, where="graveyard")
        oid = cast(game, escape=True)
        destroy(game.state, oid)
        assert game.state.objects[oid].zone is Zone.GRAVEYARD
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0, cause="effect")
        assert plus_one_counters(game, oid) == 0

    def test_flickered_after_escaping_it_enters_with_none(self, builder):
        game = board(builder, where="graveyard")
        oid = cast(game, escape=True)
        move_object(game.state, oid, Zone.EXILE, to_player=0, cause="effect")
        move_object(game.state, oid, Zone.BATTLEFIELD, to_player=0, cause="effect")
        assert plus_one_counters(game, oid) == 0
        assert not game.state.objects[oid].cast_escaped


class TestTheLoader:
    def _card(self, condition=None, **extra) -> CardModel:
        return CardModel(
            id="t_probe",
            name="Probe",
            mana_cost="{2}{B}",
            types=["Creature"],
            power=3,
            toughness=2,
            replacements=[
                {
                    "event": "self_enters_with_counters",
                    "counter": "+1/+1",
                    "amount": 2,
                    "condition": condition or {"escaped": True},
                }
            ],
            **extra,
        )

    def test_an_escape_card_loads(self):
        compile_card(
            self._card(
                graveyard_cost={"mana": "{3}{B}{B}"},
                graveyard_cast="graveyard",
            )
        )

    def test_a_card_with_no_escape_cost_is_refused(self):
        with pytest.raises(DslError, match="escaped"):
            compile_card(self._card())

    def test_a_flashback_card_is_refused(self):
        # Flashback's slot is the same field with the exile destination; a
        # reader there would fire for the wrong keyword.
        with pytest.raises(DslError, match="escaped"):
            compile_card(self._card(graveyard_cost={"mana": "{3}{B}{B}"}))

    def test_the_value_must_be_a_boolean(self):
        card = self._card(
            {"escaped": "yes"},
            graveyard_cost={"mana": "{3}{B}{B}"},
            graveyard_cast="graveyard",
        )
        with pytest.raises(DslError, match="true or false"):
            compile_card(card)
