"""A delayed trigger that watches its subject leave the battlefield.

    "Put a +1/+1 counter on target creature you control. Then it fights target
    creature an opponent controls. When **the creature an opponent controls
    dies this turn**, if you control your commander, you become the monarch."
                                            -- Fight for the Throne

A delayed ability scoped to an object is released when that object leaves the
battlefield (400.7: what comes back is a new object, and a subscription still
holding the oid would go on watching it). Every other scoped subscription wants
exactly that. This one does not: the event it exists to hear *is* the departure,
and the dies event is announced once the creature is already in the graveyard.
Released first, it never fires -- the card loads, reads as printed and never makes
anyone the monarch.

603.10a is the rule: an ability that triggers on an object leaving the
battlefield "looks back in time". So a subscription whose event is its subject's
own departure (`dies`, `creature_dies`, `leaves_battlefield`, `sacrificed`) is
spared by the release that runs as the object leaves, and struck by a second one
once the leave events have gone out. It hears that departure and no later one:
the creature reanimated and killed again is a new object, and its second death is
not the one the spell was about.

The intervening-if (603.4) is asked when the ability triggers and again as it
resolves, the same as on a printed trigger. The resolution check is what keeps
the crown off a player whose commander left in the same batch of deaths.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine import zones
from commanderblitz.engine.carddef import TriggerSpec
from commanderblitz.engine.enums import ActionKind, DecisionKind, Step, Zone
from commanderblitz.engine.events import EventType
from commanderblitz.engine.zones import destroy, exile, move_object, sacrifice
from tests.conftest import count_on_battlefield, only_oid, pass_until

THRONE = "t_ddies_throne"  # Fight for the Throne
MARK = "t_ddies_mark"  # "when that creature dies this turn, you gain 3 life"
FAREWELL = "t_ddies_farewell"  # "when that creature leaves the battlefield…"
FIGHTER = "t_ddies_fighter"  # 3/3, yours, and your commander where it matters
VICTIM = "t_ddies_victim"  # 2/2, the opponent's
BYSTANDER = "t_ddies_bystander"  # 2/2, the opponent's, never chosen


def position(builder, spell: str, *, commander: bool = True):
    game = (
        builder(players=2)
        .battlefield(0, ["forest"] * 4)
        .battlefield(0, [FIGHTER])
        .battlefield(1, [VICTIM, BYSTANDER])
        .hand(0, [spell])
        .library(0, ["forest"] * 30)
        .library(1, ["forest"] * 30)
        .step(Step.PRECOMBAT_MAIN)
        .build(advance=False)
    )
    game.state.objects[only_oid(game, FIGHTER)].is_commander = commander
    game._advance()
    return game


def settle(game) -> None:
    """Run forward until the delayed half has resolved as well.

    `armed_delays` in the predicate as well as the stack: `_arm_delayed` arms a
    copy and `game._advance` is what resolves it, so waiting on the stack alone
    reads the board one step early.
    """
    pass_until(
        game,
        lambda g: not g.state.armed_delays
        and not g.state.stack
        and not g.state.pending_triggers,
    )


def cast(game, card_id: str, *aims: str) -> None:
    """Cast the spell with its targets on ``aims``, in order, and resolve it."""
    wanted = [only_oid(game, aim) for aim in aims]
    actions = [
        a
        for a in game.legal_actions()
        if a.kind is ActionKind.CAST
        and game.state.objects[a.source].def_id == card_id
        and [r.id for r in a.targets] == wanted
    ]
    game.apply(actions[0])
    for _ in range(20):
        pending = game.pending()
        if pending is None or pending.kind is DecisionKind.PRIORITY:
            break
        choice = next((a for a in game.legal_actions() if a.kind is ActionKind.CHOOSE), None)
        if choice is None:
            break
        game.apply(choice)
    settle(game)


def life(game, pid: int = 0) -> int:
    return game.state.players[pid].life


class TestFightForTheThrone:
    def test_the_fought_creature_dying_crowns_you(self, builder):
        """The fight marks lethal damage; the creature dies to the state-based
        action after the spell resolves, and the delayed ability hears it."""
        game = position(builder, THRONE)
        cast(game, THRONE, FIGHTER, VICTIM)
        assert count_on_battlefield(game, VICTIM) == 0
        assert game.state.monarch == 0

    def test_without_your_commander_nobody_is_crowned(self, builder):
        """The intervening-if, asked as the ability would trigger."""
        game = position(builder, THRONE, commander=False)
        cast(game, THRONE, FIGHTER, VICTIM)
        assert count_on_battlefield(game, VICTIM) == 0
        assert game.state.monarch is None

    def test_the_commander_leaving_before_it_resolves_stops_it(self, builder, monkeypatch):
        """603.4's second check. The death arms the ability, and before it
        resolves your commander changes hands -- the way a commander dying later
        in the same batch of state-based actions would leave it."""
        game = position(builder, THRONE)
        fighter = only_oid(game, FIGHTER)
        real = zones.fire

        def steal_after_the_death(state, event_type, **kw):
            event = real(state, event_type, **kw)
            if event_type == EventType.DIES:
                state.objects[fighter].controller = 1
            return event

        monkeypatch.setattr(zones, "fire", steal_after_the_death)
        cast(game, THRONE, FIGHTER, VICTIM)
        assert count_on_battlefield(game, VICTIM) == 0
        assert game.state.monarch is None


class TestTheLookBack:
    def test_the_chosen_creature_dying_fires_it(self, builder):
        game = position(builder, MARK)
        cast(game, MARK, VICTIM)
        destroy(game.state, only_oid(game, VICTIM))
        settle(game)
        assert life(game) == 43

    def test_another_creature_dying_does_not(self, builder):
        """The scope. Unscoped, this fires on every creature an opponent loses."""
        game = position(builder, MARK)
        cast(game, MARK, VICTIM)
        destroy(game.state, only_oid(game, BYSTANDER))
        settle(game)
        assert life(game) == 40

    def test_a_sacrifice_is_a_death(self, builder):
        game = position(builder, MARK)
        cast(game, MARK, VICTIM)
        sacrifice(game.state, only_oid(game, VICTIM), by=1)
        settle(game)
        assert life(game) == 43

    def test_leaving_another_way_is_not_dying_and_ends_the_watch(self, builder):
        """Exiled rather than killed: no dies event, so nothing to hear -- and
        the subscription is released, because the object it watched is gone."""
        game = position(builder, MARK)
        cast(game, MARK, VICTIM)
        exile(game.state, only_oid(game, VICTIM))
        settle(game)
        assert life(game) == 40
        assert game.state.delayed_triggers == []

    def test_a_leaves_the_battlefield_watch_hears_an_exile(self, builder):
        game = position(builder, FAREWELL)
        cast(game, FAREWELL, VICTIM)
        exile(game.state, only_oid(game, VICTIM))
        settle(game)
        assert life(game) == 43


class TestOnlyThatDeparture:
    def test_the_same_card_dying_again_is_a_new_object(self, builder):
        """400.7. Reanimated, it is a different creature, and its second death is
        not the one the spell was waiting for."""
        game = position(builder, MARK)
        cast(game, MARK, VICTIM)
        victim = only_oid(game, VICTIM)
        destroy(game.state, victim)
        settle(game)
        move_object(game.state, victim, Zone.BATTLEFIELD)
        settle(game)
        destroy(game.state, victim)
        settle(game)
        assert life(game) == 43

    def test_the_subscription_is_spent_once_heard(self, builder):
        game = position(builder, MARK)
        cast(game, MARK, VICTIM)
        destroy(game.state, only_oid(game, VICTIM))
        settle(game)
        assert game.state.delayed_triggers == []

    def test_other_scoped_subscriptions_are_still_released_first(self, builder, monkeypatch):
        """Only a watch on the departure itself looks back. A subscription about
        anything else that its subject could do is gone the moment it leaves,
        before a single leave event is announced."""
        game = position(builder, MARK)
        cast(game, MARK, VICTIM)
        state = game.state
        (watch,) = state.delayed_triggers
        state.delayed_triggers.append(
            replace(watch, trigger=TriggerSpec(event="deals_combat_damage", controller="any"))
        )
        seen: list[int] = []
        real = zones.fire

        def spy(st, event_type, **kw):
            if event_type == EventType.DIES:
                seen.append(len(st.delayed_triggers))
            return real(st, event_type, **kw)

        monkeypatch.setattr(zones, "fire", spy)
        destroy(state, only_oid(game, VICTIM))
        # At the dies event only the look-back watch is left; afterwards, none.
        assert seen == [1]
        assert state.delayed_triggers == []


class TestTheLoaderPlacesIt:
    def _card(self, trigger):
        return CardModel.model_validate(
            {
                "id": "x",
                "name": "X",
                "oracle_text": "Choose target creature.",
                "mana_cost": "{G}",
                "types": ["Instant"],
                "targets": [
                    {
                        "id": "t1",
                        "kind": "permanent",
                        "count": 1,
                        "selector": {"zone": "battlefield"},
                    }
                ],
                "spell_effects": [
                    {
                        "op": "delayed_trigger",
                        "trigger": trigger,
                        "effects": [{"op": "become_monarch", "player": "you"}],
                    }
                ],
            }
        )

    @pytest.mark.parametrize("event", ["dies", "creature_dies", "leaves_battlefield", "sacrificed"])
    def test_a_departure_scoped_to_its_subject_loads(self, event):
        compile_card(
            self._card(
                {
                    "event": event,
                    "controller": "any",
                    "subject": {"target": "t1"},
                    "condition": {"exists": {"controller": "you", "is_commander": True}},
                }
            )
        )
