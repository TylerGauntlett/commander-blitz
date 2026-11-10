"""Exiling a spell off the stack -- which is *not* countering it.

"When this creature enters, exile target spell an opponent controls. Whenever
this creature attacks, if a card is exiled with it, you may cast the exiled card
without paying its mana cost." Smirking Spelljacker is the witness, and its two
sentences make two separate rules claims:

- **701.5a: exiling is not countering.** The spell leaves the stack by a plain
  zone change, so "this spell can't be countered" does not stop it, nothing
  watching for a countered spell sees anything, and the card goes to its
  owner's exile without visiting a graveyard. `counter` with ``exiles`` gets
  all three wrong.
- **607.2a: "exiled with it" is a link.** The card is linked to the creature
  that exiled it, so the attack trigger's intervening if (603.4) and its
  `play_exiled` find exactly that card -- and a new object (400.7) finds
  nothing.

The failure this exists to catch is silent: `exile` aimed at a `kind: "spell"`
target used to resolve through `choose_objects`, whose `{"target": …}` pool
keeps object refs only, so the spell resolved untouched. Every test asserts on
where the *other* spell ended up. A copy of a spell (706.10, 707.10a) has no
card, so it ceases to exist and is linked to nothing.
"""

from __future__ import annotations

import pytest

from commanderblitz.cards.loader import compile_card
from commanderblitz.cards.registry import CardRegistry
from commanderblitz.cards.schema import CardModel
from commanderblitz.engine.effects import execute
from commanderblitz.engine.effects.context import EffectContext
from commanderblitz.engine.effects.ops_stack import put_copy_on_stack
from commanderblitz.engine.enums import ActionKind, DecisionKind, Zone
from commanderblitz.engine.errors import DslError
from commanderblitz.engine.events import EventType
from commanderblitz.engine.sandbox import GameBuilder
from commanderblitz.engine.stack import push_spell
from commanderblitz.engine.structs import TargetRef
from tests.conftest import (
    attack_with,
    count_on_battlefield,
    event_types,
    find_action,
    only_oid,
    pass_until,
)

#: Smirking Spelljacker in the DSL, beside the assertions about its wording.
SPELLJACKER = {
    "id": "t_spelljacker",
    "name": "Test Spelljacker",
    "oracle_text": (
        "Flash\nFlying\nWhen this creature enters, exile target spell an opponent "
        "controls.\nWhenever this creature attacks, if a card is exiled with it, "
        "you may cast the exiled card without paying its mana cost."
    ),
    "mana_cost": "{4}{U}",
    "types": ["Creature"],
    "subtypes": ["Djinn", "Wizard"],
    "power": 3,
    "toughness": 3,
    "keywords": ["flash", "flying"],
    "abilities": [
        {
            "kind": "triggered",
            "text": "When this creature enters, exile target spell an opponent controls.",
            "trigger": {"event": "self_enters", "source": "self"},
            "targets": [
                {"id": "t1", "kind": "spell", "selector": {"controller": "opponent"}, "count": 1}
            ],
            "effects": [{"op": "exile", "objects": {"target": "t1"}, "link": True}],
        },
        {
            "kind": "triggered",
            "text": (
                "Whenever this creature attacks, if a card is exiled with it, you may "
                "cast the exiled card without paying its mana cost."
            ),
            "trigger": {
                "event": "attacks",
                "source": "self",
                "condition": {
                    "exists": {"zone": "exile", "exiled_with": "self", "controller": "any"}
                },
            },
            "effects": [
                {
                    "op": "may",
                    "prompt": "Cast the exiled card without paying its mana cost?",
                    "effects": [
                        {
                            "op": "play_exiled",
                            "objects": {
                                "zone": "exile",
                                "exiled_with": "self",
                                "controller": "any",
                            },
                        }
                    ],
                }
            ],
        },
    ],
}

#: A creature spell that cannot be countered -- where exiling and countering
#: stop agreeing.
STUBBORN = {
    "id": "t_stubborn_bear",
    "name": "Test Stubborn Bear",
    "oracle_text": "This spell can't be countered.",
    "mana_cost": "{1}{G}",
    "types": ["Creature"],
    "subtypes": ["Bear"],
    "power": 2,
    "toughness": 2,
    "uncounterable": True,
}

