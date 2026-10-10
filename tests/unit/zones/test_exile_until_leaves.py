""""Exile it until this permanent leaves the battlefield."

Oblivion Ring is the shipped witness, and the whole family — Banishing Light,
Fiend Hunter, Angel of Sanctions — waits on the same one thing: a link, written
when a permanent exiles something, readable by a *later and separate* resolution
of that permanent's own leaves-trigger.

`snapshot` is the documented answer to last-known information and cannot do
this. It writes into `EffectContext.bindings`, which lives for exactly one
resolution: the enters-trigger that exiles and the leaves-trigger that returns
are two different abilities with two different contexts, so a snapshot taken by
the first is gone before the second runs.

**The link lives on the exiled card, not on the exiler**, and that is the whole
trick. The exiler is the thing that goes away — Oblivion Ring is in a graveyard
by the time the return happens. The exiled card is sitting in exile, untouched.
And an oid survives every zone change in this engine, so a leaves-trigger's
`source_oid` still names the departed permanent: `{"exiled_with": "self"}` needs
no snapshot at all, just a comparison.

Set *after* the move to exile, because `move_object` runs
`reset_permanent_state` on the way and would wipe it. Cleared by that same reset
when the card comes back, which is correct — the link is spent once followed.

The property worth pinning is which cards come back. A plain `{"zone": "exile"}`
filter matches every card in exile from every source, so a return over it would
hand back cards this permanent never touched. That is a different card, and a
strictly better one, so `test_it_returns_only_its_own_victim` is the test that
matters here.

Note the selector needs `"controller": "any"`: an exiled card keeps its last
controller, which for O-Ring's victim is an opponent, and the selector language
defaults `controller` to "you".
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.zones import destroy, exile

RING = "oblivion_ring"


def board(builder, victims=("t_bear",)):
    return (
        builder(players=2)
        .battlefield(0, [RING, "plains", "plains", "plains", "plains"])
        .battlefield(1, list(victims))
        .active(0)
        .build()
    )


def only(game, def_id: str) -> int:
    return next(
        o for o, obj in game.state.objects.items() if obj.def_id == def_id
    )


def drive(game, limit: int = 40) -> None:
    """Advance, answering choices, until nothing is pending but a decision."""
    game._advance()
    for _ in range(limit):
        decision = game.pending()
        if decision is None:
            return
        actions = game.legal_actions()
        if decision.kind is DecisionKind.CHOOSE_OBJECTS:
            choose = next((a for a in actions if a.kind is ActionKind.CHOOSE), None)
            if choose is not None:
                game.apply(choose)
                continue
        if decision.kind is not DecisionKind.PRIORITY:
            return
        passing = next((a for a in actions if a.kind is ActionKind.PASS), None)
        if passing is None:
            return
        game.apply(passing)


def link(game, victim: int, ring: int) -> None:
    """Exile `victim` as the Ring's enters-trigger would."""
    exile(game.state, victim)
    game.state.objects[victim].exiled_by = ring


class TestTheLinkSurvives:
    def test_the_exiled_card_remembers_who_exiled_it(self, builder):
        game = board(builder)
        ring, bear = only(game, RING), only(game, "t_bear")
        link(game, bear, ring)
        assert game.state.objects[bear].exiled_by == ring

    def test_it_outlives_the_exiler_leaving(self, builder):
        game = board(builder)
        ring, bear = only(game, RING), only(game, "t_bear")
        link(game, bear, ring)
        destroy(game.state, ring)
        assert game.state.objects[bear].exiled_by == ring, (
            "the link is on the card in exile, which nothing has touched"
        )

    def test_and_is_spent_once_the_card_returns(self, builder):
        game = board(builder)
        ring, bear = only(game, RING), only(game, "t_bear")
        link(game, bear, ring)
        destroy(game.state, ring)
        drive(game)
        assert game.state.objects[bear].exiled_by is None, (
            "reset_permanent_state clears it on the way back in"
        )


class TestTheReturn:
    def test_the_card_comes_back(self, builder):
        game = board(builder)
        ring, bear = only(game, RING), only(game, "t_bear")
        link(game, bear, ring)
        destroy(game.state, ring)
        drive(game)
        assert game.state.objects[bear].zone is Zone.BATTLEFIELD

    def test_under_its_owner_s_control(self, builder):
        game = board(builder)
        ring, bear = only(game, RING), only(game, "t_bear")
        link(game, bear, ring)
        destroy(game.state, ring)
        drive(game)
        obj = game.state.objects[bear]
        assert obj.controller == obj.owner == 1, (
            "'under its owner's control' -- stealing it would be a better card"
        )

    def test_it_returns_only_its_own_victim(self, builder):
        """A plain `{"zone": "exile"}` filter would return both."""
        game = board(builder, victims=("t_bear", "t_flier"))
        ring = only(game, RING)
        bear, flier = only(game, "t_bear"), only(game, "t_flier")
        link(game, bear, ring)
        exile(game.state, flier)  # exiled by something else entirely

        destroy(game.state, ring)
        drive(game)

        assert game.state.objects[bear].zone is Zone.BATTLEFIELD
        assert game.state.objects[flier].zone is Zone.EXILE, (
            "this Ring never touched the flier; returning it would be a "
            "different card"
        )

    def test_nothing_returns_if_it_exiled_nothing(self, builder):
        game = board(builder)
        ring, bear = only(game, RING), only(game, "t_bear")
        exile(game.state, bear)  # no link
        destroy(game.state, ring)
        drive(game)
        assert game.state.objects[bear].zone is Zone.EXILE


class TestEndToEnd:
    def test_casting_the_ring_exiles_and_links(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, ["plains"] * 4)
            .battlefield(1, ["t_bear"])
            .hand(0, [RING])
            .active(0)
            .build()
        )
        cast = next(
            a
            for a in game.legal_actions()
            if a.kind is ActionKind.CAST
            and game.state.objects[a.source].def_id == RING
        )
        game.apply(cast)
        for _ in range(20):
            decision = game.pending()
            if decision is None:
                break
            actions = game.legal_actions()
            if decision.kind is DecisionKind.CHOOSE_OBJECTS:
                choose = next((a for a in actions if a.kind is ActionKind.CHOOSE), None)
                if choose is not None:
                    game.apply(choose)
                    continue
            if decision.kind is DecisionKind.PRIORITY and game.state.stack:
                game.apply(next(a for a in actions if a.kind is ActionKind.PASS))
                continue
            break

        bear = only(game, "t_bear")
        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.objects[bear].exiled_by == only(game, RING), (
            "the enters-trigger wrote the link, not the test"
        )


class TestTheLoader:
    def test_until_leaves_needs_something_to_exile(self):
        payload = {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "When this enchantment enters, exile something.",
            "mana_cost": "{W}",
            "types": ["Enchantment"],
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "When this enchantment enters, exile something.",
                    "trigger": {"event": "self_enters", "source": "self"},
                    "effects": [{"op": "exile", "until_leaves": True}],
                }
            ],
        }
        with pytest.raises(DslError, match="nothing to link"):
            compile_card(CardModel.model_validate(payload))

    def test_exiled_with_is_a_known_selector_key(self):
        from commanderblitz.engine.effects.selectors import SELECTOR_KEYS

        assert "exiled_with" in SELECTOR_KEYS
