"""Heroic (702.109) and ward (702.21): becoming the target of a spell.

The census had these as the last two entries in one cluster, and it was wrong
about which half was hard. Ward was marked `blocked` on `unless_pays` — "it
routes a cost to a player who does not control the ability and inverts the
outcome" — but `unless_pays` shipped with Rhystic Study, because `may` already
takes an arbitrary `player`, a `pay` cost and an `else` branch. What both
keywords were actually waiting on is this: an event for *becoming a target*.

**The timing is the whole mechanic.** Rule 603.2d fires these as the spell or
ability is put on the stack, not as it resolves — so ward asks its question
before the removal spell has done anything, and heroic's counter is on the
creature before the pump spell resolves. Firing on resolution instead would
make ward a refund rather than a tax, and would be the kind of wrong that still
passes a test that only checks the counter appeared.

Two things `_matches` had to be told, both of which are silent when wrong:

**`player` on the event is the caster.** Every `controller` clause on this
trigger asks *whose spell it is* — heroic is "whenever **you** cast a spell that
targets this", ward is "whenever an **opponent** does". Read off the subject
instead, the actor would be the controller of the creature being targeted, which
is nearly always the trigger's own controller: heroic would fire on an
opponent's removal spell, and ward would never fire at all.

**`source: "self"` is the target, not the spell.** For nearly every other
trigger the event's subject and its source are one object, so `_matches` accepts
either. Here the source is the spell and the subject is what it is aimed at.

`counter` grew a `sid` form for ward, because "counter **it**" is not a targeted
ability: the spell it means is the one that just targeted this permanent, which
the trigger's bindings already carried. Written as a target instead, the ward
creature's controller would get to point it at a different spell.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.structs import TargetRef
from tests.conftest import _default_answer, find_action, only_oid, plus_one_counters

HERO = "t_hero"  # 2/2, heroic: a +1/+1 counter
WARDED = "t_warded"  # 2/3, ward {2}
BEAR = "t_bear"  # 2/2 vanilla
BOLT = "t_bolt"  # {R} instant, 3 damage to any target
PUMP = "t_pump_spell"  # {G} instant, targets a creature
REMOVAL = "t_removal"  # destroys target creature


def settle(game, limit: int = 60) -> None:
    for _ in range(limit):
        if not game.state.pending_triggers and not game.state.stack:
            return
        decision = game.pending()
        if decision is None:
            game._advance()
            continue
        game.apply(_default_answer(game, decision))
    raise AssertionError("the stack never emptied")


def cast_at(game, card_id: str, target_oid: int, caster: int = 0) -> None:
    """Cast `card_id` targeting one permanent."""
    for action in game.legal_actions():
        if action.kind is not ActionKind.CAST or action.source is None:
            continue
        obj = game.state.objects.get(action.source)
        if obj is None or obj.def_id != card_id:
            continue
        if TargetRef.obj(target_oid) in action.targets:
            game.apply(action)
            return
    raise AssertionError(
        f"no cast of {card_id} targeting {target_oid}; "
        f"legal: {[(a.kind.value, a.targets) for a in game.legal_actions()]}"
    )


class TestTheEventFires:
    def test_targeting_a_permanent_emits_it(self, builder):
        game = (
            builder(players=2)
            .hand(0, [BOLT])
            .battlefield(0, ["mountain"])
            .battlefield(1, [BEAR])
            .build()
        )
        bear = only_oid(game, BEAR, 1)
        cast_at(game, BOLT, bear)
        fired = [e for e in game.state.events if e.type == EventType.BECAME_TARGET]
        assert len(fired) == 1
        assert fired[0].data["oid"] == bear
        assert fired[0].player == 0, "the caster, not the bear's controller"

    def test_it_fires_before_the_spell_resolves(self, builder):
        """Rule 603.2d — the timing that makes ward mean anything.

        Asserted as an ordering in the event log rather than by catching the
        spell on the stack: with nothing to respond to, the engine auto-passes
        and a bolt aimed at a plain bear resolves in the same `apply`. The
        ordering is the real claim anyway, and it holds either way.
        """
        game = (
            builder(players=2)
            .hand(0, [BOLT])
            .battlefield(0, ["mountain"])
            .battlefield(1, [BEAR])
            .build()
        )
        cast_at(game, BOLT, only_oid(game, BEAR, 1))
        types = [e.type for e in game.state.events]
        assert EventType.BECAME_TARGET in types
        assert types.index(EventType.BECAME_TARGET) < types.index(EventType.DAMAGE_DEALT), (
            "targeting happens as the spell is cast, not as it resolves -- "
            "otherwise ward is a refund rather than a tax"
        )

    def test_casting_with_no_targets_emits_nothing(self, builder):
        game = (
            builder(players=2)
            .hand(0, ["t_draw_spell"])
            .battlefield(0, ["island", "island", "island"])
            .build()
        )
        for action in game.legal_actions():
            if action.kind is ActionKind.CAST:
                game.apply(action)
                break
        assert not [e for e in game.state.events if e.type == EventType.BECAME_TARGET]


class TestHeroic:
    def test_your_own_spell_triggers_it(self, builder):
        game = (
            builder(players=2)
            .hand(0, [PUMP])
            .battlefield(0, ["forest", HERO])
            .build()
        )
        hero = only_oid(game, HERO, 0)
        cast_at(game, PUMP, hero)
        settle(game)
        assert plus_one_counters(game, hero) == 1

    def test_an_opponents_spell_does_not(self, builder):
        """`controller: "you"` on the trigger, and the actor is the caster.

        The failure this guards is not subtle in play and is invisible in code:
        heroic would grow off the removal spell aimed at killing it.
        """
        game = (
            builder(players=2)
            .battlefield(0, [HERO])
            .hand(1, [BOLT])
            .battlefield(1, ["mountain"])
            .active(1)
            .build()
        )
        hero = only_oid(game, HERO, 0)
        cast_at(game, BOLT, hero, caster=1)
        settle(game)
        assert plus_one_counters(game, hero) == 0

    def test_a_spell_targeting_something_else_does_not(self, builder):
        game = (
            builder(players=2)
            .hand(0, [PUMP])
            .battlefield(0, ["forest", HERO, BEAR])
            .build()
        )
        hero = only_oid(game, HERO, 0)
        cast_at(game, PUMP, only_oid(game, BEAR, 0))
        settle(game)
        assert plus_one_counters(game, hero) == 0


class TestWard:
    def position(self, builder):
        game = (
            builder(players=2)
            .battlefield(0, [WARDED])
            .hand(1, [BOLT])
            .battlefield(1, ["mountain", "mountain", "mountain"])
            .active(1)
            .build()
        )
        return game, only_oid(game, WARDED, 0)

    def answer(self, game, pay: bool) -> None:
        """Answer the ward prompt, then let the bolt finish."""
        decision = game.pending()
        assert decision is not None and decision.kind is DecisionKind.MAY, (
            f"expected the ward prompt, got {decision}"
        )
        game.apply(find_action(game, ActionKind.YES if pay else ActionKind.NO))
        # Then just far enough for the bolt to resolve or be gone. Not to the
        # end of the turn: with nothing left to respond to the engine
        # auto-passes into later turns, and every assertion here is about what
        # this one spell did.
        for _ in range(20):
            if not game.state.stack and not game.state.pending_triggers:
                return
            nxt = game.pending()
            if nxt is None:
                game._advance()
                continue
            game.apply(_default_answer(game, nxt))
        raise AssertionError("the bolt never left the stack")

    def test_declining_counters_the_spell(self, builder):
        game, warded = self.position(builder)
        cast_at(game, BOLT, warded, caster=1)
        self.answer(game, pay=False)
        assert any(e.type == EventType.SPELL_COUNTERED for e in game.state.events)
        assert game.state.objects[warded].zone is Zone.BATTLEFIELD, (
            "the bolt was countered, so the 2/3 is untouched"
        )

    def test_paying_lets_the_spell_through(self, builder):
        game, warded = self.position(builder)
        cast_at(game, BOLT, warded, caster=1)
        self.answer(game, pay=True)
        assert not [e for e in game.state.events if e.type == EventType.SPELL_COUNTERED]
        assert game.state.objects[warded].zone is Zone.GRAVEYARD, (
            "three damage to a 2/3 that was paid for"
        )

    def test_the_payer_is_the_caster(self, builder):
        """The whole shape of ward: somebody else pays, and buys nothing.

        `may` has taken an arbitrary `player` since Fact or Fiction, and
        Rhystic Study proved a cost could be routed to one. Ward is that, hung
        on the new trigger -- `{"binding": "event_player"}` is the caster,
        because the event carries the caster in `player`.
        """
        game, warded = self.position(builder)
        cast_at(game, BOLT, warded, caster=1)
        decision = game.pending()
        assert decision is not None
        assert decision.kind is DecisionKind.MAY
        assert decision.player == 1, (
            "the opponent who cast it is asked, not the ward creature's controller"
        )

    def test_your_own_spell_does_not_tax_you(self, builder):
        game = (
            builder(players=2)
            .hand(0, [BOLT])
            .battlefield(0, ["mountain", WARDED])
            .build()
        )
        warded = only_oid(game, WARDED, 0)
        cast_at(game, BOLT, warded)
        settle(game)
        assert not [e for e in game.state.events if e.type == EventType.SPELL_COUNTERED]


class TestTheLoaderGuardsTheCounterForm:
    def base(self, effect: dict) -> dict:
        return {
            "id": "probe",
            "name": "Probe",
            "oracle_text": "x",
            "mana_cost": "{U}",
            "types": ["Creature"],
            "power": 1,
            "toughness": 1,
            "abilities": [
                {
                    "kind": "triggered",
                    "text": "x",
                    "trigger": {"event": "becomes_target", "source": "self"},
                    "effects": [effect],
                }
            ],
        }

    def test_a_sid_expression_is_validated(self):
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.base({"op": "counter", "sid": {"binding_typo": "sid"}})
                )
            )

    def test_sid_and_target_together_are_refused(self):
        """One names the spell that targeted this permanent; the other lets its
        controller pick a different one. A card carrying both is ambiguous."""
        with pytest.raises(DslError):
            compile_card(
                CardModel.model_validate(
                    self.base({"op": "counter", "sid": {"binding": "sid"}, "target": "t1"})
                )
            )

    def test_the_ward_card_compiles(self, registry):
        card = registry.get(WARDED)
        (ability,) = [a for a in card.abilities if a.is_triggered]
        assert ability.trigger is not None
        assert ability.trigger.event == "becomes_target"
        assert ability.trigger.controller == "opponent"