BEAR = "t_bear"
EXILE_IT = [{"op": "exile", "objects": {"target": "t1"}, "link": True}]


@pytest.fixture
def builder(registry: CardRegistry):
    """The shared pool plus this module's two cards."""
    cards = {card.id: card for card in registry}
    for payload in (SPELLJACKER, STUBBORN):
        card = compile_card(CardModel.model_validate(payload))
        cards[card.id] = card
    pool = CardRegistry(cards)

    def make(players: int = 2, seed: int = 0) -> GameBuilder:
        return GameBuilder(pool, players=players, seed=seed)

    return make


def card_oid(game, def_id: str) -> int:
    return next(oid for oid, obj in game.state.objects.items() if obj.def_id == def_id)


def run_exile(state, controller: int, sid: int, source_oid: int | None) -> None:
    """Run the bare op at the spell ``sid``, and assert it asks nothing."""
    ctx = EffectContext(
        state=state,
        controller=controller,
        source_oid=source_oid,
        targets={"t1": (TargetRef.stack(sid),)},
    )
    for _ in execute(ctx, EXILE_IT):
        raise AssertionError("exiling a targeted spell has no question to ask")


def position(builder, *, spell: str = BEAR):
    """P1 has ``spell`` on the stack; P0 controls a Test Spelljacker.

    Returns ``(game, jacker, card)``: the creature that will exile and the card
    of the spell it is aimed at. Built with `push_spell` so the claim stays on
    the op rather than on flash timing.
    """
    game = (
        builder(players=2)
        .battlefield(0, ["t_spelljacker"])
        .hand(1, [spell])
        .library(0, ["island"] * 10)
        .library(1, ["island"] * 10)
        .build()
    )
    jacker = only_oid(game, "t_spelljacker", 0)
    card = card_oid(game, spell)
    return game, jacker, card


def to_attackers(game) -> None:
    pass_until(
        game,
        lambda g: g.pending() is not None
        and g.pending().kind is DecisionKind.DECLARE_ATTACKERS,
    )


class TestTheSpellIsExiled:
    def test_it_leaves_the_stack_for_its_owners_exile(self, builder):
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)

        run_exile(game.state, 0, item.sid, jacker)

        assert game.state.stack_item(item.sid) is None
        assert game.state.objects[bear].zone is Zone.EXILE
        assert bear in game.state.players[1].exile
        assert game.state.objects[bear].stack_id is None

    def test_it_is_linked_to_the_creature_that_exiled_it(self, builder):
        """607.2a, both ends: the card names its exiler, and the exiler lists it."""
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)

        run_exile(game.state, 0, item.sid, jacker)

        assert game.state.objects[bear].exiled_by == jacker
        assert game.state.objects[jacker].exiled_cards == [bear]

    def test_without_link_the_card_is_exiled_and_linked_to_nothing(self, builder):
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            source_oid=jacker,
            targets={"t1": (TargetRef.stack(item.sid),)},
        )
        for _ in execute(ctx, [{"op": "exile", "objects": {"target": "t1"}}]):
            raise AssertionError("no question")

        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.objects[bear].exiled_by is None

    def test_as_binds_the_exiled_card(self, builder):
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)
        ctx = EffectContext(
            state=game.state,
            controller=0,
            source_oid=jacker,
            targets={"t1": (TargetRef.stack(item.sid),)},
        )
        for _ in execute(ctx, [{"op": "exile", "objects": {"target": "t1"}, "as": "it"}]):
            raise AssertionError("no question")

        assert ctx.bindings["it"] == [bear]


class TestItIsNotACounter:
    """Rule 701.5a. Three observable differences, one per test."""

    def test_an_uncounterable_spell_is_still_exiled(self, builder):
        game, jacker, stubborn = position(builder, spell="t_stubborn_bear")
        item = push_spell(game.state, stubborn, controller=1)

        run_exile(game.state, 0, item.sid, jacker)

        assert game.state.stack_item(item.sid) is None
        assert game.state.objects[stubborn].zone is Zone.EXILE

    def test_nothing_is_told_that_a_spell_was_countered(self, builder):
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)
        mark = len(game.state.events)

        run_exile(game.state, 0, item.sid, jacker)

        assert EventType.SPELL_COUNTERED not in event_types(game.state.events[mark:])

    def test_the_card_does_not_pass_through_a_graveyard(self, builder):
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)

        run_exile(game.state, 0, item.sid, jacker)

        assert bear not in game.state.players[1].graveyard


