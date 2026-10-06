"""A delayed trigger scoped to one chosen object.

    "Choose target creature you control. Whenever **that creature** deals
    combat damage to a player or planeswalker this turn, draw that many cards."
                                            -- Hunter's Insight

`delayed_trigger` could say *when* ("this turn") and *whose* (`controller`), and
could not say *which*. Forth Eorlingas!, the card it was built for, watches any
creature you control and needs no scope -- so written without one, Hunter's
Insight is that card with a target line stapled on, and every creature you
control draws off it.

**An oid, resolved as the delayed ability is created**, for the reason the
bindings and the controller are captured there: the instant is in a graveyard
before the first blow lands, and there is nothing left to resolve "that
creature" against. `TriggerSpec.source` cannot stand in -- it says `"self"`, and
a delayed ability has no self; that is the whole reason `_delayed_matches`
exists as a narrower comparison than `_matches`.

**Compared against the event's subject**, which for a damage event is the
*dealer* -- the same object `source: "self"` means on an ordinary trigger.

A target that is gone by resolution installs nothing at all. 608.2b took it, so
there is no "that creature" to watch, and watching everything instead would be a
strictly better card.
"""

from __future__ import annotations

import pytest

from automtg.cards.loader import compile_card
from automtg.cards.schema import CardModel
from automtg.engine.enums import ActionKind, DecisionKind, Step
from automtg.engine.errors import DslError
from automtg.engine.primitives import damage_player
from tests.conftest import only_oid, pass_until

INSIGHT = "t_dsub_insight"  # scoped to the chosen creature
ANY = "t_dsub_any"  # the same subscription, unscoped
CHOSEN = "t_dsub_chosen"  # 2/2
OTHER = "t_dsub_other"  # 3/3


def position(builder, spell: str):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .battlefield(0, [CHOSEN, OTHER])
        .hand(0, [spell])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game._advance()
    return game


def cast(game, card_id: str, *, aim: str | None = None):
    """Cast the spell, aiming its target at ``aim`` when it has one."""
    actions = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST and game.state.objects[a.source].def_id == card_id
    ]
    if aim is not None:
        wanted = only_oid(game, aim)
        actions = [a for a in actions if any(r.id == wanted for r in a.targets)]
    game.apply(actions[0])
    for _ in range(20):
        pending = game.pending()
        if pending is None or pending.kind is DecisionKind.PRIORITY:
            break
        choice = next(
            (a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None
        )
        if choice is None:
            break
        game.apply(choice)
    pass_until(game, lambda g: not g.state.stack and not g.state.pending_triggers)


def connect(game, dealer: str, amount: int = 2):
    """Deal ``amount`` combat damage to the opponent, then let it settle.

    `_advance` is what drains `state.armed_delays`: an event-watching delayed
    ability is *armed* by `triggers.collect` and only reaches the stack when the
    game runs forward (603.7's two halves happen off the stack, in that order).
    Reading the board without it is reading one step too early.
    """
    damage_player(game.state, 1, amount, only_oid(game, dealer), is_combat=True)
    # `armed_delays` in the predicate, not just the stack. `_arm_delayed` puts a
    # copy there and `game._advance` is what resolves it -- but `_advance`
    # returns at once while a decision is pending, and a position built here is
    # always sitting on one. So the delayed half reaches the stack at the next
    # moment the engine can suspend, which is 603.7's own timing: both halves
    # happen off the stack, in that order. Waiting on the stack alone reads the
    # board a step early and would pass whatever the scope did.
    pass_until(
        game,
        lambda g: not g.state.armed_delays
        and not g.state.stack
        and not g.state.pending_triggers,
    )


def drawn(game, before: int, pid: int = 0) -> int:
    return before - len(game.state.players[pid].library)


class TestTheScopeHolds:
    def test_the_chosen_creature_fires_it(self, builder):
        game = position(builder, INSIGHT)
        cast(game, INSIGHT, aim=CHOSEN)
        before = len(game.state.players[0].library)
        connect(game, CHOSEN, amount=2)
        assert drawn(game, before) == 2

    def test_another_creature_does_not(self, builder):
        """The whole clause. Unscoped, this is a second card's worth of draw."""
        game = position(builder, INSIGHT)
        cast(game, INSIGHT, aim=CHOSEN)
        before = len(game.state.players[0].library)
        connect(game, OTHER, amount=3)
        assert drawn(game, before) == 0

    def test_the_other_creature_can_be_the_chosen_one(self, builder):
        """The scope follows the target rather than the card."""
        game = position(builder, INSIGHT)
        cast(game, INSIGHT, aim=OTHER)
        before = len(game.state.players[0].library)
        connect(game, OTHER, amount=3)
        assert drawn(game, before) == 3

    def test_it_fires_more_than_once(self, builder):
        """"**Whenever** … this turn" is a subscription with a lifetime, not a
        one-shot: two connections are two triggers."""
        game = position(builder, INSIGHT)
        cast(game, INSIGHT, aim=CHOSEN)
        before = len(game.state.players[0].library)
        connect(game, CHOSEN, amount=1)
        connect(game, CHOSEN, amount=1)
        assert drawn(game, before) == 2


class TestWithoutTheScope:
    """The control. An unscoped subscription is Forth Eorlingas! -- it watches
    every creature you control, which is a different card."""

    def test_any_creature_fires_it(self, builder):
        game = position(builder, ANY)
        cast(game, ANY)
        before = len(game.state.players[0].library)
        connect(game, OTHER, amount=3)
        assert drawn(game, before) == 3


class TestTheLoaderPlacesIt:
    def _card(self, trigger, **extra):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Choose target creature you control.",
                "mana_cost": "{G}",
                "types": ["Instant"],
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "count": 1,
                        "selector": {"zone": "battlefield", "controller": "you"},
                    }
                ],
                "spell_effects": [
                    {
                        "op": "delayed_trigger",
                        "trigger": trigger,
                        "effects": [{"op": "draw", "amount": {"const": 1}}],
                    }
                ],
                **extra,
            }
        )

    def test_a_target_scope_loads(self):
        compile_card(
            self._card(
                {
                    "event": "deals_combat_damage_to_player",
                    "subject": {"target": "t1"},
                }
            )
        )

    def test_a_binding_scope_loads(self):
        compile_card(
            self._card(
                {"event": "deals_combat_damage_to_player", "subject": {"binding": "it"}}
            )
        )

    def test_a_scope_that_names_no_object_is_refused(self):
        """A delayed ability has no board to search: the object it means is one
        it already has in hand, as a target or a binding."""
        with pytest.raises(DslError, match="names one object"):
            compile_card(
                self._card(
                    {
                        "event": "deals_combat_damage_to_player",
                        "subject": {"types": ["Creature"]},
                    }
                )
            )

    def test_an_event_with_no_object_subject_is_refused(self):
        """Compared against nothing, the subscription never fires -- the card
        reads as printed and does nothing."""
        with pytest.raises(DslError, match="has no object subject"):
            compile_card(
                self._card({"event": "upkeep", "subject": {"target": "t1"}})
            )