class TestACopyIsNotACard:
    """706.10, 707.10a: a copy has no card to exile, so it ceases to exist."""

    def test_the_copy_ceases_to_exist_and_is_linked_to_nothing(self, builder):
        game, jacker, bear = position(builder)
        original = push_spell(game.state, bear, controller=1)
        copy = put_copy_on_stack(game.state, 1, original)
        assert copy.oid is not None

        run_exile(game.state, 0, copy.sid, jacker)

        assert game.state.stack_item(copy.sid) is None
        assert copy.oid not in game.state.objects
        assert game.state.objects[jacker].exiled_cards == []
        assert game.state.stack_item(original.sid) is original


class TestWhenTheSpellHasAlreadyGone:
    def test_a_resolved_spell_is_not_reached(self, builder):
        """608.2b: a target that has left the stack is no longer there to move."""
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)
        game.state.stack = [it for it in game.state.stack if it.sid != item.sid]
        game.state.objects[bear].stack_id = None

        run_exile(game.state, 0, item.sid, jacker)

        assert game.state.objects[bear].zone is not Zone.EXILE
        assert game.state.objects[jacker].exiled_cards == []


class TestTheAttackTrigger:
    """The second sentence, through a real game: the linked card is cast free."""

    def _jacked(self, builder):
        game, jacker, bear = position(builder)
        item = push_spell(game.state, bear, controller=1)
        run_exile(game.state, 0, item.sid, jacker)
        return game, jacker, bear

    def _attack(self, game, jacker):
        to_attackers(game)
        attack_with(game, jacker)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(game, lambda g: g.pending() is not None and g.pending().kind is DecisionKind.MAY)

    def test_the_exiled_card_is_cast_for_free_under_its_new_controller(self, builder):
        game, jacker, bear = self._jacked(builder)
        self._attack(game, jacker)

        game.apply(find_action(game, ActionKind.YES))
        pass_until(game, lambda g: not g.state.stack)

        assert count_on_battlefield(game, BEAR, 0) == 1, "cast by the Spelljacker's controller"
        assert game.state.objects[bear].controller == 0
        assert game.state.objects[bear].owner == 1

    def test_declining_leaves_the_card_exiled_and_linked(self, builder):
        game, jacker, bear = self._jacked(builder)
        self._attack(game, jacker)

        game.apply(find_action(game, ActionKind.NO))
        pass_until(game, lambda g: not g.state.stack)

        assert game.state.objects[bear].zone is Zone.EXILE
        assert game.state.objects[bear].exiled_by == jacker

    def test_nothing_exiled_with_it_means_no_trigger(self, builder):
        """603.4: the intervening if is false, so the ability never triggers."""
        game, jacker, _bear = position(builder)
        to_attackers(game)
        attack_with(game, jacker)
        game.apply(find_action(game, ActionKind.FINISH_DECLARATION))
        pass_until(
            game,
            lambda g: g.state.combat is None
            or (g.pending() is not None and g.pending().kind is DecisionKind.MAY),
        )

        assert game.pending() is None or game.pending().kind is not DecisionKind.MAY
        assert not any(t.source_oid == jacker for t in game.state.pending_triggers)
        assert not any(it.source_oid == jacker for it in game.state.stack)


class TestTheLoaderRefusesTheNearMiss:
    def _card(self, objects: dict, kind: str = "spell") -> CardModel:
        return CardModel.model_validate(
            {
                "id": "t_probe",
                "name": "Test Probe",
                "mana_cost": "{1}{U}",
                "types": ["Instant"],
                "oracle_text": "Exile target spell.",
                "targets": [{"id": "t1", "kind": kind, "selector": {}, "count": 1}],
                "spell_effects": [{"op": "exile", "objects": objects}],
            }
        )

    def test_the_target_alone_loads(self):
        compile_card(self._card({"target": "t1"}))

    def test_a_narrowed_spell_target_is_refused_rather_than_ignored(self):
        with pytest.raises(DslError, match="spell target only through"):
            compile_card(self._card({"target": "t1", "types": ["Creature"]}))

    def test_a_narrowed_permanent_target_still_loads(self):
        compile_card(self._card({"target": "t1", "types": ["Creature"]}, kind="permanent"))
